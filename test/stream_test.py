from langchain_core.messages import HumanMessage
from langgraph.types import Command
from langchain_core.runnables import RunnableConfig
import time

from agent import build_graph


def stream_print():
    config: RunnableConfig = {"configurable": {"thread_id": "1"}}
    graph = build_graph()

    initial_state = {
        "messages": [HumanMessage(content="查看一下 README.md")],
        "project_root": ".",
    }

    print("🤖 开始执行 LangGraph 流式输出...\n")

    # ==================== 第一轮流 ====================
    for chunk in graph.stream(
        initial_state,
        config=config,
        stream_mode=["messages", "updates"],
        version="v2",
    ):
        typ = chunk.get("type")
        data = chunk.get("data")

        # -------------------- messages：打字机输出 --------------------
        if typ == "messages":
            msg_chunk, meta = data
            content = msg_chunk.content.strip()

            # 有内容才打字机输出
            if content:
                for char in content:
                    print(char, end="", flush=True)
                    time.sleep(0.02)  # 打字机速度，可调

            # 工具调用
            if hasattr(msg_chunk, "tool_calls") and msg_chunk.tool_calls:
                print(f"\n🔧 调用工具: {msg_chunk.tool_calls}")

        # -------------------- updates：节点/中断 --------------------
        elif typ == "updates":
            if "__interrupt__" in data:
                print(f"\n⏸️ 中断: {data['__interrupt__'][0].value}")
            for node in data:
                if node != "__interrupt__":
                    print(f"\n📌 执行节点: {node}")

    print("\n" + "=" * 60)

    # ==================== 第二轮 resume：打字机输出 ====================
    mock_file_content = "Hello World! This is README from ecode_back."
    for chunk in graph.stream(
        Command(resume=mock_file_content),
        config=config,
        stream_mode=["messages", "updates"],
        version="v2",
    ):
        typ = chunk.get("type")
        data = chunk.get("data")

        if typ == "messages":
            msg_chunk, meta = data
            content = msg_chunk.content

            if content:
                for char in content:
                    print(char, end="", flush=True)
                    time.sleep(0.02)

    print("\n")


if __name__ == "__main__":
    stream_print()