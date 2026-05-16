"""查询级 Spinner — 管理整个查询生命周期。

关键设计：
- Rich Status 用于 spinner 动画（思考中、执行工具）
- 流式文本直接写入 stdout，绕过 Rich 避免重绘冲突
- pause/resume 控制 spinner 显示/隐藏
"""

import sys
import time
import threading
from rich.console import Console
from rich.status import Status

try:
    from .display import console
except ImportError:
    console = Console(force_terminal=True)

# Spinner 状态
THINKING = "thinking"
TOOL_USE = "tool_use"
RESPONDING = "responding"

STATE_TEXT = {
    THINKING: "思考中",
    TOOL_USE: "执行工具",
    RESPONDING: "回复中",
}


class QuerySpinner:
    """查询级 Spinner：统一管理 spinner 和流式输出。"""

    def __init__(self):
        self._status = None
        self._query_start = 0.0
        self._state = THINKING
        self._detail = ""
        self._paused = False
        self._lock = threading.Lock()

    def _make_text(self):
        elapsed = time.time() - self._query_start
        state_text = STATE_TEXT.get(self._state, self._state)
        if self._detail:
            return f"[cyan]{state_text}: {self._detail}[/cyan] [dim]{elapsed:.1f}s[/dim]"
        return f"[cyan]{state_text}[/cyan] [dim]{elapsed:.1f}s[/dim]"

    def _refresh(self):
        """更新 Status 显示文本。"""
        if self._status and not self._paused:
            try:
                self._status.update(self._make_text())
            except Exception:
                pass

    def _timer_loop(self):
        """后台线程：每 300ms 更新计时器显示。"""
        while not self._timer_stop.is_set():
            self._refresh()
            self._timer_stop.wait(0.3)

    def start(self):
        """查询开始。"""
        self._query_start = time.time()
        self._state = THINKING
        self._detail = ""
        self._paused = False
        self._status = Status(self._make_text(), console=console, spinner="dots")
        self._status.start()
        self._timer_stop = threading.Event()
        self._timer_thread = threading.Thread(target=self._timer_loop, daemon=True)
        self._timer_thread.start()

    def stop(self):
        """查询结束。"""
        if hasattr(self, '_timer_stop') and self._timer_stop:
            self._timer_stop.set()
        if hasattr(self, '_timer_thread') and self._timer_thread:
            self._timer_thread.join(timeout=0.5)
            self._timer_thread = None
        if self._status:
            self._status.stop()
            self._status = None

    def set_state(self, state: str, detail: str = ""):
        """切换状态。"""
        with self._lock:
            self._state = state
            self._detail = detail
        self._refresh()

    def elapsed(self) -> float:
        return time.time() - self._query_start

    def stream_write(self, text: str):
        """流式文本输出：直接写入 stdout，避免 Rich 重绘干扰。"""
        if self._status and not self._paused:
            self._paused = True
            self._status.stop()
        sys.stdout.write(text)
        sys.stdout.flush()

    def stream_end(self):
        """流式输出结束：恢复 spinner。"""
        if self._paused:
            self._paused = False
            if self._status:
                self._status.start()
