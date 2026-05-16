"""权限模式定义。

每种模式定义了一组默认规则，决定哪些工具需要审批。
"""

from enum import Enum
from permissions.rules import PermissionRule, Behavior, Source


class PermissionMode(str, Enum):
    DEFAULT = "default"          # 当前行为：安全工具自动执行，危险工具需审批
    PLAN = "plan"                # 只读模式：禁止所有写操作
    AUTO_APPROVE = "auto_approve"  # 自动批准安全+常见编辑，仅破坏性操作需审批
    YOLO = "yolo"                # 全部自动批准（危险模式）


MODE_DESCRIPTIONS = {
    PermissionMode.DEFAULT: "默认模式：安全工具自动执行，危险工具需审批",
    PermissionMode.PLAN: "计划模式：只读，禁止所有写操作（用于分析和规划）",
    PermissionMode.AUTO_APPROVE: "自动批准：安全工具+常见编辑自动执行，仅破坏性操作需审批",
    PermissionMode.YOLO: "YOLO 模式：全部自动批准（谨慎使用）",
}


def get_mode_defaults(mode: PermissionMode) -> list[PermissionRule]:
    """获取模式的默认规则。"""
    if mode == PermissionMode.DEFAULT:
        return _default_mode_rules()
    elif mode == PermissionMode.PLAN:
        return _plan_mode_rules()
    elif mode == PermissionMode.AUTO_APPROVE:
        return _auto_approve_mode_rules()
    elif mode == PermissionMode.YOLO:
        return _yolo_mode_rules()
    return _default_mode_rules()


def _default_mode_rules() -> list[PermissionRule]:
    """默认模式：安全工具自动执行，危险工具需审批。"""
    return [
        # 安全工具：自动允许
        PermissionRule(tool="view_file", behavior=Behavior.ALLOW, source=Source.MODE),
        PermissionRule(tool="search_code", behavior=Behavior.ALLOW, source=Source.MODE),
        PermissionRule(tool="list_files", behavior=Behavior.ALLOW, source=Source.MODE),
        PermissionRule(tool="compact", behavior=Behavior.ALLOW, source=Source.MODE),
        PermissionRule(tool="get_tool_details", behavior=Behavior.ALLOW, source=Source.MODE),
        # Git 只读工具：自动允许
        PermissionRule(tool="git_status", behavior=Behavior.ALLOW, source=Source.MODE),
        PermissionRule(tool="git_diff", behavior=Behavior.ALLOW, source=Source.MODE),
        PermissionRule(tool="git_log", behavior=Behavior.ALLOW, source=Source.MODE),
        PermissionRule(tool="git_blame", behavior=Behavior.ALLOW, source=Source.MODE),
        # 记忆工具：自动允许
        PermissionRule(tool="save_memory", behavior=Behavior.ALLOW, source=Source.MODE),
        PermissionRule(tool="list_memories", behavior=Behavior.ALLOW, source=Source.MODE),
        # 子 Agent 工具：需审批
        PermissionRule(tool="run_agent", behavior=Behavior.ASK, source=Source.MODE),
        # 后台任务工具：需审批
        PermissionRule(tool="create_background_task", behavior=Behavior.ASK, source=Source.MODE),
        PermissionRule(tool="get_task_status", behavior=Behavior.ALLOW, source=Source.MODE),
        PermissionRule(tool="list_background_tasks", behavior=Behavior.ALLOW, source=Source.MODE),
        PermissionRule(tool="kill_background_task", behavior=Behavior.ASK, source=Source.MODE),
        # 危险工具：需审批
        PermissionRule(tool="edit_file", behavior=Behavior.ASK, source=Source.MODE),
        PermissionRule(tool="write_file", behavior=Behavior.ASK, source=Source.MODE),
        PermissionRule(tool="create_file", behavior=Behavior.ASK, source=Source.MODE),
        PermissionRule(tool="create_directory", behavior=Behavior.ASK, source=Source.MODE),
        PermissionRule(tool="run_command", behavior=Behavior.ASK, source=Source.MODE),
        PermissionRule(tool="git_commit", behavior=Behavior.ASK, source=Source.MODE),
    ]


def _plan_mode_rules() -> list[PermissionRule]:
    """计划模式：只读，禁止所有写操作。"""
    return [
        # 只读工具：允许
        PermissionRule(tool="view_file", behavior=Behavior.ALLOW, source=Source.MODE),
        PermissionRule(tool="search_code", behavior=Behavior.ALLOW, source=Source.MODE),
        PermissionRule(tool="list_files", behavior=Behavior.ALLOW, source=Source.MODE),
        PermissionRule(tool="get_tool_details", behavior=Behavior.ALLOW, source=Source.MODE),
        # Git 只读工具：允许
        PermissionRule(tool="git_status", behavior=Behavior.ALLOW, source=Source.MODE),
        PermissionRule(tool="git_diff", behavior=Behavior.ALLOW, source=Source.MODE),
        PermissionRule(tool="git_log", behavior=Behavior.ALLOW, source=Source.MODE),
        PermissionRule(tool="git_blame", behavior=Behavior.ALLOW, source=Source.MODE),
        # 记忆工具：允许（只读）
        PermissionRule(tool="list_memories", behavior=Behavior.ALLOW, source=Source.MODE),
        # 写工具：拒绝
        PermissionRule(tool="edit_file", behavior=Behavior.DENY, source=Source.MODE),
        PermissionRule(tool="write_file", behavior=Behavior.DENY, source=Source.MODE),
        PermissionRule(tool="create_file", behavior=Behavior.DENY, source=Source.MODE),
        PermissionRule(tool="create_directory", behavior=Behavior.DENY, source=Source.MODE),
        PermissionRule(tool="run_command", behavior=Behavior.DENY, source=Source.MODE),
        PermissionRule(tool="git_commit", behavior=Behavior.DENY, source=Source.MODE),
        PermissionRule(tool="save_memory", behavior=Behavior.DENY, source=Source.MODE),
        # compact 允许（只读操作）
        PermissionRule(tool="compact", behavior=Behavior.ALLOW, source=Source.MODE),
    ]


def _auto_approve_mode_rules() -> list[PermissionRule]:
    """自动批准模式：安全工具+常见编辑自动执行，仅破坏性操作需审批。"""
    return [
        # 安全工具：允许
        PermissionRule(tool="view_file", behavior=Behavior.ALLOW, source=Source.MODE),
        PermissionRule(tool="search_code", behavior=Behavior.ALLOW, source=Source.MODE),
        PermissionRule(tool="list_files", behavior=Behavior.ALLOW, source=Source.MODE),
        PermissionRule(tool="compact", behavior=Behavior.ALLOW, source=Source.MODE),
        PermissionRule(tool="get_tool_details", behavior=Behavior.ALLOW, source=Source.MODE),
        # Git 只读工具：允许
        PermissionRule(tool="git_status", behavior=Behavior.ALLOW, source=Source.MODE),
        PermissionRule(tool="git_diff", behavior=Behavior.ALLOW, source=Source.MODE),
        PermissionRule(tool="git_log", behavior=Behavior.ALLOW, source=Source.MODE),
        PermissionRule(tool="git_blame", behavior=Behavior.ALLOW, source=Source.MODE),
        # 记忆工具：自动批准
        PermissionRule(tool="save_memory", behavior=Behavior.ALLOW, source=Source.MODE),
        PermissionRule(tool="list_memories", behavior=Behavior.ALLOW, source=Source.MODE),
        # 常见编辑：自动批准
        PermissionRule(tool="edit_file", behavior=Behavior.ALLOW, source=Source.MODE),
        PermissionRule(tool="write_file", behavior=Behavior.ALLOW, source=Source.MODE),
        PermissionRule(tool="create_file", behavior=Behavior.ALLOW, source=Source.MODE),
        PermissionRule(tool="create_directory", behavior=Behavior.ALLOW, source=Source.MODE),
        # 破坏性操作：需审批
        PermissionRule(tool="run_command", behavior=Behavior.ASK, source=Source.MODE),
        PermissionRule(tool="git_commit", behavior=Behavior.ASK, source=Source.MODE),
    ]


def _yolo_mode_rules() -> list[PermissionRule]:
    """YOLO 模式：全部自动批准。"""
    return [
        PermissionRule(tool="*", behavior=Behavior.ALLOW, source=Source.MODE),
    ]
