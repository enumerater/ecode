import json
import logging
from typing import TypedDict, Annotated

from langchain_core.messages import (
    BaseMessage, AIMessage, ToolMessage, SystemMessage, HumanMessage,
)
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.types import interrupt

from model import llm
from session import checkpointer
from tools import ALL_TOOLS, DANGEROUS_TOOLS, set_project_root
from tools.context_tools import COMPACT_SIGNAL
from context_manager import micro_compact, auto_compact, manual_compact

logger = logging.getLogger(__name__)

# 工具结果最大字符数，超过则截断（保留头尾）
MAX_TOOL_RESULT_CHARS = 8000

SYSTEM_PROMPT_TEMPLATE = """\
你是一个 AI 编码助手，可以直接操作项目文件系统。

项目根目录: {project_root}

## 工作规则

### 先读后写
编辑前必须先用 view_file 查看文件内容，确认要修改的上下文。不要凭记忆修改。

### 局部修改优先
优先使用 edit_file 进行局部修改（old_string → new_string），而不是 write_file 全量覆盖。
- old_string 应包含足够的上下文使其唯一匹配（通常 3-10 行）
- 不要包含过多不变的行，只取必要的上下文

### 每次只做一个逻辑变更
先说明计划，再执行。不要一次性做多个不相关的修改。

### 变更后验证
修改后回读文件或运行测试，确认变更生效且无误。

### 错误处理
工具失败时分析错误原因，换一种方式重试，不要重复同样的调用。

### 路径规则
所有路径相对于项目根目录。不要使用绝对路径。

### 上下文管理
- 当对话变长或切换任务时，调用 compact 工具压缩上下文
- compact 工具会保留关键信息，释放 token 空间
- 在以下情况考虑调用 compact：
  - 切换到一个完全不同的任务
  - 感觉上下文中有大量不再相关的历史信息
  - 接连完成多个独立小任务后

## 沟通
- 简洁直接，不要废话。
- 匹配用户语言（中文或英文）。
- 不确定时先问，不要猜。
- 展示变更时用 diff 格式（- 旧 / + 新）。
"""

tool_llm = llm.bind_tools(ALL_TOOLS)


class State(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    project_root: str
    last_error: str
    retry_count: int
    usage: dict  # {"prompt_tokens": int, "completion_tokens": int, "total_tokens": int}
    compact_summary: str  # 最近一次压缩的摘要文本
    compact_at: int  # 压缩时的消息数量，用于判断哪些是新消息


def think(state: State) -> dict:
    project_root = state.get("project_root", ".")
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(project_root=project_root)
    messages = list(state["messages"])
    original_msg_count = len(messages)  # 记录原始 state 消息数

    # Layer 3: 如果有 compact_summary，只保留压缩后的摘要 + 新消息
    compact_summary = state.get("compact_summary")
    compact_at = state.get("compact_at", 0)
    if compact_summary and compact_at > 0 and compact_at < len(messages):
        new_messages = messages[compact_at:]
        messages = [SystemMessage(content=f"[对话历史摘要]\n{compact_summary}")] + new_messages

    # Layer 1: Micro-Compact — 每轮自动，替换旧工具结果为占位符
    messages = micro_compact(messages)

    # Layer 2: Auto-Compact — token 超阈值时调用 LLM 生成摘要
    result = {"messages": []}
    messages, summary = auto_compact(messages, llm)
    if summary:
        logger.info(f"Auto-Compact 摘要: {summary[:100]}...")
        # 持久化压缩结果到 state，避免下轮重复处理完整历史
        # compact_at 记录的是原始 state 中的位置，不是压缩后列表的长度
        result["compact_summary"] = summary
        result["compact_at"] = original_msg_count

    full_messages = [SystemMessage(content=system_prompt)] + messages
    response = tool_llm.invoke(full_messages)

    # 累积 token 用量
    usage = state.get("usage") or {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    if hasattr(response, "usage_metadata") and response.usage_metadata:
        um = response.usage_metadata
        usage = {
            "prompt_tokens": usage["prompt_tokens"] + um.get("input_tokens", 0),
            "completion_tokens": usage["completion_tokens"] + um.get("output_tokens", 0),
            "total_tokens": usage["total_tokens"] + um.get("total_tokens", 0),
        }

    result["messages"] = [response]
    result["usage"] = usage
    return result


def execute_tools(state: State) -> dict:
    last = state["messages"][-1]
    tool_map = {t.name: t for t in ALL_TOOLS}
    results = []
    compact_triggered = False
    compact_instruction = ""

    set_project_root(state.get("project_root", "."))

    for tc in last.tool_calls:
        tool_name = tc["name"]
        tool_args = tc["args"]

        # 检查工具是否存在
        if tool_name not in tool_map:
            results.append(ToolMessage(
                content=json.dumps({
                    "success": False,
                    "error": f"未知工具: {tool_name}。可用工具: {', '.join(tool_map.keys())}",
                }, ensure_ascii=False),
                tool_call_id=tc["id"],
            ))
            continue

        # 危险工具需要审批
        if tool_name in DANGEROUS_TOOLS:
            approval = interrupt({
                "type": "tool_approval",
                "tool_name": tool_name,
                "tool_call_id": tc["id"],
                "args": tool_args,
            })
            if approval == "rejected":
                results.append(ToolMessage(
                    content=json.dumps({"success": False, "error": "用户拒绝了此操作"}, ensure_ascii=False),
                    tool_call_id=tc["id"],
                ))
                continue

        try:
            result = tool_map[tool_name].invoke(tool_args)

            # 检查是否是 compact 工具的信号
            if tool_name == "compact":
                try:
                    signal_data = json.loads(result)
                    if signal_data.get("signal") == COMPACT_SIGNAL:
                        compact_triggered = True
                        compact_instruction = signal_data.get("instruction", "")
                except (json.JSONDecodeError, TypeError):
                    pass

            # 截断过大的工具结果，防止 token 暴涨
            if len(result) > MAX_TOOL_RESULT_CHARS:
                keep = MAX_TOOL_RESULT_CHARS // 2
                result = result[:keep] + f"\n... [结果已截断，原长 {len(result)} 字符] ...\n" + result[-keep:]

            results.append(ToolMessage(content=result, tool_call_id=tc["id"]))
        except Exception as e:
            results.append(ToolMessage(
                content=json.dumps({"success": False, "error": f"工具执行异常: {e}"}, ensure_ascii=False),
                tool_call_id=tc["id"],
            ))

    # Layer 3: 处理 compact 信号 — 生成摘要并存入 state
    final_update = {"messages": results}
    if compact_triggered:
        logger.info("Manual Compact 触发")
        # 用当前完整消息列表生成摘要
        all_messages = state["messages"] + results
        _, summary = manual_compact(all_messages, llm, compact_instruction)
        if summary:
            # 记录压缩位置：当前消息总数（后续新消息从这个位置开始）
            final_update["compact_summary"] = summary
            final_update["compact_at"] = len(all_messages)
            # 替换 compact 工具的结果为包含摘要确认的版本
            results[-1] = ToolMessage(
                content=json.dumps({
                    "success": True,
                    "summary": summary[:200],
                    "message": f"上下文已压缩。{len(all_messages)} 条历史消息已摘要化。",
                }, ensure_ascii=False),
                tool_call_id=results[-1].tool_call_id,
            )

    return final_update


def handle_error(state: State) -> dict:
    last_error = ""
    # 检查最后一批 ToolMessage 中是否有错误
    for msg in reversed(state["messages"]):
        if not isinstance(msg, ToolMessage):
            break
        try:
            result = json.loads(msg.content)
            if not result.get("success", True):
                last_error = result.get("error", "Unknown error")
                break
        except (json.JSONDecodeError, TypeError):
            pass

    # 如果没有错误，重置重试计数
    if not last_error:
        return {"last_error": "", "retry_count": 0}

    # 有错误时增加重试计数
    retry = state.get("retry_count", 0) + 1

    # 重试次数耗尽，返回一条消息告知用户而不是静默结束
    if retry > MAX_RETRIES:
        return {
            "last_error": last_error,
            "retry_count": retry,
            "messages": [AIMessage(content=f"抱歉，连续多次工具调用失败（最近的错误: {last_error}），已停止重试。请检查问题后重试。")],
        }

    return {"last_error": last_error, "retry_count": retry}


def route_after_think(state: State) -> str:
    last = state["messages"][-1]
    if isinstance(last, AIMessage) and last.tool_calls:
        return "execute_tools"
    return END


MAX_RETRIES = 3


def should_continue(state: State) -> str:
    retry_count = state.get("retry_count", 0)
    if retry_count > MAX_RETRIES:
        return END
    return "think"


def build_graph():
    g = StateGraph(State)

    g.add_node("think", think)
    g.add_node("execute_tools", execute_tools)
    g.add_node("handle_error", handle_error)

    g.add_edge(START, "think")
    g.add_conditional_edges("think", route_after_think, {
        "execute_tools": "execute_tools",
        END: END,
    })
    g.add_edge("execute_tools", "handle_error")
    g.add_conditional_edges("handle_error", should_continue, {
        "think": "think",
        END: END,
    })

    return g.compile(checkpointer=checkpointer)
