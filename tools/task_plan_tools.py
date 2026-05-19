"""任务规划工具：让 agent 将复杂任务分解为多个步骤并跟踪执行进度。"""

import json
import uuid
from langchain_core.tools import tool


# 任务信号常量
TASK_SIGNAL = "TASK_UPDATE"


@tool
def create_task(subject: str, active_form: str = "") -> str:
    """创建一个任务步骤，用于复杂任务的规划和进度跟踪。

    在处理复杂任务时，先用此工具创建所有步骤，然后逐步执行。
    每个步骤会实时显示在前端，用户可以看到当前进度。

    Args:
        subject: 任务标题（如 "分析项目结构"、"编写数据模型"）
        active_form: 执行中显示的文本（如 "正在分析项目结构"），为空时使用 subject
    """
    task_id = str(uuid.uuid4())[:8]
    return json.dumps({
        "signal": TASK_SIGNAL,
        "action": "create",
        "task": {
            "id": task_id,
            "subject": subject,
            "activeForm": active_form or subject,
            "status": "pending",
        },
    }, ensure_ascii=False)


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
    update_data = {"signal": TASK_SIGNAL, "action": "update", "task_id": task_id}
    if status:
        update_data["status"] = status
    if subject:
        update_data["subject"] = subject
    if active_form:
        update_data["activeForm"] = active_form
    return json.dumps(update_data, ensure_ascii=False)


@tool
def list_tasks() -> str:
    """列出当前所有任务及其状态。

    用于查看任务规划的整体进度。
    """
    return json.dumps({
        "signal": TASK_SIGNAL,
        "action": "list",
    }, ensure_ascii=False)
