"""设置加载器：合并用户/项目/本地设置。

设置文件格式（JSON）：
{
    "permissions": [
        {"tool": "run_command", "pattern": "git commit*", "behavior": "allow"},
        {"tool": "edit_file", "pattern": "*.test.py", "behavior": "allow"}
    ]
}
"""

import json
import logging
from pathlib import Path
from typing import Any

from permissions.rules import PermissionRule, Behavior, Source

logger = logging.getLogger(__name__)

# 用户级设置目录
USER_SETTINGS_DIR = Path.home() / ".ecode"
USER_SETTINGS_FILE = USER_SETTINGS_DIR / "settings.json"

# 项目级设置文件（相对于项目根目录）
PROJECT_SETTINGS_FILE = ".ecode/settings.json"


def _load_json_file(path: Path) -> dict:
    """加载 JSON 文件，不存在或解析失败返回空字典。"""
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        logger.warning(f"加载设置文件失败 {path}: {e}")
        return {}


def _parse_rules(raw_rules: list[dict], source: Source) -> list[PermissionRule]:
    """将原始规则列表解析为 PermissionRule 对象。"""
    rules = []
    for r in raw_rules:
        tool = r.get("tool", "")
        behavior_str = r.get("behavior", "ask")
        pattern = r.get("pattern", "")

        if not tool:
            continue

        try:
            behavior = Behavior(behavior_str)
        except ValueError:
            logger.warning(f"未知行为: {behavior_str}，跳过规则 {r}")
            continue

        rules.append(PermissionRule(
            tool=tool,
            behavior=behavior,
            source=source,
            pattern=pattern,
        ))
    return rules


class Settings:
    """应用设置，合并多来源的规则。"""

    def __init__(self, project_root: str = "."):
        self.project_root = project_root
        self._user_rules: list[PermissionRule] = []
        self._project_rules: list[PermissionRule] = []
        self._session_rules: list[PermissionRule] = []
        self._extra: dict[str, Any] = {}

        self._load()

    def _load(self):
        """加载所有设置源。"""
        # 用户级
        user_data = _load_json_file(USER_SETTINGS_FILE)
        self._user_rules = _parse_rules(
            user_data.get("permissions", []), Source.USER,
        )
        self._extra = {k: v for k, v in user_data.items() if k != "permissions"}

        # 项目级
        project_path = Path(self.project_root) / PROJECT_SETTINGS_FILE
        project_data = _load_json_file(project_path)
        self._project_rules = _parse_rules(
            project_data.get("permissions", []), Source.PROJECT,
        )

    def get_all_rules(self) -> list[PermissionRule]:
        """获取所有规则（用户+项目+会话）。"""
        return self._session_rules + self._project_rules + self._user_rules

    def add_session_rule(self, rule: dict):
        """添加会话级规则。"""
        parsed = _parse_rules([rule], Source.SESSION)
        self._session_rules.extend(parsed)

    def clear_session_rules(self):
        """清除会话级规则。"""
        self._session_rules.clear()

    def get(self, key: str, default=None) -> Any:
        """获取额外设置。"""
        return self._extra.get(key, default)

    def get_disabled_skills(self) -> list[str]:
        """获取禁用的 skill 列表。"""
        return list(self._extra.get("disabled_skills", []))

    def set_disabled_skills(self, disabled: list[str]):
        """设置禁用的 skill 列表并持久化到项目级 settings.json。"""
        project_path = Path(self.project_root) / PROJECT_SETTINGS_FILE
        data = _load_json_file(project_path)
        data["disabled_skills"] = disabled
        project_path.parent.mkdir(parents=True, exist_ok=True)
        project_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        self._extra["disabled_skills"] = disabled
