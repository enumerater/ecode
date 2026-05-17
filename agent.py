import json
import asyncio
import logging
from typing import TypedDict, Annotated

from langchain_core.messages import (
    BaseMessage, AIMessage, ToolMessage, SystemMessage, HumanMessage,
)
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.types import interrupt

# llm 延迟导入，避免未配置时 import 失败
from session import get_checkpointer
from tools import ALL_TOOLS, SAFE_TOOLS, DANGEROUS_TOOLS, TOOL_META, set_project_root
from tools.context_tools import COMPACT_SIGNAL
from tools.tool_index import build_tool_index
from tools.tool_executor import execute_tool_batches
from context_manager import micro_compact, auto_compact, manual_compact, reactive_compact
from project_context import load_project_context
from memory.loader import load_memories
from permissions.rules import evaluate_permission, Behavior, PermissionRule
from permissions.modes import PermissionMode, get_mode_defaults
from settings import Settings

logger = logging.getLogger(__name__)

# 工具结果最大字符数，超过则截断（保留头尾）
MAX_TOOL_RESULT_CHARS = 8000

# 最大重试次数
MAX_RETRIES = 3

# 错误恢复：指数退避基础延迟（秒）
RETRY_BASE_DELAY = 1.0

# 不可变工作规则（纯静态文本，不含模板变量，跨轮复用以最大化 KV cache）
IMMUTABLE_INSTRUCTIONS = """\
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

### 工具详情
工具一览表已在上方列出。当你不确定某个工具的参数或用法时，先调用 get_tool_details 获取完整文档，再使用该工具。

## 沟通
- 简洁直接，不要废话。
- 匹配用户语言（中文或英文）。
- 不确定时先问，不要猜。
- 展示变更时用 diff 格式（- 旧 / + 新）。
"""


def _build_immutable_context(project_root: str) -> str:
    """构建不可变 system prompt 前缀。每个 session 只调用一次。

    内容跨轮完全一致，LLM provider 可缓存 KV。
    """
    sections = []

    # 头部：角色 + 项目根目录
    header = f"你是一个 AI 编码助手，可以直接操作项目文件系统。\n\n项目根目录: {project_root}"
    sections.append(header)

    # ecode.md 项目上下文
    ecode_md = load_project_context(project_root)
    if ecode_md:
        sections.append(f"## 项目上下文 (ecode.md)\n\n{ecode_md}")

    # 记忆系统
    memories = load_memories(project_root)
    if memories:
        sections.append(f"## 跨会话记忆\n\n{memories}")

    # 工具索引表
    tool_index = build_tool_index(ALL_TOOLS, SAFE_TOOLS, DANGEROUS_TOOLS, TOOL_META)
    sections.append(f"## 可用工具一览\n\n{tool_index}\n\n使用 `get_tool_details` 工具获取某个工具的完整文档。")

    # 工作规则
    sections.append(IMMUTABLE_INSTRUCTIONS)

    return "\n\n---\n\n".join(sections)

_tool_llm = None


def _get_tool_llm():
    global _tool_llm
    if _tool_llm is None:
        from model import llm
        _tool_llm = llm.bind_tools(ALL_TOOLS)
    return _tool_llm


class State(TypedDict):
    messages: Annotated[list[BaseMessage], add_messages]
    project_root: str
    last_error: str
    retry_count: int
    usage: dict  # {"prompt_tokens": int, "completion_tokens": int, "total_tokens": int}
    compact_summary: str  # 最近一次压缩的摘要文本
    compact_at: int  # 压缩时的消息数量，用于判断哪些是新消息
    immutable_context: str  # 不可变上下文（ecode.md + 工具索引 + 工作规则），构建一次跨轮复用
    permission_mode: str  # 权限模式：default, plan, auto_approve, yolo
    plan_mode: bool  # 是否处于计划模式


def _is_prompt_too_long_error(error: Exception) -> bool:
    """检测是否为 prompt-too-long 错误。"""
    error_str = str(error).lower()
    return any(kw in error_str for kw in [
        "context_length_exceeded",
        "maximum context length",
        "prompt is too long",
        "token limit",
        "context window",
        "request too large",
        "max_tokens",
    ])


def _is_transient_api_error(error: Exception) -> bool:
    """检测是否为瞬态 API 错误（可重试）。"""
    error_str = str(error).lower()
    return any(kw in error_str for kw in [
        "rate_limit",
        "rate limit",
        "overloaded",
        "529",
        "503",
        "timeout",
        "connection",
        "econnreset",
    ])


def think(state: State) -> dict:
    from model import llm
    messages = list(state["messages"])
    original_msg_count = len(messages)

    # ── 不可变上下文：构建一次，跨轮复用 ──
    immutable_ctx = state.get("immutable_context")
    if not immutable_ctx:
        project_root = state.get("project_root", ".")
        immutable_ctx = _build_immutable_context(project_root)

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
        result["compact_summary"] = summary
        result["compact_at"] = original_msg_count

    # 首次构建时存入 state，后续轮次直接复用
    if not state.get("immutable_context"):
        result["immutable_context"] = immutable_ctx

    # ── 组装：不可变 SystemMessage（缓存前缀）+ 可变消息 ──
    plan_mode = state.get("plan_mode", False)
    if plan_mode:
        plan_instruction = SystemMessage(content="""## ⚠️ 计划模式已激活

你当前处于**计划模式**。在此模式下：
- **禁止**执行任何修改操作（edit_file, write_file, create_file, create_directory, run_command, git_commit）
- **只允许**分析代码、搜索、查看文件等只读操作
- 你的任务是：分析问题、制定计划、输出详细的实施方案
- 计划完成后，调用 `exit_plan_mode` 工具请求用户批准执行

请专注于分析和规划，不要尝试执行修改。""")
        full_messages = [SystemMessage(content=immutable_ctx), plan_instruction] + messages
    else:
        full_messages = [SystemMessage(content=immutable_ctx)] + messages

    try:
        response = _get_tool_llm().invoke(full_messages)
    except Exception as e:
        # ── 错误恢复：prompt-too-long → Reactive Compact 重试 ──
        if _is_prompt_too_long_error(e):
            logger.warning(f"Prompt-too-long 错误，触发 Reactive Compact: {e}")
            compacted_messages, compact_summary_text = reactive_compact(messages, llm)
            if compact_summary_text:
                result["compact_summary"] = compact_summary_text
                result["compact_at"] = original_msg_count
                # 重试 LLM 调用
                full_messages = [SystemMessage(content=immutable_ctx)] + compacted_messages
                try:
                    response = _get_tool_llm().invoke(full_messages)
                except Exception as retry_e:
                    logger.error(f"Reactive Compact 重试失败: {retry_e}")
                    result["messages"] = [AIMessage(content=f"抱歉，上下文过长且压缩后仍无法处理: {retry_e}")]
                    return result
            else:
                result["messages"] = [AIMessage(content=f"抱歉，上下文过长且压缩失败: {e}")]
                return result
        else:
            raise

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
    compact_triggered = False
    compact_instruction = ""

    set_project_root(state.get("project_root", "."))

    # 获取权限模式和规则
    permission_mode = state.get("permission_mode", "default")
    try:
        mode = PermissionMode(permission_mode)
    except ValueError:
        mode = PermissionMode.DEFAULT

    project_root = state.get("project_root", ".")
    settings = Settings(project_root)
    mode_rules = get_mode_defaults(mode)
    all_rules = settings.get_all_rules() + mode_rules

    # 创建权限检查函数
    def check_permission(tool_name: str, tool_args: dict) -> str:
        """返回 'allow', 'deny', 或 'ask'"""
        result = evaluate_permission(tool_name, tool_args, all_rules)
        return result.behavior.value

    # 使用并行工具执行器（传入权限检查函数）
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(
                    asyncio.run,
                    execute_tool_batches(
                        tool_calls=last.tool_calls,
                        tool_map=tool_map,
                        tool_meta=TOOL_META,
                        interrupt_fn=interrupt,
                        dangerous_tools=DANGEROUS_TOOLS,
                        permission_checker=check_permission,
                    ),
                )
                results = future.result(timeout=300)
        else:
            results = loop.run_until_complete(
                execute_tool_batches(
                    tool_calls=last.tool_calls,
                    tool_map=tool_map,
                    tool_meta=TOOL_META,
                    interrupt_fn=interrupt,
                    dangerous_tools=DANGEROUS_TOOLS,
                    permission_checker=check_permission,
                ),
            )
    except RuntimeError:
        results = asyncio.run(
            execute_tool_batches(
                tool_calls=last.tool_calls,
                tool_map=tool_map,
                tool_meta=TOOL_META,
                interrupt_fn=interrupt,
                dangerous_tools=DANGEROUS_TOOLS,
                permission_checker=check_permission,
            ),
        )

    # 处理 compact 信号和 plan mode 信号
    plan_mode_enter = False
    plan_mode_exit = False
    for i, tc in enumerate(last.tool_calls):
        if tc["name"] == "compact":
            # 找到对应的 ToolMessage
            for msg in results:
                if msg.tool_call_id == tc["id"]:
                    try:
                        signal_data = json.loads(msg.content)
                        if signal_data.get("signal") == COMPACT_SIGNAL:
                            compact_triggered = True
                            compact_instruction = signal_data.get("instruction", "")
                    except (json.JSONDecodeError, TypeError):
                        pass
        elif tc["name"] == "enter_plan_mode":
            for msg in results:
                if msg.tool_call_id == tc["id"]:
                    try:
                        signal_data = json.loads(msg.content)
                        if signal_data.get("signal") == "ENTER_PLAN_MODE":
                            plan_mode_enter = True
                    except (json.JSONDecodeError, TypeError):
                        pass
        elif tc["name"] == "exit_plan_mode":
            for msg in results:
                if msg.tool_call_id == tc["id"]:
                    try:
                        signal_data = json.loads(msg.content)
                        if signal_data.get("signal") == "EXIT_PLAN_MODE":
                            plan_mode_exit = True
                    except (json.JSONDecodeError, TypeError):
                        pass

    # Layer 3: 处理 compact 信号 — 生成摘要并存入 state
    final_update = {"messages": results}

    # 处理 plan mode 状态变更
    current_plan_mode = state.get("plan_mode", False)
    if plan_mode_enter and not current_plan_mode:
        final_update["plan_mode"] = True
        final_update["permission_mode"] = "plan"
        logger.info("进入计划模式")
    elif plan_mode_exit and current_plan_mode:
        final_update["plan_mode"] = False
        final_update["permission_mode"] = "default"
        logger.info("退出计划模式")
    if compact_triggered:
        logger.info("Manual Compact 触发")
        all_messages = state["messages"] + results
        _, summary = manual_compact(all_messages, llm, compact_instruction)
        if summary:
            final_update["compact_summary"] = summary
            final_update["compact_at"] = len(all_messages)
            # 替换 compact 工具的结果
            for i, msg in enumerate(results):
                if hasattr(msg, 'tool_call_id'):
                    # 找到 compact 工具的 ToolMessage
                    for tc in last.tool_calls:
                        if tc["name"] == "compact" and msg.tool_call_id == tc["id"]:
                            results[i] = ToolMessage(
                                content=json.dumps({
                                    "success": True,
                                    "summary": summary[:200],
                                    "message": f"上下文已压缩。{len(all_messages)} 条历史消息已摘要化。",
                                }, ensure_ascii=False),
                                tool_call_id=msg.tool_call_id,
                            )
                            break

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

    return g.compile(checkpointer=get_checkpointer())
