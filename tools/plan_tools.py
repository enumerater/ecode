"""Plan 模式工具：控制 agent 的计划/执行模式。"""

import json
import os
from langchain_core.tools import tool


@tool
def enter_plan_mode() -> str:
    """进入计划模式。

    在计划模式下，agent 只会分析和规划，不会执行任何修改操作。
    适用于复杂任务的前期分析阶段。

    需要用户审批。
    """
    return json.dumps({
        "signal": "ENTER_PLAN_MODE",
        "message": "已进入计划模式。现在只分析规划，不执行修改。",
    }, ensure_ascii=False)


@tool
def exit_plan_mode(plan_content: str = "") -> str:
    """退出计划模式，开始执行。

    当计划完成并获得用户批准后，调用此工具退出计划模式。
    如果提供了 plan_content，会自动保存为 .ecode/plan.md 文件。

    Args:
        plan_content: 完整的计划内容（Markdown 格式）。
            应包含：任务概述、步骤列表、涉及文件、注意事项等。
            为空时不保存文件。

    需要用户审批。
    """
    saved_path = ""
    if plan_content:
        try:
            from tools import get_project_root
            project_root = get_project_root()
            ecode_dir = os.path.join(project_root, ".ecode")
            os.makedirs(ecode_dir, exist_ok=True)
            plan_path = os.path.join(ecode_dir, "plan.md")
            with open(plan_path, "w", encoding="utf-8") as f:
                f.write(plan_content)
            saved_path = plan_path
        except Exception as e:
            saved_path = f"保存失败: {e}"

    result = {
        "signal": "EXIT_PLAN_MODE",
        "message": "已退出计划模式。现在可以执行修改操作。",
    }
    if saved_path:
        result["plan_saved_to"] = saved_path
        result["message"] += f" 计划已保存到 {saved_path}"
    return json.dumps(result, ensure_ascii=False)
