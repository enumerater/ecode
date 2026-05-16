"""后台任务管理器。"""

import asyncio
import uuid
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable

logger = logging.getLogger(__name__)


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    KILLED = "killed"


@dataclass
class Task:
    """后台任务。"""
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    type: str = "local_bash"  # local_bash, local_agent
    status: TaskStatus = TaskStatus.PENDING
    description: str = ""
    command: str = ""
    output: str = ""
    error: str = ""
    exit_code: int = -1
    _async_task: asyncio.Task = field(default=None, repr=False)


class TaskManager:
    """后台任务管理器。"""

    def __init__(self):
        self._tasks: dict[str, Task] = {}

    def create_task(self, description: str, command: str = "", task_type: str = "local_bash") -> Task:
        """创建一个后台任务。"""
        task = Task(
            type=task_type,
            description=description,
            command=command,
        )
        self._tasks[task.id] = task
        return task

    def get_task(self, task_id: str) -> Task | None:
        """获取任务。"""
        return self._tasks.get(task_id)

    def list_tasks(self, status: TaskStatus = None) -> list[Task]:
        """列出所有任务。"""
        tasks = list(self._tasks.values())
        if status:
            tasks = [t for t in tasks if t.status == status]
        return tasks

    def update_task(self, task_id: str, **kwargs) -> Task | None:
        """更新任务状态。"""
        task = self._tasks.get(task_id)
        if not task:
            return None
        for key, value in kwargs.items():
            if hasattr(task, key):
                setattr(task, key, value)
        return task

    def kill_task(self, task_id: str) -> bool:
        """终止任务。"""
        task = self._tasks.get(task_id)
        if not task:
            return False
        if task._async_task and not task._async_task.done():
            task._async_task.cancel()
        task.status = TaskStatus.KILLED
        return True

    async def run_bash_task(self, task: Task, cwd: str = "."):
        """在后台运行 bash 命令。"""
        task.status = TaskStatus.RUNNING
        try:
            proc = await asyncio.create_subprocess_shell(
                task.command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
            )
            stdout, stderr = await proc.communicate()
            task.output = stdout.decode("utf-8", errors="replace")
            task.error = stderr.decode("utf-8", errors="replace")
            task.exit_code = proc.returncode
            task.status = TaskStatus.COMPLETED if proc.returncode == 0 else TaskStatus.FAILED
        except asyncio.CancelledError:
            task.status = TaskStatus.KILLED
        except Exception as e:
            task.error = str(e)
            task.status = TaskStatus.FAILED

    def start_bash_task(self, task: Task, cwd: str = "."):
        """启动后台 bash 任务。"""
        loop = asyncio.get_event_loop()
        task._async_task = loop.create_task(self.run_bash_task(task, cwd))
        return task


# 全局任务管理器
task_manager = TaskManager()
