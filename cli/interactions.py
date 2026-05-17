"""交互组件：prompt_toolkit 输入、单选菜单、多选菜单、确认对话。"""
import os
import sys
import re
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


# ── prompt_toolkit 设置 ─────────────────────────────────────────────────────
HISTORY_FILE = os.path.join(os.path.expanduser("~"), ".ecode_history")
_HISTORY_MAX = 1000

_prompt_session = None
_slash_commands: list[str] = []

# ── 粘贴芯片（Paste Chip）──────────────────────────────────────────────────
# 粘贴多行文本时，显示为 [Pasted text #N +X lines] 的可折叠芯片
_CHIP_PATTERN = re.compile(r"\[Pasted text #(\d+) \+(\d+) lines\]")
_chip_counter = 0
_chip_store: dict[str, str] = {}  # 显示文本 → 原始文本


def _make_chip_text(original: str) -> str:
    """将多行文本转换为芯片显示文本。"""
    global _chip_counter
    _chip_counter += 1
    lines = original.split("\n")
    extra = len(lines) - 1
    chip = f"[Pasted text #{_chip_counter} +{extra} lines]"
    _chip_store[chip] = original
    return chip


def _expand_chips(text: str) -> str:
    """将所有芯片展开为原始文本。"""
    result = text
    for chip, original in _chip_store.items():
        result = result.replace(chip, original)
    return result


# ── 历史文件管理 ──────────────────────────────────────────────────────────
def _load_history():
    """加载历史记录文件。"""
    from prompt_toolkit.history import FileHistory
    history = FileHistory(HISTORY_FILE)
    return history


def _create_prompt_session():
    """创建 prompt_toolkit PromptSession。"""
    global _prompt_session
    if _prompt_session is not None:
        return _prompt_session

    from prompt_toolkit import PromptSession
    from prompt_toolkit.completion import WordCompleter
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.filters import Condition

    history = _load_history()

    # ── 键绑定 ──
    kb = KeyBindings()

    @kb.add("c-c")
    def _(event):
        """Ctrl+C: 清空输入。"""
        event.app.current_buffer.text = ""
        event.app.current_buffer.cursor_position = 0

    # ── Backspace: 删除整个芯片 ──
    @kb.add("backspace")
    def _(event):
        buf = event.app.current_buffer
        text = buf.text
        pos = buf.cursor_position
        before = text[:pos]
        for chip in _chip_store:
            if before.endswith(chip):
                new_text = text[:pos - len(chip)] + text[pos:]
                new_pos = pos - len(chip)
                buf.text = new_text
                buf.cursor_position = new_pos
                return
        # 普通退格
        buf.delete_before_cursor(count=1)

    # ── Enter: 展开芯片后提交 ──
    @kb.add("enter")
    def _(event):
        buf = event.app.current_buffer
        expanded = _expand_chips(buf.text)
        buf.text = expanded
        buf.validate_and_handle()

    # ── Tab: 补全斜杠命令 ──
    @Condition
    def has_slash_commands():
        return len(_slash_commands) > 0

    @kb.add("tab", filter=has_slash_commands)
    def _(event):
        buf = event.app.current_buffer
        text = buf.text
        if text.startswith("/"):
            matches = [c for c in _slash_commands if c.startswith(text)]
            if len(matches) == 1:
                buf.text = matches[0]
                buf.cursor_position = len(matches[0])
            elif len(matches) > 1:
                # 显示匹配列表
                sys.stdout.write("\n" + "  ".join(matches) + "\n")
                sys.stdout.flush()
        else:
            buf.insert_text("    ")

    # ── PromptSession ──
    cwd_short = os.path.basename(os.getcwd())
    prompt_msg = [
        ("class:dim", f"\n[{cwd_short}] "),
        ("class:prompt", "> "),
    ]

    # 尝试创建 output，处理无控制台的情况
    output = None
    try:
        from prompt_toolkit.output import defaults as output_defaults
        output = output_defaults.create_output()
    except Exception:
        from prompt_toolkit.output.vt100 import Vt100_Output
        output = Vt100_Output(sys.stdout)

    _prompt_session = PromptSession(
        message=prompt_msg,
        history=history,
        key_bindings=kb,
        multiline=False,
        wrap_lines=False,
        output=output,
    )

    # ── 拦截粘贴：在 buffer.insert_text 时检测多行文本并转为芯片 ──
    _orig_insert_text = _prompt_session.default_buffer.insert_text

    def _patched_insert_text(data, overwrite=False, move_cursor=True, fire_event=True):
        if "\n" in data:
            lines = data.rstrip("\n").split("\n")
            if len(lines) > 1:
                chip = _make_chip_text(data.rstrip("\n"))
                first_line = lines[0]
                data = first_line + " " + chip if first_line else chip
        return _orig_insert_text(data, overwrite=overwrite, move_cursor=move_cursor, fire_event=fire_event)

    _prompt_session.default_buffer.insert_text = _patched_insert_text

    return _prompt_session


def prompt_input(message=">"):
    """带历史记录的输入，支持多行粘贴芯片。

    - 粘贴多行文本时自动显示为 [Pasted text #N +X lines] 芯片
    - 芯片作为一个整体：Backspace 一键删除
    - Enter 发送时自动展开芯片为原始文本
    """
    global _chip_store
    _chip_store = {}  # 每次输入清空芯片存储

    session = _create_prompt_session()

    # 更新提示符（如果 message 不同）
    cwd_short = os.path.basename(os.getcwd())
    if message != ">":
        session.message = [
            ("class:dim", f"\n[{cwd_short}] "),
            ("class:prompt", f"{message} "),
        ]

    try:
        result = session.prompt()
    except (EOFError, KeyboardInterrupt):
        return None

    # 展开芯片
    expanded = _expand_chips(result)
    # 清理芯片存储
    _chip_store.clear()
    return expanded


def set_slash_commands(cmds: list[str]):
    """设置斜杠命令补全列表。"""
    global _slash_commands
    _slash_commands = [f"/{c}" for c in cmds]
    # 如果 session 已创建，更新补全器
    if _prompt_session is not None:
        from prompt_toolkit.completion import WordCompleter
        completer = WordCompleter(_slash_commands, ignore_case=True)
        _prompt_session.completer = completer


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
