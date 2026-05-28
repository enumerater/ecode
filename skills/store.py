"""Skill 注册表：管理已加载的 skill。"""

from __future__ import annotations
import logging
from pathlib import Path

from skills.loader import Skill, scan_skill_dir

logger = logging.getLogger(__name__)

# 内置 skill 目录
_BUILTIN_DIR = Path(__file__).parent / "builtin"


class SkillStore:
    """内存 skill 注册表。"""

    def __init__(self):
        self._skills: dict[str, Skill] = {}
        self._disabled: set[str] = set()

    def load_all(self, project_root: str = "."):
        """加载所有来源的 skill：builtin → user → project。"""
        self._skills.clear()

        # 1. 内置 skills
        if _BUILTIN_DIR.is_dir():
            for skill in scan_skill_dir(_BUILTIN_DIR, "builtin"):
                self._skills[skill.name] = skill
                logger.debug(f"加载内置 skill: {skill.name}")

        # 2. 用户级 skills: ~/.ecode/skills/
        user_dir = Path.home() / ".ecode" / "skills"
        if user_dir.is_dir():
            for skill in scan_skill_dir(user_dir, "user"):
                self._skills[skill.name] = skill
                logger.debug(f"加载用户 skill: {skill.name}")

        # 3. 项目级 skills: <project_root>/.ecode/skills/
        project_dir = Path(project_root) / ".ecode" / "skills"
        if project_dir.is_dir():
            for skill in scan_skill_dir(project_dir, "project"):
                self._skills[skill.name] = skill
                logger.debug(f"加载项目 skill: {skill.name}")

        # 读取禁用列表
        self._load_disabled(project_root)

        logger.info(f"共加载 {len(self._skills)} 个 skill, {len(self._disabled)} 个已禁用")

    def _load_disabled(self, project_root: str = "."):
        """从 settings.json 读取禁用的 skill 列表。"""
        self._disabled.clear()
        # 用户级
        user_settings = Path.home() / ".ecode" / "settings.json"
        if user_settings.exists():
            try:
                import json
                data = json.loads(user_settings.read_text(encoding="utf-8"))
                self._disabled.update(data.get("disabled_skills", []))
            except Exception:
                pass
        # 项目级（覆盖用户级）
        project_settings = Path(project_root) / ".ecode" / "settings.json"
        if project_settings.exists():
            try:
                import json
                data = json.loads(project_settings.read_text(encoding="utf-8"))
                # 项目级用 enabled_skills 白名单模式也可以，但统一用 disabled 列表
                self._disabled.update(data.get("disabled_skills", []))
            except Exception:
                pass

    def is_enabled(self, name: str) -> bool:
        """检查 skill 是否启用。"""
        return name not in self._disabled

    def set_enabled(self, name: str, enabled: bool):
        """设置 skill 启用状态（内存）。"""
        if enabled:
            self._disabled.discard(name)
        else:
            self._disabled.add(name)

    def save_disabled(self, project_root: str = "."):
        """持久化禁用列表到项目级 settings.json。"""
        import json
        project_path = Path(project_root) / ".ecode" / "settings.json"
        data = {}
        if project_path.exists():
            try:
                data = json.loads(project_path.read_text(encoding="utf-8"))
            except Exception:
                pass
        data["disabled_skills"] = sorted(self._disabled)
        project_path.parent.mkdir(parents=True, exist_ok=True)
        project_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        logger.info(f"已保存禁用 skill 列表: {sorted(self._disabled)}")

    def get_all(self) -> list[Skill]:
        """返回所有 skill（含禁用），用于管理界面。"""
        return list(self._skills.values())

    def get(self, name: str) -> Skill | None:
        """获取 skill（不管是否启用）。"""
        return self._skills.get(name)

    def get_enabled(self, name: str) -> Skill | None:
        """获取已启用的 skill，禁用的返回 None。"""
        if name in self._disabled:
            return None
        return self._skills.get(name)

    def list(self) -> list[Skill]:
        """返回所有已启用的 skill。"""
        return [s for s in self._skills.values() if s.name not in self._disabled]

    def list_user_invocable(self) -> list[Skill]:
        """返回已启用且用户可调用的 skill。"""
        return [s for s in self._skills.values()
                if s.user_invocable and s.name not in self._disabled]

    def list_model_invocable(self) -> list[Skill]:
        """返回已启用且 LLM 可调用的 skill。"""
        return [s for s in self._skills.values()
                if not s.disable_model_invocation and s.name not in self._disabled]

    def reload(self, project_root: str = "."):
        """重新加载所有 skill。"""
        self.load_all(project_root)

    def get_skill_names(self) -> list[str]:
        """返回已启用的 skill 名称列表。"""
        return [s.name for s in self._skills.values() if s.name not in self._disabled]


# 全局单例
skill_store = SkillStore()
