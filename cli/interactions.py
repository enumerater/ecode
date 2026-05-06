"""prompt_toolkit 交互组件：带历史的输入、单选、多选、确认、多行输入。"""
import os
import sys
from prompt_toolkit import PromptSession
from prompt_toolkit.history import FileHistory
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.styles import Style

HISTORY_FILE = os.path.join(os.path.expanduser("~"), ".ecode_history")

_style = Style.from_dict({
    "prompt": "cyan",
})

# Lazy singleton prompt session
_session = None


def _get_session():
    global _session
    if _session is None:
        _session = PromptSession(history=FileHistory(HISTORY_FILE))
    return _session


def prompt_input(message=">"):
    """带历史记录的单行输入。上/下箭头翻历史，Ctrl+R 搜索历史。"""
    try:
        session = _get_session()
        return session.prompt(HTML(f"<prompt>{message} </prompt>"), style=_style)
    except (EOFError, KeyboardInterrupt):
        return None
    except Exception:
        # Fallback for terminals that don't support prompt_toolkit
        try:
            sys.stdout.write(f"{message} ")
            sys.stdout.flush()
            return input()
        except (EOFError, KeyboardInterrupt):
            return None


def select_one(options, message="选择："):
    """单选菜单。上下箭头移动，Enter 确认，Esc/Ctrl+C 取消。

    options: [{"value": str, "label": str}, ...]
    Returns: 选中的 value，或 None（取消）
    """
    if not options:
        return None

    import msvcrt

    idx = 0
    rendered_lines = 0

    def _render():
        nonlocal rendered_lines
        for _ in range(rendered_lines):
            sys.stdout.write("\033[A\033[K")
        lines = []
        lines.append(f"\033[1m{message}\033[0m")
        for i, opt in enumerate(options):
            if i == idx:
                lines.append(f"  \033[36m▶\033[0m \033[1m{opt['label']}\033[0m")
            else:
                lines.append(f"    \033[2m{opt['label']}\033[0m")
        lines.append("  \033[2m↑↓ 移动  Enter 确认  Esc 取消\033[0m")
        sys.stdout.write("\n".join(lines) + "\n")
        sys.stdout.flush()
        rendered_lines = len(lines)

    _render()

    while True:
        key = msvcrt.getch()
        if key == b'\xe0':  # Arrow key prefix on Windows
            key2 = msvcrt.getch()
            if key2 == b'H':  # Up
                idx = (idx - 1) % len(options)
            elif key2 == b'P':  # Down
                idx = (idx + 1) % len(options)
            _render()
        elif key == b'\r':  # Enter
            for _ in range(rendered_lines):
                sys.stdout.write("\033[A\033[K")
            sys.stdout.flush()
            return options[idx]["value"]
        elif key == b'\x1b':  # Esc
            for _ in range(rendered_lines):
                sys.stdout.write("\033[A\033[K")
            sys.stdout.flush()
            return None


def select_multi(options, message="选择（空格切换，Enter 确认）："):
    """多选菜单。上下箭头移动，空格切换选中，Enter 确认。

    options: [{"value": str, "label": str}, ...]
    Returns: 选中的 value 列表
    """
    if not options:
        return []

    import msvcrt

    idx = 0
    checked = set()
    rendered_lines = 0

    def _render():
        nonlocal rendered_lines
        for _ in range(rendered_lines):
            sys.stdout.write("\033[A\033[K")
        lines = []
        lines.append(f"\033[1m{message}\033[0m")
        for i, opt in enumerate(options):
            mark = "\033[32m✓\033[0m" if opt["value"] in checked else "\033[2m○\033[0m"
            if i == idx:
                lines.append(f"  \033[36m▶\033[0m {mark} \033[1m{opt['label']}\033[0m")
            else:
                lines.append(f"    {mark} {opt['label']}")
        lines.append("  \033[2m↑↓ 移动  空格切换  Enter 确认  Esc 取消\033[0m")
        sys.stdout.write("\n".join(lines) + "\n")
        sys.stdout.flush()
        rendered_lines = len(lines)

    _render()

    while True:
        key = msvcrt.getch()
        if key == b'\xe0':
            key2 = msvcrt.getch()
            if key2 == b'H':
                idx = (idx - 1) % len(options)
            elif key2 == b'P':
                idx = (idx + 1) % len(options)
            _render()
        elif key == b' ':  # Space to toggle
            val = options[idx]["value"]
            if val in checked:
                checked.discard(val)
            else:
                checked.add(val)
            _render()
        elif key == b'\r':  # Enter
            for _ in range(rendered_lines):
                sys.stdout.write("\033[A\033[K")
            sys.stdout.flush()
            return [opt["value"] for opt in options if opt["value"] in checked]
        elif key == b'\x1b':  # Esc
            for _ in range(rendered_lines):
                sys.stdout.write("\033[A\033[K")
            sys.stdout.flush()
            return []


def confirm(message="确认？", default=True):
    """确认对话。y/n 输入，Enter 使用默认值。"""
    hint = "[Y/n]" if default else "[y/N]"
    try:
        session = _get_session()
        answer = session.prompt(
            HTML(f"<prompt>{message} {hint} </prompt>"),
            style=_style,
        ).strip().lower()
    except (EOFError, KeyboardInterrupt):
        return False
    except Exception:
        try:
            sys.stdout.write(f"{message} {hint} ")
            sys.stdout.flush()
            answer = input().strip().lower()
        except (EOFError, KeyboardInterrupt):
            return False
    if not answer:
        return default
    return answer in ("y", "yes", "是", "true", "1")


def text_input(message="输入内容（输入 END 结束）："):
    """多行文本输入。每行输入，单独输入 END 结束。"""
    from rich.console import Console
    console = Console()
    console.print(f"[dim]{message}[/dim]")
    lines = []
    try:
        session = _get_session()
        use_prompt_toolkit = True
    except Exception:
        use_prompt_toolkit = False

    while True:
        try:
            if use_prompt_toolkit:
                line = session.prompt(HTML("<prompt>  </prompt>"), style=_style)
            else:
                sys.stdout.write("  ")
                sys.stdout.flush()
                line = input()
        except (EOFError, KeyboardInterrupt):
            return None
        if line.strip().upper() == "END":
            break
        lines.append(line)
    return "\n".join(lines) if lines else None
