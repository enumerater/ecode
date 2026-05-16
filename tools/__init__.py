from pathlib import Path

from tools.file_tools import view_file, edit_file, write_file, create_file, create_directory
from tools.search_tools import search_code, list_files
from tools.command_tools import run_command
from tools.context_tools import compact
from tools.tool_index import get_tool_details
from tools.git_tools import git_status, git_diff, git_log, git_commit, git_blame
from tools.memory_tools import save_memory, list_memories
from tools.plan_tools import enter_plan_mode, exit_plan_mode
from tools.agent_tool import run_agent
from tools.task_tools import create_background_task, get_task_status, list_background_tasks, kill_background_task

# ── 工具分类集合（向后兼容）──
SAFE_TOOLS = {"view_file", "search_code", "list_files", "compact", "get_tool_details", "git_status", "git_diff", "git_log", "git_blame", "save_memory", "list_memories", "get_task_status", "list_background_tasks"}
DANGEROUS_TOOLS = {"edit_file", "write_file", "create_file", "create_directory", "run_command", "git_commit", "enter_plan_mode", "exit_plan_mode", "run_agent", "create_background_task", "kill_background_task"}
ALL_TOOLS = [view_file, edit_file, write_file, create_file, create_directory, search_code, list_files, run_command, compact, get_tool_details, git_status, git_diff, git_log, git_commit, git_blame, save_memory, list_memories, enter_plan_mode, exit_plan_mode, run_agent, create_background_task, get_task_status, list_background_tasks, kill_background_task]

# ── 工具并发元数据 ──
# is_concurrency_safe: 是否可以与其他工具并发执行（只读、无副作用）
# is_read_only: 是否只读
# is_destructive: 是否具有破坏性（需要审批）
TOOL_META: dict[str, dict] = {
    "view_file":       {"is_concurrency_safe": True,  "is_read_only": True,  "is_destructive": False},
    "search_code":     {"is_concurrency_safe": True,  "is_read_only": True,  "is_destructive": False},
    "list_files":      {"is_concurrency_safe": True,  "is_read_only": True,  "is_destructive": False},
    "compact":         {"is_concurrency_safe": False, "is_read_only": True,  "is_destructive": False},
    "get_tool_details": {"is_concurrency_safe": True, "is_read_only": True,  "is_destructive": False},
    "edit_file":       {"is_concurrency_safe": False, "is_read_only": False, "is_destructive": True},
    "write_file":      {"is_concurrency_safe": False, "is_read_only": False, "is_destructive": True},
    "create_file":     {"is_concurrency_safe": False, "is_read_only": False, "is_destructive": True},
    "create_directory": {"is_concurrency_safe": False, "is_read_only": False, "is_destructive": True},
    "run_command":     {"is_concurrency_safe": False, "is_read_only": False, "is_destructive": True},
    # Git 工具
    "git_status":      {"is_concurrency_safe": True,  "is_read_only": True,  "is_destructive": False},
    "git_diff":        {"is_concurrency_safe": True,  "is_read_only": True,  "is_destructive": False},
    "git_log":         {"is_concurrency_safe": True,  "is_read_only": True,  "is_destructive": False},
    "git_commit":      {"is_concurrency_safe": False, "is_read_only": False, "is_destructive": True},
    "git_blame":       {"is_concurrency_safe": True,  "is_read_only": True,  "is_destructive": False},
    # 记忆工具
    "save_memory":     {"is_concurrency_safe": False, "is_read_only": False, "is_destructive": False},
    "list_memories":   {"is_concurrency_safe": True,  "is_read_only": True,  "is_destructive": False},
    # Plan 模式工具
    "enter_plan_mode": {"is_concurrency_safe": False, "is_read_only": False, "is_destructive": True},
    "exit_plan_mode":  {"is_concurrency_safe": False, "is_read_only": False, "is_destructive": True},
    # 子 Agent 工具
    "run_agent":       {"is_concurrency_safe": False, "is_read_only": True,  "is_destructive": True},
    # 后台任务工具
    "create_background_task": {"is_concurrency_safe": False, "is_read_only": False, "is_destructive": True},
    "get_task_status":       {"is_concurrency_safe": True,  "is_read_only": True,  "is_destructive": False},
    "list_background_tasks": {"is_concurrency_safe": True,  "is_read_only": True,  "is_destructive": False},
    "kill_background_task":  {"is_concurrency_safe": False, "is_read_only": False, "is_destructive": True},
}


def get_tool_meta(tool_name: str) -> dict:
    """获取工具的并发元数据，未知工具返回保守默认值。"""
    return TOOL_META.get(tool_name, {
        "is_concurrency_safe": False,
        "is_read_only": False,
        "is_destructive": True,
    })


_project_root: str = "."


def set_project_root(root: str):
    global _project_root
    _project_root = root


def get_project_root() -> str:
    return _project_root


def resolve_safe_path(project_root: str, path: str) -> tuple[Path, str | None]:
    root = Path(project_root).resolve()
    target = (root / path).resolve()
    if not str(target).startswith(str(root)):
        return target, f"Path '{path}' escapes project root"
    return target, None
