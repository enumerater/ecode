"""Plan 模式工具：控制 agent 的计划/执行模式。"""

import json
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
def exit_plan_mode() -> str:
    """退出计划模式，开始执行。

    当计划完成并获得用户批准后，调用此工具退出计划模式。

    需要用户审批。
    """
    return json.dumps({
        "signal": "EXIT_PLAN_MODE",
        "message": "已退出计划模式。现在可以执行修改操作。",
    }, ensure_ascii=False)
