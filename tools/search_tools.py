import json
import re
from pathlib import Path
from langchain_core.tools import tool

MAX_MATCHES = 50
MAX_FILES = 100

# 可搜索的文件扩展名
SEARCHABLE_EXTENSIONS = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".go",
    ".rs", ".c", ".cpp", ".h", ".hpp", ".css", ".html",
    ".json", ".yaml", ".yml", ".toml", ".md", ".txt",
    ".sql", ".sh", ".bash", ".zsh", ".vue", ".svelte",
    ".xml", ".ini", ".cfg", ".env", ".conf", ".mdx",
    ".scss", ".less", ".vue", ".astro", ".rb", ".php",
}


@tool
def search_code(pattern: str, path: str = ".", include_pattern: str = "") -> str:
    """在项目文件中搜索正则表达式。返回匹配的行及其上下文。

    Args:
        pattern: 正则表达式
        path: 搜索起始路径（相对于项目根目录）
        include_pattern: 可选，glob 模式过滤文件（如 "*.py"）
    """
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

    skip_dirs = {".git", "node_modules", "__pycache__", ".venv", "venv", ".idea", ".vscode", "dist", "build"}
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
            if len(matches) >= MAX_MATCHES:
                return
            if entry.is_dir():
                if entry.name not in skip_dirs:
                    walk(entry)
            elif entry.is_file():
                # 应用 include_pattern 过滤
                if include_pattern and not entry.match(include_pattern):
                    continue
                if not include_pattern and entry.suffix not in SEARCHABLE_EXTENSIONS:
                    continue
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
def list_files(path: str = ".", pattern: str = "*", max_depth: int = 2) -> str:
    """列出目录中的文件和子目录，支持 glob 模式过滤。

    Args:
        path: 目录路径（相对于项目根目录）
        pattern: glob 模式（如 "*.py", "src/**"）
        max_depth: 最大递归深度，默认 3
    """
    from tools import get_project_root, resolve_safe_path

    resolved, err = resolve_safe_path(get_project_root(), path)
    if err:
        return json.dumps({"success": False, "error": err}, ensure_ascii=False)
    if not resolved.is_dir():
        return json.dumps({"success": False, "error": f"不是目录: {path}"}, ensure_ascii=False)

    skip_dirs = {".git", "node_modules", "__pycache__", ".venv", "venv", ".idea", ".vscode", "dist", "build"}
    files = []
    dirs = []

    def walk(p: Path, depth: int = 0):
        if depth >= max_depth or len(files) >= MAX_FILES:
            return
        try:
            entries = sorted(p.iterdir())
        except PermissionError:
            return
        for entry in entries:
            if len(files) >= MAX_FILES:
                return
            if entry.is_dir():
                if entry.name not in skip_dirs:
                    rel = str(entry.relative_to(resolved))
                    dirs.append(rel + "/")
                    walk(entry, depth + 1)
            elif entry.is_file():
                if pattern == "*" or entry.match(pattern):
                    files.append(str(entry.relative_to(resolved)))

    walk(resolved)

    return json.dumps({
        "success": True,
        "path": str(resolved),
        "directories": sorted(dirs),
        "files": sorted(files),
        "total_dirs": len(dirs),
        "total_files": len(files),
        "truncated": len(files) >= MAX_FILES,
    }, ensure_ascii=False)
