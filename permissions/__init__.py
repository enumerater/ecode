"""权限系统：规则引擎 + 权限模式。"""

from permissions.rules import PermissionRule, PermissionResult, evaluate_permission
from permissions.modes import PermissionMode, get_mode_defaults, MODE_DESCRIPTIONS

__all__ = [
    "PermissionRule", "PermissionResult", "evaluate_permission",
    "PermissionMode", "get_mode_defaults", "MODE_DESCRIPTIONS",
]
