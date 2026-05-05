import json
from typing import TypedDict, Annotated

from langchain_core.messages import (
    BaseMessage, AIMessage, ToolMessage, SystemMessage,
)
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.types import interrupt

from model import llm
from session import checkpointer
from tools import ALL_TOOLS, DANGEROUS_TOOLS, set_project_root


SYSTEM_PROMPT_TEMPLATE = """\
你是一个 AI 编码助手，可以直接操作项目文件系统。

项目根目录: {project_root}

## 可用工具

### 只读（免审批）
- view_file(path, start_line?, end_line?): 读取文件内容。支持行范围。编辑前务必先查看。
- search_code(pattern, path?): 用正则在文件中搜索代码。
- list_files(path?, pattern?): 列出目录文件，支持 glob 过滤。

### 可写（需审批）
- edit_file(path, old_string, new_string): 局部修改文件，将 old_string 替换为 new_string。old_string 必须唯一匹配。
- write_file(path, content): 覆盖写入文件全部内容。文件不存在则创建。
- create_file(path, content): 创建新文件。已存在则失败。
- create_directory(path): 创建目录（递归创建）。
- run_command(command): 执行终端命令。

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


def think(state: State) -> dict:
    project_root = state.get("project_root", ".")
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(project_root=project_root)
    messages = [SystemMessage(content=system_prompt)] + state["messages"]
    response = tool_llm.invoke(messages)
    return {"messages": [response]}


def execute_tools(state: State) -> dict:
    last = state["messages"][-1]
    tool_map = {t.name: t for t in ALL_TOOLS}
    results = []

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
            results.append(ToolMessage(content=result, tool_call_id=tc["id"]))
        except Exception as e:
            results.append(ToolMessage(
                content=json.dumps({"success": False, "error": f"工具执行异常: {e}"}, ensure_ascii=False),
                tool_call_id=tc["id"],
            ))

    return {"messages": results}


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
