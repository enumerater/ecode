from pathlib import Path

from tools.file_tools import view_file, edit_file, create_file
from tools.search_tools import search_code, list_files
from tools.command_tools import run_command

SAFE_TOOLS = {"view_file", "search_code", "list_files"}
DANGEROUS_TOOLS = {"edit_file", "create_file", "run_command"}
ALL_TOOLS = [view_file, edit_file, create_file, search_code, list_files, run_command]

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
