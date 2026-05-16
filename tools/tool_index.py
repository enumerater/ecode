"""工具索引：构建紧凑摘要表 + 按需获取完整文档。"""

from langchain_core.tools import BaseTool, tool


def build_tool_index(
    tools: list[BaseTool],
    safe_tools: set[str],
    dangerous_tools: set[str],
    tool_meta: dict[str, dict] = None,
) -> str:
    """生成工具摘要 markdown 表格，用于 system prompt。"""
    lines = ["| Tool | Description | Type | Concurrency |", "|------|-------------|------|-------------|"]
    for t in tools:
        doc = (t.description or "").strip()
        first_line = doc.split("\n")[0].strip()
        if len(first_line) > 60:
            first_line = first_line[:57] + "..."
        if t.name in safe_tools:
            tool_type = "safe"
        elif t.name in dangerous_tools:
            tool_type = "dangerous"
        else:
            tool_type = "meta"
        # 并发信息
        if tool_meta and t.name in tool_meta:
            meta = tool_meta[t.name]
            concurrency = "parallel" if meta.get("is_concurrency_safe") else "serial"
        else:
            concurrency = "serial"
        lines.append(f"| {t.name} | {first_line} | {tool_type} | {concurrency} |")
    return "\n".join(lines)


def get_tool_full_doc(tool_obj: BaseTool) -> str:
    """提取工具的完整文档 + 参数 schema。"""
    parts = [f"## {tool_obj.name}", tool_obj.description or "(no description)"]

    try:
        schema = (
            tool_obj.args_schema.model_json_schema()
            if hasattr(tool_obj, "args_schema") and tool_obj.args_schema
            else {}
        )
        properties = schema.get("properties", {})
        required = schema.get("required", [])
        if properties:
            parts.append("\n### Arguments")
            for param_name, param_info in properties.items():
                req = " (required)" if param_name in required else " (optional)"
                ptype = param_info.get("type", "any")
                desc = param_info.get("description", "")
                default = param_info.get("default", None)
                line = f"- `{param_name}` ({ptype}){req}"
                if default is not None:
                    line += f" = {default}"
                if desc:
                    line += f": {desc}"
                parts.append(line)
    except Exception:
        pass

    return "\n".join(parts)


@tool
def get_tool_details(tool_name: str) -> str:
    """获取某个工具的完整文档（参数、用法、示例）。

    当你不确定某个工具的参数或用法时调用此工具。

    Args:
        tool_name: 工具名称，如 "view_file", "edit_file"
    """
    from tools import ALL_TOOLS

    tool_map = {t.name: t for t in ALL_TOOLS}
    if tool_name not in tool_map:
        available = ", ".join(tool_map.keys())
        return f"未知工具: {tool_name}。可用工具: {available}"
    return get_tool_full_doc(tool_map[tool_name])
