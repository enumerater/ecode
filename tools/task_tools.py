"""后台任务工具。"""

import json
from langchain_core.tools import tool


@tool
def create_background_task(description: str, command: str) -> str:
    """创建一个后台运行的任务。

    任务会在后台执行，不会阻塞对话。适用于：
    - 长时间运行的构建命令
    - 测试执行
    - 文件下载

    Args:
        description: 任务描述
        command: 要执行的 shell 命令
    """
    from tasks import task_manager

    task = task_manager.create_task(description=description, command=command)
    from tools import get_project_root
    task_manager.start_bash_task(task, cwd=get_project_root())

    return json.dumps({
        "success": True,
        "task_id": task.id,
        "description": task.description,
        "status": task.status.value,
        "message": f"任务 {task.id} 已在后台启动",
    }, ensure_ascii=False)


@tool
def get_task_status(task_id: str) -> str:
    """获取后台任务的状态。

    Args:
        task_id: 任务 ID
    """
    from tasks import task_manager

    task = task_manager.get_task(task_id)
    if not task:
        return json.dumps({
            "success": False,
            "error": f"任务 {task_id} 不存在",
        }, ensure_ascii=False)

    result = {
        "success": True,
        "task_id": task.id,
        "description": task.description,
        "status": task.status.value,
        "command": task.command,
    }

    # 如果任务完成，包含输出
    if task.status.value in ("completed", "failed"):
        result["output"] = task.output[-2000:] if task.output else ""
        result["error"] = task.error[-1000:] if task.error else ""
        result["exit_code"] = task.exit_code

    return json.dumps(result, ensure_ascii=False)


@tool
def list_background_tasks() -> str:
    """列出所有后台任务。"""
    from tasks import task_manager

    tasks = task_manager.list_tasks()
    task_list = []
    for task in tasks:
        task_list.append({
            "task_id": task.id,
            "description": task.description,
            "status": task.status.value,
            "command": task.command[:50],
        })

    return json.dumps({
        "success": True,
        "tasks": task_list,
        "total": len(task_list),
    }, ensure_ascii=False)


@tool
def kill_background_task(task_id: str) -> str:
    """终止一个后台任务。

    Args:
        task_id: 任务 ID
    """
    from tasks import task_manager

    success = task_manager.kill_task(task_id)
    if success:
        return json.dumps({
            "success": True,
            "message": f"任务 {task_id} 已终止",
        }, ensure_ascii=False)
    else:
        return json.dumps({
            "success": False,
            "error": f"任务 {task_id} 不存在或无法终止",
        }, ensure_ascii=False)
