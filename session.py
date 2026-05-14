"""会话管理：MySQL 持久化的 Checkpointer + SessionManager。"""

import os
import logging
from datetime import datetime

import yaml
import pymysql
from langgraph.checkpoint.mysql.pymysql import PyMySQLSaver

logger = logging.getLogger(__name__)

# ── 数据库配置加载 ────────────────────────────────────────────────────────

def _load_db_config() -> dict:
    """从 config.yaml 读取 database 配置。"""
    config_path = os.path.join(os.path.dirname(__file__), "config.yaml")
    with open(config_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return raw.get("database", {})


def _get_pymysql_conn(cfg: dict) -> pymysql.Connection:
    """创建一个 pymysql 原生连接（用于 SessionManager）。"""
    host = cfg.get("host", "localhost")
    port = cfg.get("port", 3306)
    user = cfg.get("user", "root")
    database = cfg.get("database", "ecode")

    password = ""
    password_env = cfg.get("password_env")
    if password_env:
        password = os.environ.get(password_env, "")
    if not password:
        password = cfg.get("password", "")

    return pymysql.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        database=database,
        charset="utf8mb4",
        autocommit=True,
    )


# ── Checkpointer（LangGraph 状态持久化）──────────────────────────────────

_db_cfg = _load_db_config()

# 创建持久连接给 PyMySQLSaver（from_conn_string 是 context manager 不适合模块级单例）
_cp_conn = _get_pymysql_conn(_db_cfg)
checkpointer = PyMySQLSaver(_cp_conn)
checkpointer.setup()
logger.info("MySQL checkpointer 已初始化并建表")


# ── SessionManager（会话元数据持久化）────────────────────────────────────

_SESSIONS_TABLE = "sessions"

_CREATE_SESSIONS_TABLE = f"""
CREATE TABLE IF NOT EXISTS {_SESSIONS_TABLE} (
    thread_id    VARCHAR(255) PRIMARY KEY,
    project_root VARCHAR(512) NOT NULL,
    title        VARCHAR(255) DEFAULT 'New Chat',
    created_at   DATETIME NOT NULL,
    updated_at   DATETIME NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
"""


class SessionManager:
    def __init__(self):
        self._ensure_table()

    def _ensure_table(self):
        conn = _get_pymysql_conn(_db_cfg)
        try:
            with conn.cursor() as cur:
                cur.execute(_CREATE_SESSIONS_TABLE)
        finally:
            conn.close()

    def _conn(self) -> pymysql.Connection:
        return _get_pymysql_conn(_db_cfg)

    def create_or_update(self, thread_id: str, project_root: str, title: str = ""):
        now = datetime.now()
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT thread_id FROM {_SESSIONS_TABLE} WHERE thread_id = %s",
                    (thread_id,),
                )
                exists = cur.fetchone()
                if exists:
                    cur.execute(
                        f"UPDATE {_SESSIONS_TABLE} SET updated_at = %s WHERE thread_id = %s",
                        (now, thread_id),
                    )
                else:
                    cur.execute(
                        f"INSERT INTO {_SESSIONS_TABLE} (thread_id, project_root, title, created_at, updated_at) "
                        f"VALUES (%s, %s, %s, %s, %s)",
                        (thread_id, project_root, title or "New Chat", now, now),
                    )
        finally:
            conn.close()

    def list_sessions(self) -> list[dict]:
        conn = self._conn()
        try:
            with conn.cursor(pymysql.cursors.DictCursor) as cur:
                cur.execute(
                    f"SELECT thread_id, project_root, title, created_at, updated_at "
                    f"FROM {_SESSIONS_TABLE} ORDER BY updated_at DESC"
                )
                rows = cur.fetchall()
                for row in rows:
                    row["created_at"] = row["created_at"].isoformat()
                    row["updated_at"] = row["updated_at"].isoformat()
                return rows
        finally:
            conn.close()

    def get_session(self, thread_id: str) -> dict | None:
        conn = self._conn()
        try:
            with conn.cursor(pymysql.cursors.DictCursor) as cur:
                cur.execute(
                    f"SELECT thread_id, project_root, title, created_at, updated_at "
                    f"FROM {_SESSIONS_TABLE} WHERE thread_id = %s",
                    (thread_id,),
                )
                row = cur.fetchone()
                if row:
                    row["created_at"] = row["created_at"].isoformat()
                    row["updated_at"] = row["updated_at"].isoformat()
                return row
        finally:
            conn.close()

    def delete_session(self, thread_id: str) -> bool:
        conn = self._conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    f"DELETE FROM {_SESSIONS_TABLE} WHERE thread_id = %s",
                    (thread_id,),
                )
                return cur.rowcount > 0
        finally:
            conn.close()

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
