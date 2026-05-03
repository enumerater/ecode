from fastapi import FastAPI
from fastapi.responses import StreamingResponse
import asyncio
import json

from langchain_core.runnables import RunnableConfig

from agent import build_graph
from langchain_core.messages import BaseMessage

app = FastAPI()
agent = build_graph()

def sse(event: str, data: dict):
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"

@app.post("/api/chat/stream")
async def chat_stream(data: dict):
    prompt = data.get("prompt", "")
    project_context = data.get("context", {})
    thread_id = data.get("thread_id", "default_thread")
    tool_result = data.get("tool_result", None)

    print("\n" + "="*50)
    print(f"🟢 用户指令：{prompt}")
    print(f"🟢 会话ID：{thread_id}")
    print("="*50 + "\n")

    config: RunnableConfig = {"configurable": {"thread_id": thread_id}}

    async def generate():
        try:
            async for chunk in agent.astream(
                input={
                    "messages": [{"role": "user", "content": prompt}],
                    "user_prompt": prompt,
                    "project_context": project_context,
                    "tool_result": tool_result,
                    "thread_id": thread_id,
                },
                stream_mode=["messages", "updates"],
                thread_id=thread_id,
                version="v2",
                config=config
            ):
                # ✅ 修复1：删除错误的元组解包，正确处理消息
                if chunk["type"] == "messages":
                    message,metadata = chunk["data"]
                    # 只处理文本消息，跳过工具消息
                    print(f"🟢 输出：{message}")
                    print(f"🟢 元数据：{metadata}")

                    yield sse("text", {"chunk": message.content})
                    await asyncio.sleep(0.01)

                # ✅ 修复2：正确获取工具调用指令
                if chunk["type"] == "updates":
                    print("==================================================================")
                    print(chunk)
                    print("==================================================================")

                    # 修复并取消注释这里的代码
                    state_data = chunk["data"]
                    # LangGraph 的 updates 结构是 {"节点名": {"状态变量": "值"}}
                    if "call_tool" in state_data and state_data["call_tool"].get("tool_call"):
                        tool_call = state_data["call_tool"]["tool_call"]
                        print(f" 发送工具调用: {tool_call}")
                        yield sse("action", tool_call)

            yield sse("done", {"status": "ok"})

        except Exception as e:
            print(f"🔴 后端错误：{str(e)}")
            yield sse("text", {"chunk": f"错误：{str(e)}"})
            yield sse("done", {"status": "error"})

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache"}
    )

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)