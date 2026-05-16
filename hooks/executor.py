"""Hook 执行引擎。"""

import json
import subprocess
import logging
import fnmatch
from pathlib import Path
from typing import Any

from hooks.types import HookEvent, HookType, HookConfig, HookResult

logger = logging.getLogger(__name__)

# 用户级设置目录
USER_SETTINGS_DIR = Path.home() / ".ecode"
USER_SETTINGS_FILE = USER_SETTINGS_DIR / "settings.json"

# 项目级设置文件
PROJECT_SETTINGS_FILE = ".ecode/settings.json"


def _load_hooks_from_file(path: Path) -> list[HookConfig]:
    """从设置文件加载 hooks。"""
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        hooks_data = data.get("hooks", [])
        hooks = []
        for h in hooks_data:
            try:
                event = HookEvent(h.get("event", ""))
            except ValueError:
                logger.warning(f"未知 hook 事件: {h.get('event')}")
                continue

            hook_type_str = h.get("type", "shell")
            try:
                hook_type = HookType(hook_type_str)
            except ValueError:
                logger.warning(f"未知 hook 类型: {hook_type_str}")
                continue

            hooks.append(HookConfig(
                event=event,
                type=hook_type,
                command=h.get("command", ""),
                matcher=h.get("matcher", ""),
                timeout=h.get("timeout", 30),
                async_mode=h.get("async", False),
            ))
        return hooks
    except Exception as e:
        logger.warning(f"加载 hooks 失败 {path}: {e}")
        return []


class HookExecutor:
    """Hook 执行器。"""

    def __init__(self, project_root: str = "."):
        self.project_root = project_root
        self._hooks: list[HookConfig] = []
        self._load()

    def _load(self):
        """加载所有 hooks。"""
        # 用户级
        self._hooks.extend(_load_hooks_from_file(USER_SETTINGS_FILE))
        # 项目级
        project_path = Path(self.project_root) / PROJECT_SETTINGS_FILE
        self._hooks.extend(_load_hooks_from_file(project_path))

    def get_hooks(self, event: HookEvent, tool_name: str = "") -> list[HookConfig]:
        """获取匹配的 hooks。"""
        matched = []
        for hook in self._hooks:
            if hook.event != event:
                continue
            # 如果有 matcher，检查工具名
            if hook.matcher and tool_name:
                if not fnmatch.fnmatch(tool_name, hook.matcher):
                    continue
            matched.append(hook)
        return matched

    def execute_shell_hook(self, hook: HookConfig, context: dict = None) -> HookResult:
        """执行 shell 类型的 hook。"""
        try:
            env = {**__import__('os').environ}
            if context:
                env["ECODE_HOOK_CONTEXT"] = json.dumps(context, ensure_ascii=False)

            result = subprocess.run(
                hook.command,
                shell=True,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=hook.timeout,
                cwd=self.project_root,
                env=env,
            )

            output = result.stdout.strip()
            error = result.stderr.strip()

            # 解析输出（期望 JSON 格式）
            hook_result = HookResult(success=result.returncode == 0, output=output, error=error)
            if output:
                try:
                    parsed = json.loads(output)
                    hook_result.continue_execution = parsed.get("continue", True)
                    hook_result.decision = parsed.get("decision", "")
                    hook_result.system_message = parsed.get("systemMessage", "")
                except json.JSONDecodeError:
                    pass

            return hook_result

        except subprocess.TimeoutExpired:
            return HookResult(success=False, error=f"Hook 超时 ({hook.timeout}s)")
        except Exception as e:
            return HookResult(success=False, error=str(e))

    def execute_prompt_hook(self, hook: HookConfig, context: dict = None) -> HookResult:
        """执行 prompt 类型的 hook（返回要注入的文本）。"""
        return HookResult(
            success=True,
            system_message=hook.command,
        )


def run_hooks(
    event: HookEvent,
    tool_name: str = "",
    project_root: str = ".",
    context: dict = None,
) -> list[HookResult]:
    """运行指定事件的所有匹配 hooks。

    Args:
        event: Hook 事件
        tool_name: 工具名（用于 matcher 匹配）
        project_root: 项目根目录
        context: 上下文数据

    Returns:
        HookResult 列表
    """
    executor = HookExecutor(project_root)
    hooks = executor.get_hooks(event, tool_name)

    if not hooks:
        return []

    results = []
    for hook in hooks:
        if hook.type == HookType.SHELL:
            result = executor.execute_shell_hook(hook, context)
        elif hook.type == HookType.PROMPT:
            result = executor.execute_prompt_hook(hook, context)
        else:
            result = HookResult(success=False, error=f"不支持的 hook 类型: {hook.type}")

        results.append(result)

        # 如果 hook 要求停止执行
        if not result.continue_execution:
            break

    return results
