"""交互组件：readline 历史、单选菜单、多选菜单、确认对话。"""
import os
import sys
import atexit

# ── ANSI 色码 ──────────────────────────────────────────────────────────────
C = {
    "cyan":    "\033[36m",
    "green":   "\033[32m",
    "yellow":  "\033[33m",
    "red":     "\033[31m",
    "bold":    "\033[1m",
    "dim":     "\033[2m",
    "reset":   "\033[0m",
}

def clr(text, *keys):
    return "".join(C[k] for k in keys) + str(text) + C["reset"]


# ── readline 历史设置 ──────────────────────────────────────────────────────
HISTORY_FILE = os.path.join(os.path.expanduser("~"), ".ecode_history")
_HISTORY_MAX = 1000

def setup_readline():
    """初始化 readline：加载历史、设置长度、注册退出时保存。"""
    try:
        import readline as _rl
        try:
            _rl.read_history_file(HISTORY_FILE)
        except FileNotFoundError:
            pass
        _rl.set_history_length(_HISTORY_MAX)
        atexit.register(_rl.write_history_file, HISTORY_FILE)
    except ImportError:
        # Windows 没有 readline 也没 pyreadline3，跳过
        pass

# 斜杠命令补全列表（在 chat.py 中注册）
_slash_commands: list[str] = []

def set_slash_commands(cmds: list[str]):
    global _slash_commands
    _slash_commands = [f"/{c}" for c in cmds]
    try:
        import readline as _rl
        def _completer(text, state):
            matches = [c for c in _slash_commands if c.startswith(text)]
            return matches[state] if state < len(matches) else None
        _rl.set_completer(_completer)
        _rl.parse_and_bind("tab: complete")
    except ImportError:
        pass


# ── 带历史的输入 ──────────────────────────────────────────────────────────

def prompt_input(message=">"):
    """带历史记录的单行输入。上/下箭头翻历史，Tab 补全斜杠命令。"""
    cwd_short = os.path.basename(os.getcwd())
    prompt = clr(f"\n[{cwd_short}] ", "dim") + clr(f"{message} ", "cyan", "bold")
    try:
        return input(prompt)
    except (EOFError, KeyboardInterrupt):
        return None


# ── 单选菜单 ──────────────────────────────────────────────────────────────

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
        # 清除上次渲染
        for _ in range(rendered_lines):
            sys.stdout.write("\033[A\033[K")
        lines = []
        lines.append(clr(message, "bold"))
        for i, opt in enumerate(options):
            if i == idx:
                lines.append(f"  {clr('▶', 'cyan')} {clr(opt['label'], 'bold')}")
            else:
                lines.append(f"    {clr(opt['label'], 'dim')}")
        lines.append(clr("  ↑↓ 移动  Enter 确认  Esc 取消", "dim"))
        sys.stdout.write("\n".join(lines) + "\n")
        sys.stdout.flush()
        rendered_lines = len(lines)

    _render()

    while True:
        key = msvcrt.getch()
        if key == b'\xe0':  # Windows 方向键前缀
            key2 = msvcrt.getch()
            if key2 == b'H':  # 上
                idx = (idx - 1) % len(options)
            elif key2 == b'P':  # 下
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


# ── 多选菜单 ──────────────────────────────────────────────────────────────

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
        lines.append(clr(message, "bold"))
        for i, opt in enumerate(options):
            mark = clr("✓", "green") if opt["value"] in checked else clr("○", "dim")
            if i == idx:
                lines.append(f"  {clr('▶', 'cyan')} {mark} {clr(opt['label'], 'bold')}")
            else:
                lines.append(f"    {mark} {opt['label']}")
        lines.append(clr("  ↑↓ 移动  空格切换  Enter 确认  Esc 取消", "dim"))
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
        elif key == b' ':  # 空格切换
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


# ── 确认对话 ──────────────────────────────────────────────────────────────

def confirm(message="确认？", default=True):
    """确认对话。y/n 输入，Enter 使用默认值。"""
    hint = clr("[Y/n]", "dim") if default else clr("[y/N]", "dim")
    try:
        ans = input(clr(f"  {message} ", "yellow") + hint + " ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        return False
    if not ans:
        return default
    return ans in ("y", "yes", "是", "true", "1")


# ── 多行文本输入 ──────────────────────────────────────────────────────────

def text_input(message="输入内容（输入 END 结束）："):
    """多行文本输入。每行输入，单独输入 END 结束。"""
    print(clr(message, "dim"))
    lines = []
    while True:
        try:
            line = input(clr("  ", "dim"))
        except (EOFError, KeyboardInterrupt):
            return None
        if line.strip().upper() == "END":
            break
        lines.append(line)
    return "\n".join(lines) if lines else None
