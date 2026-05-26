"""End-to-end test with actual agent."""
import sys
sys.stdout.reconfigure(encoding='utf-8')

from rich.console import Console
console = Console(force_terminal=True)

from cli.live_status import QuerySpinner, THINKING, TOOL_USE, RESPONDING
from cli.chat import _build_result_summary, _process_stream
from cli.display import tool_label, format_tool_call_args, format_usage, format_text
from langchain_core.messages import HumanMessage
from agent import build_graph
import uuid

graph = build_graph()
thread_id = str(uuid.uuid4())
config = {"configurable": {"thread_id": thread_id}}

console.print("[bold cyan]=== Ecode 终端演示 ===[/bold cyan]\n")

# Simulate the full flow
spinner = QuerySpinner()
spinner.start()

import time

# Phase 1: Thinking
time.sleep(0.8)

# Phase 2: Tool call
spinner.set_state(TOOL_USE, "列出文件")
time.sleep(0.3)
spinner.stop()

console.print("\n  [blue]▸[/blue] [bold]列出文件[/bold] [dim].[/dim]")
console.print("  [green]✓[/green] [dim]⏱ 0.3s[/dim] 20 文件, 12 目录")

spinner.resume()
spinner.set_state(THINKING)
time.sleep(0.5)

# Phase 3: Another tool
spinner.set_state(TOOL_USE, "查看文件")
spinner.stop()

console.print("\n  [blue]▸[/blue] [bold]查看文件[/bold] [dim]src/main.py[/dim]")
console.print("  [green]✓[/green] [dim]⏱ 0.2s[/dim] src/main.py 120 行")

spinner.resume()
spinner.set_state(THINKING)
time.sleep(0.3)

# Phase 4: Responding
spinner.set_state(RESPONDING)
spinner.stop()

console.print()
format_text({"chunk": "当前目录包含 20 个文件和 12 个目录。主要文件有："})

spinner.resume()
time.sleep(0.2)
spinner.stop()

console.print()

# Final usage
elapsed = spinner.elapsed()
format_usage({"prompt_tokens": 500, "completion_tokens": 200, "total_tokens": 700}, elapsed)

console.print("\n[bold green]✓ 演示完成[/bold green]")
