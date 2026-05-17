"""会话管理：支持 MySQL 和内存两种持久化后端，可运行时动态切换。"""

import os
import logging
from datetime import datetime
from abc import ABC, abstractmethod

import yaml
from langgraph.checkpoint.memory import MemorySaver

logger = logging.getLogger(__name__)

# ── 数据库配置加载 ────────────────────────────────────────────────────────


def _load_db_config() -> dict:
    """从 config.yaml 读取 database 配置，文件不存在返回空字典。"""
    config_path = os.path.join(os.getcwd(), "config.yaml")
    if not os.path.exists(config_path):
        return {}
    with open(config_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    return raw.get("database", {})


def _get_pymysql_conn(cfg: dict):
    """创建一个 pymysql 原生连接（用于 SessionManager）。"""
    import pymysql

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


# ── SessionManager 抽象基类 ──────────────────────────────────────────────


class BaseSessionManager(ABC):
    @abstractmethod
    def create_or_update(self, thread_id: str, project_root: str, title: str = ""):
        ...

    @abstractmethod
    def list_sessions(self) -> list[dict]:
        ...

    @abstractmethod
    def get_session(self, thread_id: str) -> dict | None:
        ...

    @abstractmethod
    def delete_session(self, thread_id: str) -> bool:
        ...

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


# ── 内存 SessionManager ──────────────────────────────────────────────────


class MemorySessionManager(BaseSessionManager):
    """基于内存的会话管理（进程内，重启丢失）。"""

    def __init__(self):
        self._sessions: dict[str, dict] = {}

    def create_or_update(self, thread_id: str, project_root: str, title: str = ""):
        now = datetime.now().isoformat()
        if thread_id in self._sessions:
            self._sessions[thread_id]["updated_at"] = now
        else:
            self._sessions[thread_id] = {
                "thread_id": thread_id,
                "project_root": project_root,
                "title": title or "New Chat",
                "created_at": now,
                "updated_at": now,
            }

    def list_sessions(self) -> list[dict]:
        return sorted(
            self._sessions.values(),
            key=lambda s: s["updated_at"],
            reverse=True,
        )

    def get_session(self, thread_id: str) -> dict | None:
        return self._sessions.get(thread_id)

    def delete_session(self, thread_id: str) -> bool:
        return self._sessions.pop(thread_id, None) is not None


# ── MySQL SessionManager ─────────────────────────────────────────────────

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


class MySQLSessionManager(BaseSessionManager):
    """基于 MySQL 的会话管理。"""

    def __init__(self, db_cfg: dict):
        self._db_cfg = db_cfg
        self._ensure_table()

    def _ensure_table(self):
        conn = _get_pymysql_conn(self._db_cfg)
        try:
            with conn.cursor() as cur:
                cur.execute(_CREATE_SESSIONS_TABLE)
        finally:
            conn.close()

    def _conn(self):
        return _get_pymysql_conn(self._db_cfg)

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
        import pymysql

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
        import pymysql

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


# ── 存储后端管理 ──────────────────────────────────────────────────────────

SUPPORTED_BACKENDS = ("memory", "mysql")


class StorageState:
    """管理当前存储后端的状态容器。"""

    def __init__(self):
        self.backend: str = "memory"
        self.checkpointer = None
        self.session_manager: BaseSessionManager | None = None
        self._mysql_cp_conn = None  # MySQL checkpointer 的持久连接
        self._init_memory()

    def _init_memory(self):
        self.checkpointer = MemorySaver()
        self.session_manager = MemorySessionManager()
        logger.info("已初始化内存存储后端")

    def _init_mysql(self):
        import pymysql
        from langgraph.checkpoint.mysql.pymysql import PyMySQLSaver

        db_cfg = _load_db_config()
        if not db_cfg:
            raise ValueError("未找到数据库配置。请在 config.yaml 中配置 database 部分（参考 config.yaml.example）")
        self._mysql_cp_conn = _get_pymysql_conn(db_cfg)
        self.checkpointer = PyMySQLSaver(self._mysql_cp_conn)
        self.checkpointer.setup()
        self.session_manager = MySQLSessionManager(db_cfg)
        logger.info("已初始化 MySQL 存储后端")

    def _cleanup_mysql(self):
        if self._mysql_cp_conn:
            try:
                self._mysql_cp_conn.close()
            except Exception:
                pass
            self._mysql_cp_conn = None

    def switch_to(self, backend: str) -> str:
        """切换到指定后端，返回实际使用的后端名称。"""
        if backend not in SUPPORTED_BACKENDS:
            raise ValueError(f"不支持的后端: {backend}，可选: {SUPPORTED_BACKENDS}")

        if backend == self.backend:
            return self.backend

        # 清理旧后端
        if self.backend == "mysql":
            self._cleanup_mysql()

        # 初始化新后端
        if backend == "mysql":
            try:
                self._init_mysql()
            except Exception as e:
                # MySQL 连接失败，回退到内存
                logger.warning(f"MySQL 连接失败，回退到内存后端: {e}")
                self._init_memory()
                self.backend = "memory"
                raise ConnectionError(f"MySQL 连接失败: {e}，已回退到内存后端")
        else:
            self._init_memory()

        self.backend = backend
        return self.backend


_storage = StorageState()


def get_checkpointer():
    """获取当前 checkpointer（动态，切换后端后自动更新）。"""
    return _storage.checkpointer


def get_session_manager() -> BaseSessionManager:
    """获取当前 session_manager（动态，切换后端后自动更新）。"""
    return _storage.session_manager


def get_storage_backend() -> str:
    """获取当前存储后端名称。"""
    return _storage.backend


def switch_storage(backend: str) -> str:
    """切换存储后端，返回实际使用的后端名称。"""
    return _storage.switch_to(backend)


# ── 兼容旧导入 ────────────────────────────────────────────────────────────
# 旧代码直接 from session import checkpointer, session_manager
# 通过模块属性代理到 _storage，保证兼容
# 但 agent.py / chat.py 需要改用 get_checkpointer() / get_session_manager()


def __getattr__(name):
    if name == "checkpointer":
        return _storage.checkpointer
    if name == "session_manager":
        return _storage.session_manager
    raise AttributeError(f"module 'session' has no attribute {name!r}")
