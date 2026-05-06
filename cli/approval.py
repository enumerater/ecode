"""审批详情展示（不再包含交互逻辑，交互由 chat.py 的 confirm 处理）。"""
from rich.console import Console
from rich.panel import Panel

console = Console()


def show_approval_details(data: dict):
    """显示需要审批的工具调用详情。"""
    args = data.get("args", {})
    lines = [f"工具: {data.get('tool_name', '')}"]

    if args.get("path"):
        lines.append(f"路径: {args['path']}")
    if args.get("command"):
        lines.append(f"命令: {args['command']}")
    if args.get("pattern"):
        lines.append(f"模式: {args['pattern']}")
    if args.get("old_string"):
        lines.append(f"替换:\n  - {args['old_string'][:200]}")
        lines.append(f"  + {(args.get('new_string') or '')[:200]}")
    if args.get("content") and not args.get("old_string"):
        preview = args["content"][:500]
        suffix = "\n..." if len(args["content"]) > 500 else ""
        lines.append(f"内容:\n{preview}{suffix}")

    console.print(Panel("\n".join(lines), title="需要审批", style="yellow", expand=False))
