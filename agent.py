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
- view_file(path): 读取文件内容。编辑前务必先查看。
- edit_file(path, content): 替换文件全部内容。需要用户审批。
- create_file(path, content): 创建新文件。已存在则失败。需要用户审批。
- search_code(pattern, path?): 用正则在文件中搜索代码。
- list_files(path?, pattern?): 列出目录文件，支持 glob 过滤。
- run_command(command): 执行终端命令。需要用户审批。

## 工作规则
1. 先读后写。编辑前先用 view_file 或 search_code 了解上下文。
2. edit_file 时提供完整文件内容，不是 diff。
3. 每次只做一个逻辑变更，先说明计划再执行。
4. 变更后验证：回读文件或运行测试。
5. 工具失败时分析错误，换一种方式重试，不要重复同样的调用。
6. 路径相对于项目根目录。

## 沟通
- 简洁直接。
- 匹配用户语言（中文或英文）。
- 不确定时先问，不要猜。
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

        if tool_name in DANGEROUS_TOOLS:
            approval = interrupt({
                "type": "tool_approval",
                "tool_name": tool_name,
                "tool_call_id": tc["id"],
                "args": tc["args"],
            })
            if approval == "rejected":
                results.append(ToolMessage(
                    content=json.dumps({"success": False, "error": "用户拒绝了此操作"}),
                    tool_call_id=tc["id"],
                ))
                continue

        try:
            result = tool_map[tool_name].invoke(tc["args"])
            results.append(ToolMessage(content=result, tool_call_id=tc["id"]))
        except Exception as e:
            results.append(ToolMessage(
                content=json.dumps({"success": False, "error": str(e)}),
                tool_call_id=tc["id"],
            ))

    return {"messages": results}


def handle_error(state: State) -> dict:
    last_error = ""
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

    retry = (state.get("retry_count", 0) + 1) if last_error else 0
    return {"last_error": last_error, "retry_count": retry}


def route_after_think(state: State) -> str:
    last = state["messages"][-1]
    if isinstance(last, AIMessage) and last.tool_calls:
        return "execute_tools"
    return END


def should_continue(state: State) -> str:
    if state.get("retry_count", 0) > 3:
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
