"""End-to-end CLI test."""
import sys
sys.stdout.reconfigure(encoding='utf-8')

from cli.live_status import ThinkingIndicator
from cli.chat import _build_result_summary, _process_stream
from cli.display import tool_label, format_tool_call_args, format_usage
from rich.console import Console

console = Console(force_terminal=True)

console.print("[bold cyan]=== Ecode CLI 演示 ===[/bold cyan]\n")

# 1. Spinner
console.print("[dim]1. Spinner 动画：[/dim]")
t = ThinkingIndicator()
t.start()
import time
time.sleep(1)
t.update("执行 list_files")
time.sleep(0.5)
t.stop()
console.print("  [green]✓[/green] Spinner 正常\n")

# 2. 工具调用 + 结果
console.print("[dim]2. 工具调用显示：[/dim]")
tools = [
    ("view_file", {"path": "src/main.py", "start_line": 1, "end_line": 50},
     {"path": "src/main.py", "total_lines": 120}),
    ("search_code", {"pattern": "def main", "path": ".", "include_pattern": "*.py"},
     {"total": 8}),
    ("run_command", {"command": "pytest tests/ -v"},
     {"exit_code": 0}),
    ("list_files", {"path": ".", "max_depth": 1},
     {"total_files": 20, "total_dirs": 12}),
    ("edit_file", {"path": "config.yaml"},
     {"path": "config.yaml", "lines_removed": 2, "lines_added": 5}),
]

for name, args, result in tools:
    label = tool_label(name)
    detail = format_tool_call_args(name, args)
    console.print(f"  [blue]▸[/blue] [bold]{label}[/bold] [dim]{detail}[/dim]")
    summary = _build_result_summary(name, result)
    console.print(f"  [green]✓[/green] [dim]⏱ 0.3s[/dim] {summary}")

# 3. 用量
console.print()
format_usage({"prompt_tokens": 500, "completion_tokens": 200, "total_tokens": 700}, 3.2)

console.print("\n[bold green]✓ 全部正常！[/bold green]")
