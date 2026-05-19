"""用户决策工具：让 agent 在不确定时暂停并向用户展示选项。"""

import json
from langchain_core.tools import tool


@tool
def ask_user_question(questions: str) -> str:
    """在任务开始前暂停，向用户展示选项让用户选择方案。

    当遇到架构选型、技术选择、约定等不确定的决策时，调用此工具让用户做决定。
    用户可以通过左右箭头选择方案，也可以自己输入方案。

    Args:
        questions: JSON 字符串，格式为问题列表。每个问题包含:
            - question: 问题文本（如 "选择 Web 框架"）
            - header: 短标签，最多12字符（如 "框架"）
            - options: 选项列表，每个包含 label 和 description
            - multi_select: 是否允许多选（默认 false）

        示例:
        [
            {
                "question": "选择后端框架",
                "header": "框架",
                "options": [
                    {"label": "FastAPI", "description": "现代异步框架，自带 OpenAPI 文档"},
                    {"label": "Flask", "description": "轻量级框架，灵活简单"},
                    {"label": "Django", "description": "全功能框架，内置 ORM 和管理后台"}
                ],
                "multi_select": false
            }
        ]
    """
    try:
        parsed = json.loads(questions) if isinstance(questions, str) else questions
    except (json.JSONDecodeError, TypeError):
        return json.dumps({
            "success": False,
            "error": "questions 参数必须是有效的 JSON 字符串",
        }, ensure_ascii=False)

    if not isinstance(parsed, list) or not parsed:
        return json.dumps({
            "success": False,
            "error": "questions 必须是非空数组",
        }, ensure_ascii=False)

    # 验证每个问题的结构
    for i, q in enumerate(parsed):
        if not isinstance(q, dict):
            return json.dumps({
                "success": False,
                "error": f"questions[{i}] 必须是对象",
            }, ensure_ascii=False)
        if not q.get("question"):
            return json.dumps({
                "success": False,
                "error": f"questions[{i}].question 不能为空",
            }, ensure_ascii=False)
        if not q.get("options") or not isinstance(q["options"], list):
            return json.dumps({
                "success": False,
                "error": f"questions[{i}].options 必须是非空数组",
            }, ensure_ascii=False)

    return json.dumps({
        "signal": "ASK_USER_QUESTION",
        "questions": parsed,
    }, ensure_ascii=False)
