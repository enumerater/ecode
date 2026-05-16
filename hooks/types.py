"""Hook 类型定义。"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Any


class HookEvent(str, Enum):
    """Hook 事件类型。"""
    PRE_TOOL_USE = "PreToolUse"
    POST_TOOL_USE = "PostToolUse"
    POST_TOOL_USE_FAILURE = "PostToolUseFailure"
    SESSION_START = "SessionStart"
    SESSION_END = "SessionEnd"
    STOP = "Stop"
    USER_PROMPT_SUBMIT = "UserPromptSubmit"


class HookType(str, Enum):
    """Hook 执行类型。"""
    SHELL = "shell"      # 执行 shell 命令
    PROMPT = "prompt"    # 注入提示文本
    CALLBACK = "callback"  # 回调函数（Python）


@dataclass
class HookConfig:
    """Hook 配置。"""
    event: HookEvent
    type: HookType
    command: str = ""        # shell 命令或 prompt 文本
    matcher: str = ""        # 工具名匹配模式（可选）
    timeout: int = 30        # 超时时间（秒）
    async_mode: bool = False  # 是否异步执行


@dataclass
class HookResult:
    """Hook 执行结果。"""
    success: bool = True
    continue_execution: bool = True  # 是否继续执行
    decision: str = ""       # approve, block, 或空
    system_message: str = ""  # 注入的系统消息
    output: str = ""         # hook 输出
    error: str = ""          # 错误信息
