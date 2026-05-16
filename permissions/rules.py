"""权限规则引擎。

规则格式：
{
    "tool": "tool_name",           # 工具名，支持 glob 模式
    "pattern": "content_pattern",  # 可选，匹配工具参数的正则
    "behavior": "allow|deny|ask",  # 行为
    "source": "user|project|local|session"  # 来源（自动填充）
}
"""

import fnmatch
import re
from dataclasses import dataclass, field
from enum import Enum


class Behavior(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    ASK = "ask"


class Source(str, Enum):
    SESSION = "session"    # 最高优先级
    PROJECT = "project"    # 项目级 .ecode/settings.json
    LOCAL = "local"        # 本地级
    USER = "user"          # 用户级 ~/.ecode/settings.json
    MODE = "mode"          # 模式默认值（最低优先级）


@dataclass
class PermissionRule:
    tool: str                    # 工具名模式（支持 glob）
    behavior: Behavior
    source: Source
    pattern: str = ""            # 可选，匹配工具参数的正则
    _compiled_pattern: re.Pattern = field(default=None, repr=False)

    def __post_init__(self):
        if self.pattern:
            try:
                self._compiled_pattern = re.compile(self.pattern, re.IGNORECASE)
            except re.error:
                self._compiled_pattern = None

    def matches(self, tool_name: str, tool_args: dict = None) -> bool:
        """检查此规则是否匹配给定的工具调用。"""
        # 检查工具名（glob 模式）
        if not fnmatch.fnmatch(tool_name, self.tool):
            return False
        # 如果有内容模式，检查工具参数
        if self._compiled_pattern and tool_args:
            args_str = " ".join(str(v) for v in tool_args.values())
            if not self._compiled_pattern.search(args_str):
                return False
        return True


@dataclass
class PermissionResult:
    behavior: Behavior
    rule: PermissionRule = None
    reason: str = ""


# 优先级：session > project > local > user > mode
_SOURCE_PRIORITY = {
    Source.SESSION: 0,
    Source.PROJECT: 1,
    Source.LOCAL: 2,
    Source.USER: 3,
    Source.MODE: 4,
}


def evaluate_permission(
    tool_name: str,
    tool_args: dict,
    rules: list[PermissionRule],
    default_behavior: Behavior = Behavior.ASK,
) -> PermissionResult:
    """评估工具调用的权限。

    按优先级遍历规则，第一个匹配的规则决定行为。

    Args:
        tool_name: 工具名
        tool_args: 工具参数
        rules: 规则列表（混合来源）
        default_behavior: 无规则匹配时的默认行为

    Returns:
        PermissionResult
    """
    # 按优先级排序
    sorted_rules = sorted(rules, key=lambda r: _SOURCE_PRIORITY.get(r.source, 99))

    for rule in sorted_rules:
        if rule.matches(tool_name, tool_args):
            return PermissionResult(
                behavior=rule.behavior,
                rule=rule,
                reason=f"规则匹配: {rule.source.value}/{rule.tool} -> {rule.behavior.value}",
            )

    return PermissionResult(
        behavior=default_behavior,
        reason=f"无匹配规则，使用默认行为: {default_behavior.value}",
    )
