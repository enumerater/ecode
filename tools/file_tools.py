import json
from langchain_core.tools import tool


@tool
def view_file(path: str, start_line: int = 0, end_line: int = -1) -> str:
    """读取并返回文件内容。path 相对于项目根目录。可选 start_line 和 end_line 指定行范围（从1开始，包含两端）。"""
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
    total = len(lines)

    # 处理行范围
    start = max(1, start_line) if start_line > 0 else 1
    end = min(total, end_line) if end_line > 0 else total
    if start > total:
        start = total
    if end < start:
        end = start

    selected = lines[start - 1:end]
    numbered = "\n".join(f"{i:4d} | {line}" for i, line in enumerate(selected, start))

    return json.dumps({
        "success": True,
        "path": str(resolved),
        "content": numbered,
        "total_lines": total,
        "showing_lines": f"{start}-{end}",
    }, ensure_ascii=False)


@tool
def edit_file(path: str, old_string: str, new_string: str) -> str:
    """局部修改文件：将 old_string 替换为 new_string。

    规则：
    - old_string 必须在文件中存在且唯一（不能有多个匹配）
    - old_string 和 new_string 不能相同
    - 替换后文件编码为 UTF-8
    - 建议在替换前先用 view_file 查看文件内容确认上下文

    需要用户审批。
    """
    from tools import get_project_root, resolve_safe_path

    resolved, err = resolve_safe_path(get_project_root(), path)
    if err:
        return json.dumps({"success": False, "error": err}, ensure_ascii=False)
    if not resolved.is_file():
        return json.dumps({"success": False, "error": f"文件不存在: {path}"}, ensure_ascii=False)

    if old_string == new_string:
        return json.dumps({"success": False, "error": "old_string 和 new_string 不能相同"}, ensure_ascii=False)

    try:
        content = resolved.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)

    count = content.count(old_string)
    if count == 0:
        return json.dumps({
            "success": False,
            "error": "old_string 在文件中未找到，请检查内容是否完全匹配（包括空格和缩进）",
        }, ensure_ascii=False)
    if count > 1:
        return json.dumps({
            "success": False,
            "error": f"old_string 在文件中出现 {count} 次，必须唯一。请提供更多上下文使其唯一匹配",
        }, ensure_ascii=False)

    new_content = content.replace(old_string, new_string, 1)
    try:
        resolved.write_text(new_content, encoding="utf-8")
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)

    # 计算变更行数
    old_lines = old_string.splitlines()
    new_lines = new_string.splitlines()
    return json.dumps({
        "success": True,
        "path": str(resolved),
        "lines_removed": len(old_lines),
        "lines_added": len(new_lines),
    }, ensure_ascii=False)


@tool
def write_file(path: str, content: str) -> str:
    """覆盖写入文件全部内容。文件不存在则创建（自动创建父目录）。需要用户审批。"""
    from tools import get_project_root, resolve_safe_path

    resolved, err = resolve_safe_path(get_project_root(), path)
    if err:
        return json.dumps({"success": False, "error": err}, ensure_ascii=False)
    try:
        resolved.parent.mkdir(parents=True, exist_ok=True)
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
    """创建新文件并写入内容。如果文件已存在则失败。自动创建父目录。需要用户审批。"""
    from tools import get_project_root, resolve_safe_path

    resolved, err = resolve_safe_path(get_project_root(), path)
    if err:
        return json.dumps({"success": False, "error": err}, ensure_ascii=False)
    if resolved.exists():
        return json.dumps({"success": False, "error": f"文件已存在: {path}，请使用 edit_file 或 write_file 修改"}, ensure_ascii=False)
    try:
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(content, encoding="utf-8")
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)
    return json.dumps({
        "success": True,
        "path": str(resolved),
    }, ensure_ascii=False)


@tool
def create_directory(path: str) -> str:
    """创建目录（递归创建，类似 mkdir -p）。需要用户审批。"""
    from tools import get_project_root, resolve_safe_path

    resolved, err = resolve_safe_path(get_project_root(), path)
    if err:
        return json.dumps({"success": False, "error": err}, ensure_ascii=False)
    if resolved.is_file():
        return json.dumps({"success": False, "error": f"同名文件已存在: {path}"}, ensure_ascii=False)
    try:
        resolved.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)
    return json.dumps({
        "success": True,
        "path": str(resolved),
    }, ensure_ascii=False)
