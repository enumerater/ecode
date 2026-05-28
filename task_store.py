"""任务存储：内存任务状态管理 + 事件通知。

设计参考 Claude Code 的 TasksV2Store：
- 工具做 CRUD 操作，返回简单文本
- TaskStore 管理状态 + 通知订阅者
- UI（CLI/SSE）独立订阅，与 agent 循环解耦
"""

import threading
from dataclasses import dataclass
from typing import Callable


@dataclass
class Task:
    id: str
    subject: str
    active_form: str
    status: str = "pending"  # pending | in_progress | completed


class TaskStore:
    """线程安全的内存任务存储 + 事件通知。"""

    def __init__(self):
        self._tasks: dict[str, Task] = {}
        self._lock = threading.Lock()
        self._subscribers: list[Callable] = []
        self._id_counter = 0

    def create(self, subject: str, active_form: str = "") -> Task:
        """创建任务，返回 Task 对象。"""
        with self._lock:
            self._id_counter += 1
            task_id = str(self._id_counter)
            task = Task(
                id=task_id,
                subject=subject,
                active_form=active_form or subject,
                status="pending",
            )
            self._tasks[task_id] = task
        self._notify()
        return task

    def update(self, task_id: str, status: str = "", subject: str = "", active_form: str = "") -> Task | None:
        """更新任务，返回更新后的 Task 或 None。"""
        with self._lock:
            task = self._tasks.get(task_id)
            if not task:
                return None
            if status:
                task.status = status
            if subject:
                task.subject = subject
            if active_form:
                task.active_form = active_form
        self._notify()
        return task

    def list(self) -> list[Task]:
        """返回所有任务列表（按 ID 排序）。"""
        with self._lock:
            return sorted(self._tasks.values(), key=lambda t: int(t.id))

    def get(self, task_id: str) -> Task | None:
        """获取单个任务。"""
        with self._lock:
            return self._tasks.get(task_id)

    def reset(self):
        """清空所有任务。"""
        with self._lock:
            self._tasks.clear()
            self._id_counter = 0
        self._notify()

    def subscribe(self, callback: Callable) -> Callable:
        """订阅任务变化，返回取消订阅函数。"""
        self._subscribers.append(callback)

        def unsubscribe():
            try:
                self._subscribers.remove(callback)
            except ValueError:
                pass

        return unsubscribe

    def _notify(self):
        """通知所有订阅者。"""
        tasks = self.list()
        for cb in self._subscribers[:]:
            try:
                cb(tasks)
            except Exception:
                pass


# 全局单例
task_store = TaskStore()
