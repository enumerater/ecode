"""审批详情展示：更丰富的工具调用详情。"""

import json
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

console = Console(force_terminal=True)


def show_approval_details(data: dict):
    """显示需要审批的工具调用详情。"""
    tool_name = data.get("tool_name", "")
    args = data.get("args", {})

    # 根据工具类型显示不同的详情
    if tool_name == "edit_file":
        _show_edit_details(args)
    elif tool_name == "write_file":
        _show_write_details(args)
    elif tool_name == "create_file":
        _show_create_details(args)
    elif tool_name == "run_command":
        _show_command_details(args)
    elif tool_name == "git_commit":
        _show_git_commit_details(args)
    elif tool_name == "create_background_task":
        _show_task_details(args)
    else:
        _show_generic_details(tool_name, args)


def _show_edit_details(args: dict):
    """显示编辑文件详情。"""
    path = args.get("path", "")
    old_string = args.get("old_string", "")
    new_string = args.get("new_string", "")

    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_column("Key", style="dim")
    table.add_column("Value")

    table.add_row("工具", "[bold]编辑文件[/bold]")
    table.add_row("路径", f"[cyan]{path}[/cyan]")

    console.print(Panel(table, title="[yellow]需要审批[/yellow]", expand=False))

    # 显示 diff 风格的变更
    if old_string or new_string:
        console.print("\n  [dim]变更内容:[/dim]")
        for line in old_string.split("\n"):
            if line.strip():
                console.print(f"  [red]- {line}[/red]")
        for line in new_string.split("\n"):
            if line.strip():
                console.print(f"  [green]+ {line}[/green]")


def _show_write_details(args: dict):
    """显示写入文件详情。"""
    path = args.get("path", "")
    content = args.get("content", "")

    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_column("Key", style="dim")
    table.add_column("Value")

    table.add_row("工具", "[bold]写入文件[/bold]")
    table.add_row("路径", f"[cyan]{path}[/cyan]")
    table.add_row("大小", f"{len(content)} 字符")

    console.print(Panel(table, title="[yellow]需要审批[/yellow]", expand=False))

    # 显示内容预览
    if content:
        preview = content[:500]
        suffix = "\n..." if len(content) > 500 else ""
        console.print(f"\n  [dim]内容预览:[/dim]\n{preview}{suffix}")


def _show_create_details(args: dict):
    """显示创建文件详情。"""
    path = args.get("path", "")
    content = args.get("content", "")

    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_column("Key", style="dim")
    table.add_column("Value")

    table.add_row("工具", "[bold]创建文件[/bold]")
    table.add_row("路径", f"[cyan]{path}[/cyan]")
    table.add_row("大小", f"{len(content)} 字符")

    console.print(Panel(table, title="[yellow]需要审批[/yellow]", expand=False))

    if content:
        preview = content[:500]
        suffix = "\n..." if len(content) > 500 else ""
        console.print(f"\n  [dim]内容预览:[/dim]\n{preview}{suffix}")


def _show_command_details(args: dict):
    """显示执行命令详情。"""
    command = args.get("command", "")
    timeout = args.get("timeout", 60)

    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_column("Key", style="dim")
    table.add_column("Value")

    table.add_row("工具", "[bold]执行命令[/bold]")
    table.add_row("命令", f"[yellow]{command}[/yellow]")
    table.add_row("超时", f"{timeout}s")

    console.print(Panel(table, title="[yellow]需要审批[/yellow]", expand=False))


def _show_git_commit_details(args: dict):
    """显示 Git 提交详情。"""
    message = args.get("message", "")

    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_column("Key", style="dim")
    table.add_column("Value")

    table.add_row("工具", "[bold]Git 提交[/bold]")
    table.add_row("提交信息", f"[green]{message}[/green]")

    console.print(Panel(table, title="[yellow]需要审批[/yellow]", expand=False))


def _show_task_details(args: dict):
    """显示后台任务详情。"""
    description = args.get("description", "")
    command = args.get("command", "")

    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_column("Key", style="dim")
    table.add_column("Value")

    table.add_row("工具", "[bold]创建后台任务[/bold]")
    table.add_row("描述", description)
    table.add_row("命令", f"[yellow]{command}[/yellow]")

    console.print(Panel(table, title="[yellow]需要审批[/yellow]", expand=False))


def _show_generic_details(tool_name: str, args: dict):
    """显示通用详情。"""
    table = Table(show_header=False, box=None, padding=(0, 1))
    table.add_column("Key", style="dim")
    table.add_column("Value")

    table.add_row("工具", f"[bold]{tool_name}[/bold]")

    for key, value in args.items():
        if isinstance(value, str) and len(value) > 100:
            value = value[:100] + "..."
        table.add_row(key, str(value))

    console.print(Panel(table, title="[yellow]需要审批[/yellow]", expand=False))
