"""实时状态显示组件 — 兼容 Windows + VSCode。"""

import sys
import time
import threading


class ThinkingIndicator:
    """思考指示器：轻量级 Spinner。"""

    FRAMES = ["-", "\\", "|", "/"]

    def __init__(self):
        self._stop_event = threading.Event()
        self._thread = None
        self._start_time = 0.0
        self._text = "思考中"

    def _run(self):
        frame_idx = 0
        while not self._stop_event.is_set():
            frame = self.FRAMES[frame_idx % len(self.FRAMES)]
            elapsed = time.time() - self._start_time
            line = f"\r  {frame} {self._text} {elapsed:.1f}s   "
            try:
                sys.stdout.write(line)
                sys.stdout.flush()
            except Exception:
                pass
            frame_idx += 1
            self._stop_event.wait(0.15)
        # 清除 spinner 行
        try:
            sys.stdout.write("\r" + " " * 60 + "\r")
            sys.stdout.flush()
        except Exception:
            pass

    def start(self):
        self._start_time = time.time()
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=1)
            self._thread = None

    def update(self, text: str):
        self._text = text
