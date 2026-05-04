from datetime import datetime
from langgraph.checkpoint.memory import InMemorySaver

checkpointer = InMemorySaver()

_sessions: dict[str, dict] = {}


class SessionManager:
    def create_or_update(self, thread_id: str, project_root: str, title: str = ""):
        now = datetime.now().isoformat()
        if thread_id not in _sessions:
            _sessions[thread_id] = {
                "thread_id": thread_id,
                "project_root": project_root,
                "title": title or "New Chat",
                "created_at": now,
                "updated_at": now,
            }
        else:
            _sessions[thread_id]["updated_at"] = now

    def list_sessions(self) -> list[dict]:
        return sorted(_sessions.values(), key=lambda s: s["updated_at"], reverse=True)

    def get_session(self, thread_id: str) -> dict | None:
        return _sessions.get(thread_id)

    def delete_session(self, thread_id: str) -> bool:
        if thread_id in _sessions:
            del _sessions[thread_id]
            return True
        return False

    def get_history(self, thread_id: str, graph) -> list[dict]:
        config = {"configurable": {"thread_id": thread_id}}
        state = graph.get_state(config)
        if not state or not state.values:
            return []
        messages = state.values.get("messages", [])
        return [self._serialize_message(m) for m in messages]

    @staticmethod
    def _serialize_message(msg) -> dict:
        base = {
            "id": getattr(msg, "id", None),
            "type": msg.type,
            "content": msg.content if isinstance(msg.content, str) else str(msg.content),
        }
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            base["tool_calls"] = msg.tool_calls
        if hasattr(msg, "tool_call_id") and msg.tool_call_id:
            base["tool_call_id"] = msg.tool_call_id
        return base


session_manager = SessionManager()
