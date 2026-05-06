import asyncio
import json

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage, ToolMessage, AIMessage
from langgraph.types import Command

from agent import build_graph
from schemas import ChatRequest, ResumeRequest
from session import session_manager
from utils.sse import sse

app = FastAPI(title="AI Coding Agent")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

graph = build_graph()


async def stream_graph(input_data, config: dict):
    """共享的 SSE 流生成器，供 chat/stream 和 chat/resume 使用。"""
    try:
        accumulated_usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

        async for chunk in graph.astream(
            input_data,
            stream_mode=["messages", "updates"],
            config=config,
            version="v2",
        ):
            typ = chunk.get("type")
            data = chunk.get("data")

            if typ == "messages":
                msg, metadata = data
                node = metadata.get("langgraph_node", "")

                # AI 文本响应
                if node == "think" and msg.content:
                    yield sse("text", {"chunk": msg.content})
                    await asyncio.sleep(0.01)

                # 流式 token 用量（streaming usage metadata）
                if node == "think" and hasattr(msg, "usage_metadata") and msg.usage_metadata:
                    um = msg.usage_metadata
                    accumulated_usage = {
                        "prompt_tokens": um.get("input_tokens", 0),
                        "completion_tokens": um.get("output_tokens", 0),
                        "total_tokens": um.get("total_tokens", 0),
                    }

                # 工具调用请求
                if hasattr(msg, "tool_calls") and msg.tool_calls:
                    for tc in msg.tool_calls:
                        if tc.get("name") and tc.get("args"):
                            yield sse("tool_call", {
                                "tool_name": tc["name"],
                                "tool_call_id": tc["id"],
                                "args": tc["args"],
                            })

                # 工具执行结果
                if isinstance(msg, ToolMessage) and node == "execute_tools":
                    yield sse("tool_result", {
                        "tool_call_id": msg.tool_call_id,
                        "result": msg.content,
                    })

            elif typ == "updates":
                # 中断（需要审批）
                if "__interrupt__" in data:
                    for intr in data["__interrupt__"]:
                        yield sse("approval_required", intr.value)

                # 从节点更新中提取累积 usage（think 节点返回的最终值）
                if isinstance(data, dict):
                    for _node_name, node_output in data.items():
                        if isinstance(node_output, dict) and "usage" in node_output:
                            accumulated_usage = node_output["usage"]

        # 在 done 之前发送 token 用量
        yield sse("usage", accumulated_usage)
        yield sse("done", {"status": "ok"})

    except Exception as e:
        yield sse("error", {"message": str(e)})
        yield sse("done", {"status": "error"})


# ─── POST /api/chat/stream ───

@app.post("/api/chat/stream")
async def chat_stream(req: ChatRequest):
    config = {"configurable": {"thread_id": req.thread_id}}
    session_manager.create_or_update(
        req.thread_id, req.project_root, title=req.prompt[:50]
    )

    input_data = {
        "messages": [HumanMessage(content=req.prompt)],
        "project_root": req.project_root,
    }

    return StreamingResponse(
        stream_graph(input_data, config),
        media_type="text/event-stream",
    )


# ─── POST /api/chat/resume ───

@app.post("/api/chat/resume")
async def chat_resume(req: ResumeRequest):
    session = session_manager.get_session(req.thread_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    config = {"configurable": {"thread_id": req.thread_id}}
    session_manager.create_or_update(req.thread_id, session["project_root"])

    return StreamingResponse(
        stream_graph(Command(resume=req.approval), config),
        media_type="text/event-stream",
    )


# ─── GET /api/sessions ───

@app.get("/api/sessions")
async def list_sessions():
    return session_manager.list_sessions()


# ─── DELETE /api/sessions/{thread_id} ───

@app.delete("/api/sessions/{thread_id}")
async def delete_session(thread_id: str):
    if not session_manager.delete_session(thread_id):
        raise HTTPException(status_code=404, detail="Session not found")
    return {"status": "ok"}


# ─── GET /api/sessions/{thread_id}/history ───

@app.get("/api/sessions/{thread_id}/history")
async def get_history(thread_id: str):
    session = session_manager.get_session(thread_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return session_manager.get_history(thread_id, graph)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
