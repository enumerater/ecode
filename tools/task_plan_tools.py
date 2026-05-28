"""任务规划工具：让 agent 将复杂任务分解为多个步骤并跟踪执行进度。

工具做纯 CRUD 操作，通过 TaskStore 事件总线通知 UI。
"""

from langchain_core.tools import tool

from task_store import task_store


@tool
def create_task(subject: str, active_form: str = "") -> str:
    """创建一个任务步骤，用于复杂任务的规划和进度跟踪。

    在处理复杂任务时，先用此工具创建所有步骤，然后逐步执行。
    每个步骤会实时显示在前端，用户可以看到当前进度。

    Args:
        subject: 任务标题（如 "分析项目结构"、"编写数据模型"）
        active_form: 执行中显示的文本（如 "正在分析项目结构"），为空时使用 subject
    """
    task = task_store.create(subject, active_form)
    return f"任务已创建: {task.subject} (id: {task.id})"


@tool
def update_task(task_id: str, status: str = "", subject: str = "", active_form: str = "") -> str:
    """更新任务状态或信息。

    开始执行某步骤时设为 in_progress，完成时设为 completed。

    Args:
        task_id: 任务 ID（创建时返回的 id）
        status: 新状态，可选值: "pending", "in_progress", "completed"
        subject: 更新任务标题（可选）
        active_form: 更新执行中显示文本（可选）
    """
    task = task_store.update(task_id, status=status, subject=subject, active_form=active_form)
    if not task:
        return f"任务 {task_id} 不存在"
    parts = [f"任务 {task_id} 已更新"]
    if status:
        parts.append(f"状态: {status}")
    return ", ".join(parts)


@tool
def list_tasks() -> str:
    """列出当前所有任务及其状态。

    用于查看任务规划的整体进度。
    """
    tasks = task_store.list()
    if not tasks:
        return "当前没有任务"
    lines = [f"共 {len(tasks)} 个任务:"]
    for t in tasks:
        icon = {"pending": "○", "in_progress": "▶", "completed": "✓"}.get(t.status, "○")
        lines.append(f"  {icon} [{t.status}] {t.subject} (id: {t.id})")
    return "\n".join(lines)
