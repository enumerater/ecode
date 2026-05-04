import json
from langchain_core.tools import tool


@tool
def view_file(path: str) -> str:
    """读取并返回文件内容。path 相对于项目根目录。"""
    from tools import get_project_root, resolve_safe_path

    resolved, err = resolve_safe_path(get_project_root(), path)
    if err:
        return json.dumps({"success": False, "error": err}, ensure_ascii=False)
    if not resolved.is_file():
        return json.dumps({"success": False, "error": f"文件不存在: {path}"}, ensure_ascii=False)
    try:
        content = resolved.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)
    lines = content.splitlines()
    numbered = "\n".join(f"{i + 1:4d} | {line}" for i, line in enumerate(lines))
    return json.dumps({
        "success": True,
        "path": str(resolved),
        "content": numbered,
        "total_lines": len(lines),
    }, ensure_ascii=False)


@tool
def edit_file(path: str, content: str) -> str:
    """用新内容替换文件的全部内容。需要用户审批。"""
    from tools import get_project_root, resolve_safe_path

    resolved, err = resolve_safe_path(get_project_root(), path)
    if err:
        return json.dumps({"success": False, "error": err}, ensure_ascii=False)
    if not resolved.is_file():
        return json.dumps({"success": False, "error": f"文件不存在: {path}"}, ensure_ascii=False)
    try:
        resolved.write_text(content, encoding="utf-8")
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)
    return json.dumps({
        "success": True,
        "path": str(resolved),
        "bytes_written": len(content.encode("utf-8")),
    }, ensure_ascii=False)


@tool
def create_file(path: str, content: str) -> str:
    """创建新文件。如果文件已存在则失败。需要用户审批。"""
    from tools import get_project_root, resolve_safe_path

    resolved, err = resolve_safe_path(get_project_root(), path)
    if err:
        return json.dumps({"success": False, "error": err}, ensure_ascii=False)
    if resolved.exists():
        return json.dumps({"success": False, "error": f"文件已存在: {path}"}, ensure_ascii=False)
    try:
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(content, encoding="utf-8")
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)
    return json.dumps({
        "success": True,
        "path": str(resolved),
    }, ensure_ascii=False)
