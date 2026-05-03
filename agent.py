from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import tools_condition
from langchain_core.tools import StructuredTool, tool
from langchain_core.messages import ToolMessage, AIMessage
from model import llm
from typing import TypedDict, Annotated, Optional, Dict, Any
from langgraph.graph.message import add_messages
from langgraph.checkpoint.memory import InMemorySaver

checkpointer = InMemorySaver()

# ======================
# 你的 State（无修改）
# ======================
class State(TypedDict):
    messages: Annotated[list, add_messages]
    user_prompt: str
    project_context: Optional[Dict[str, Any]]
    tool_call: Optional[Dict[str, Any]]
    tool_result: Optional[Dict[str, Any]]
    thread_id: str
    current_file: Optional[Dict[str, Any]]


# ======================
# 前端工具定义
# ======================
@tool
def view_file(path: str) -> str:
    """【前端执行】查看指定文件的完整内容"""
    return "前端执行结果"

@tool
def edit_file(path: str, start_line: int, end_line: int, content: str) -> str:
    """【前端执行】精确行号修改文件"""
    return "前端执行结果"


frontend_tools = [
    view_file,edit_file
]
tool_llm = llm.bind_tools(frontend_tools)


# ======================
# 节点1：AI 对话节点
# ======================
def chatbot_node(state: State) -> State:
    system_prompt = f"""
    你是代码智能体，基于项目结构完成任务。
    项目上下文：{state.get('project_context', {})}
    需修改代码先查看文件，再精确编辑行号。
    """
    messages = [{"role": "system", "content": system_prompt}] + state["messages"]
    response = tool_llm.invoke(messages)
    return {"messages": [response]}


# ======================
# 节点2：处理工具结果（修复返回None问题）
# ======================
def handle_tool_result(state: State) -> State:
    tool_result = state.get("tool_result")
    # ✅ 修复：永远返回合法State，不返回None/空
    if tool_result:
        tool_msg = ToolMessage(
            content=str(tool_result),
            tool_call_id="frontend_001"
        )
        return {"messages": [tool_msg]}
    # 无结果时返回空消息，不返回None
    return {"messages": []}


# ======================
# 节点3：调用前端工具（修复格式）
# ======================
def call_frontend_tool(state: State) -> State:
    last_msg = state["messages"][-1]
    if isinstance(last_msg, AIMessage) and last_msg.tool_calls:
        tool = last_msg.tool_calls[0]
        return {
            "tool_call": {
                "type": tool["name"],
                **tool["args"]
            }
        }
    # ✅ 修复：无工具调用时返回空，不崩溃
    return {"tool_call": None}


# ======================
# 构建图（中断正常工作）
# ======================
def build_graph():
    graph_builder = StateGraph(State)

    graph_builder.add_node("handle_result", handle_tool_result)
    graph_builder.add_node("chatbot", chatbot_node)
    graph_builder.add_node("call_tool", call_frontend_tool)

    graph_builder.add_edge(START, "handle_result")
    graph_builder.add_edge("handle_result", "chatbot")

    graph_builder.add_conditional_edges(
        "chatbot",
        tools_condition,
        {"tools": "call_tool", "__end__": END}
    )

    graph_builder.add_edge("call_tool", END)

    # ✅ 核心：调用工具后中断
    return graph_builder.compile(
        debug=True,
        checkpointer=checkpointer,
    )