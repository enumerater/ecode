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

        logger.info(f"共加载 {len(self._skills)} 个 skill")

    def get(self, name: str) -> Skill | None:
        """获取 skill。"""
        return self._skills.get(name)

    def list(self) -> list[Skill]:
        """返回所有 skill。"""
        return list(self._skills.values())

    def list_user_invocable(self) -> list[Skill]:
        """返回用户可调用的 skill。"""
        return [s for s in self._skills.values() if s.user_invocable]

    def list_model_invocable(self) -> list[Skill]:
        """返回 LLM 可调用的 skill。"""
        return [s for s in self._skills.values() if not s.disable_model_invocation]

    def reload(self, project_root: str = "."):
        """重新加载所有 skill。"""
        self.load_all(project_root)

    def get_skill_names(self) -> list[str]:
        """返回所有 skill 名称列表。"""
        return list(self._skills.keys())


# 全局单例
skill_store = SkillStore()
