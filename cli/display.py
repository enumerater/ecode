import json
import threading
import time
import sys
from datetime import datetime, timezone
from rich.console import Console
from rich.panel import Panel

console = Console()


class TimerDisplay:
    """实时计时器，在 stderr 上显示，不影响 stdout 的 rich 输出。"""

    def __init__(self):
        self._start = 0.0
        self._stop_event = threading.Event()
        self._thread = None

    def start(self):
        self._start = time.time()
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._tick, daemon=True)
        self._thread.start()

    def _tick(self):
        while not self._stop_event.is_set():
            elapsed = time.time() - self._start
            sys.stderr.write(f"\r⏱ {elapsed:.1f}s")
            sys.stderr.flush()
            time.sleep(0.2)
        # 清除计时行
        sys.stderr.write("\r" + " " * 20 + "\r")
        sys.stderr.flush()

    def stop(self):
        if self._thread:
            self._stop_event.set()
            self._thread.join(timeout=1)
        elapsed = time.time() - self._start
        return elapsed

TOOL_LABELS = {
    "view_file": "查看文件",
    "edit_file": "编辑文件",
    "write_file": "写入文件",
    "create_file": "创建文件",
    "create_directory": "创建目录",
    "search_code": "搜索代码",
    "list_files": "列出文件",
    "run_command": "执行命令",
}

# tool_call_id -> tool_name 映射
_tool_call_map = {}


def tool_label(name):
    return TOOL_LABELS.get(name, name)


def format_tool_call_args(tool_name, args):
    if not args:
        return ""
    if tool_name == "view_file":
        s = args.get("path", "")
        if args.get("start_line"):
            s += f" (行 {args['start_line']}-{args.get('end_line', '末尾')})"
        return s
    if tool_name in ("edit_file", "write_file", "create_file", "create_directory"):
        return args.get("path", "")
    if tool_name == "search_code":
        s = f'"{args.get("pattern", "")}" in {args.get("path", ".")}'
        if args.get("include_pattern"):
            s += f" [{args['include_pattern']}]"
        return s
    if tool_name == "list_files":
        s = args.get("path", ".")
        if args.get("max_depth"):
            s += f" (深度 {args['max_depth']})"
        return s
    if tool_name == "run_command":
        return args.get("command", "")
    return ""


def format_result_detail(tool_name, data):
    label = tool_label(tool_name)
    if not data or not isinstance(data, dict):
        console.print(f"  [green]✓ {label} 完成[/green]")
        return

    success = data.get("success", True)
    error = data.get("error") or data.get("message", "")

    if not success:
        console.print(f"  [red]✗ {label} 失败: {error or '未知错误'}[/red]")
        return

    if tool_name == "view_file":
        path = data.get("path", "")
        content = data.get("content", "")
        total = data.get("total_lines", 0)
        showing = data.get("showing_lines", "")
        path_str = f" [dim]{path}[/dim]" if path else ""
        if not content:
            console.print(f"  [green]✓ {label}[/green]{path_str} [dim](空文件)[/dim]")
            return
        lines = content.split("\n")
        preview = "\n".join(lines[:8])
        range_str = f" 行 {showing}" if showing else ""
        suffix = f"\n  [dim]... 共 {total} 行[/dim]" if len(lines) > 8 else ""
        console.print(f"  [green]✓ {label}[/green]{path_str}[dim]{range_str}[/dim]\n  [dim]{preview}[/dim]{suffix}")

    elif tool_name == "edit_file":
        path = data.get("path", "")
        removed = data.get("lines_removed", 0)
        added = data.get("lines_added", 0)
        path_str = f" [dim]{path}[/dim]" if path else ""
        console.print(f"  [green]✓ {label}[/green]{path_str} [dim](-{removed} +{added} 行)[/dim]")

    elif tool_name in ("write_file", "create_file"):
        path = data.get("path", "")
        size = data.get("bytes_written") or data.get("bytes") or data.get("size") or 0
        path_str = f" [dim]{path}[/dim]" if path else ""
        size_str = f" [dim]({size} bytes)[/dim]" if size else ""
        console.print(f"  [green]✓ {label}[/green]{path_str}{size_str}")

    elif tool_name == "create_directory":
        path = data.get("path", "")
        path_str = f" [dim]{path}[/dim]" if path else ""
        console.print(f"  [green]✓ {label}[/green]{path_str}")

    elif tool_name == "search_code":
        results = data.get("results") or data.get("matches", [])
        count = data.get("count") or len(results)
        if not results and not count:
            console.print(f"  [dim]✓ {label} 无匹配结果[/dim]")
            return
        if results:
            preview_lines = []
            for r in results[:5]:
                if isinstance(r, str):
                    preview_lines.append(r)
                else:
                    preview_lines.append(f'{r.get("file", "")}:{r.get("line", "")}  {(r.get("content") or r.get("text", "")).strip()}')
            preview = "\n".join(preview_lines)
            suffix = f"\n  [dim]... 共 {count} 处匹配[/dim]" if count > 5 else ""
            console.print(f"  [green]✓ {label} {count} 处匹配[/green]\n  [dim]{preview}[/dim]{suffix}")
        else:
            console.print(f"  [green]✓ {label} {count} 处匹配[/green]")

    elif tool_name == "list_files":
        dirs = data.get("directories", [])
        files = data.get("files", [])
        all_items = dirs + files
        total = data.get("total") or len(all_items)
        if not all_items:
            console.print(f"  [dim]✓ {label} 空目录[/dim]")
            return
        preview = "\n".join(all_items[:15])
        suffix = f"\n  [dim]... 共 {total} 项[/dim]" if total > 15 else ""
        console.print(f"  [dim]{preview}[/dim]{suffix}")

    elif tool_name == "run_command":
        exit_code = data.get("exit_code", data.get("exitCode"))
        exit_str = ""
        if exit_code is not None:
            if exit_code == 0:
                exit_str = " [green]✓ exit 0[/green]"
            else:
                exit_str = f" [red]✗ exit {exit_code}[/red]"
        output = data.get("output") or data.get("stdout", "")
        if not output:
            console.print(f"  [dim](无输出)[/dim]{exit_str}")
            return
        lines = output.split("\n")
        preview = "\n".join(lines[-10:])
        prefix = f"  [dim]... 省略 {len(lines) - 10} 行[/dim]\n" if len(lines) > 10 else ""
        console.print(f"{prefix}  [dim]{preview}[/dim]{exit_str}")

    else:
        # 通用兜底：提取关键字段展示
        path = data.get("path", "")
        msg = data.get("message", "")
        summary = data.get("summary", "")
        detail = path or msg or summary or ""
        detail_str = f" [dim]{detail[:120]}[/dim]" if detail else ""
        console.print(f"  [green]✓ {label}[/green]{detail_str}")


# --- Public API ---


def show_banner():
    console.clear()
    console.print(Panel("[black] ecode-cli 代码智能体 [/black]", style="cyan", expand=False))
    console.print()


def show_session_info(thread_id, project_root):
    console.print(f"[dim]会话: {thread_id[:8]}  项目: {project_root}[/dim]")
    console.print("[dim]输入 /help 查看可用命令[/dim]\n")


def show_help():
    cmds = [
        ("/help", "显示此帮助"),
        ("/sessions", "列出所有会话"),
        ("/switch", "切换会话"),
        ("/new", "新建会话"),
        ("/delete", "删除会话"),
        ("/history", "查看当前会话历史"),
        ("/clear", "清屏"),
        ("/exit", "退出"),
    ]
    lines = [f"  [cyan]{cmd.ljust(12)}[/cyan] {desc}" for cmd, desc in cmds]
    console.print(Panel("\n".join(lines), title="可用命令", expand=False))


def format_text(data):
    chunk = data.get("chunk", "")
    if chunk:
        console.print(str(chunk), end="", highlight=False)


def format_tool_call(data):
    tool_name = data.get("tool_name", "")
    tool_call_id = data.get("tool_call_id")
    if tool_call_id:
        _tool_call_map[tool_call_id] = tool_name
    label = tool_label(tool_name)
    detail = format_tool_call_args(tool_name, data.get("args"))
    detail_str = f" [dim]{detail}[/dim]" if detail else ""
    console.print(f"\n[blue]> {label}[/blue]{detail_str}[blue] ...[/blue]")


def format_tool_result(data):
    tool_call_id = data.get("tool_call_id")
    tool_name = _tool_call_map.pop(tool_call_id, "") if tool_call_id else ""
    if not tool_name:
        tool_name = data.get("_tool_name", "")

    result = data.get("result")
    if isinstance(result, str):
        try:
            parsed = json.loads(result)
        except (ValueError, TypeError):
            console.print(f"  [dim]{result[:300]}[/dim]")
            return
    elif isinstance(result, dict):
        parsed = result
    elif result is not None:
        console.print(f"  [dim]{str(result)[:300]}[/dim]")
        return
    else:
        parsed = data

    format_result_detail(tool_name, parsed)


def format_usage(data, elapsed=None):
    prompt = data.get("prompt_tokens", 0)
    completion = data.get("completion_tokens", 0)
    total = data.get("total_tokens", prompt + completion)
    elapsed_str = f" ⏱ {elapsed:.1f}s" if elapsed is not None else ""
    console.print(f"\n  [dim]⤷ 消耗: {total} tokens (输入 {prompt} + 输出 {completion}){elapsed_str}[/dim]")


def format_error(data):
    console.print(f"\n[red]错误: {data.get('message', '')}[/red]")


def format_time(date_str):
    if not date_str:
        return ""
    try:
        dt = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
        diff = datetime.now(timezone.utc) - dt
        mins = int(diff.total_seconds() / 60)
        if mins < 1:
            return "刚刚"
        if mins < 60:
            return f"{mins} 分钟前"
        hours = mins // 60
        if hours < 24:
            return f"{hours} 小时前"
        return f"{hours // 24} 天前"
    except Exception:
        return ""
