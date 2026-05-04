import json
import re
from pathlib import Path
from langchain_core.tools import tool

MAX_MATCHES = 50
MAX_FILES = 200


@tool
def search_code(pattern: str, path: str = ".") -> str:
    """在项目文件中搜索正则表达式。返回匹配的行。"""
    from tools import get_project_root, resolve_safe_path

    resolved, err = resolve_safe_path(get_project_root(), path)
    if err:
        return json.dumps({"success": False, "error": err}, ensure_ascii=False)
    if not resolved.exists():
        return json.dumps({"success": False, "error": f"路径不存在: {path}"}, ensure_ascii=False)

    try:
        regex = re.compile(pattern)
    except re.error as e:
        return json.dumps({"success": False, "error": f"无效正则: {e}"}, ensure_ascii=False)

    skip_dirs = {".git", "node_modules", "__pycache__", ".venv", "venv", ".idea", ".vscode"}
    matches = []
    root = Path(get_project_root()).resolve()

    def walk(p: Path):
        if len(matches) >= MAX_MATCHES:
            return
        try:
            entries = sorted(p.iterdir())
        except PermissionError:
            return
        for entry in entries:
            if entry.is_dir():
                if entry.name not in skip_dirs:
                    walk(entry)
            elif entry.is_file() and entry.suffix in (
                ".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".go",
                ".rs", ".c", ".cpp", ".h", ".css", ".html", ".json",
                ".yaml", ".yml", ".toml", ".md", ".txt", ".sql", ".sh",
                ".vue", ".svelte", ".xml", ".ini", ".cfg", ".env",
            ):
                try:
                    text = entry.read_text(encoding="utf-8", errors="replace")
                    for i, line in enumerate(text.splitlines(), 1):
                        if regex.search(line):
                            rel = str(entry.relative_to(root))
                            matches.append(f"{rel}:{i}: {line.strip()}")
                            if len(matches) >= MAX_MATCHES:
                                return
                except (PermissionError, OSError):
                    continue

    walk(resolved if resolved.is_dir() else resolved.parent)

    return json.dumps({
        "success": True,
        "pattern": pattern,
        "matches": matches,
        "total": len(matches),
        "truncated": len(matches) >= MAX_MATCHES,
    }, ensure_ascii=False)


@tool
def list_files(path: str = ".", pattern: str = "*") -> str:
    """列出目录中的文件，支持 glob 模式过滤。"""
    from tools import get_project_root, resolve_safe_path

    resolved, err = resolve_safe_path(get_project_root(), path)
    if err:
        return json.dumps({"success": False, "error": err}, ensure_ascii=False)
    if not resolved.is_dir():
        return json.dumps({"success": False, "error": f"不是目录: {path}"}, ensure_ascii=False)

    skip_dirs = {".git", "node_modules", "__pycache__", ".venv", "venv"}
    files = []
    for f in resolved.rglob(pattern):
        if any(part in skip_dirs for part in f.parts):
            continue
        if f.is_file():
            files.append(str(f.relative_to(resolved)))
            if len(files) >= MAX_FILES:
                break

    return json.dumps({
        "success": True,
        "path": str(resolved),
        "files": sorted(files),
        "total": len(files),
        "truncated": len(files) >= MAX_FILES,
    }, ensure_ascii=False)
