---
name: test
description: 运行项目测试
argument-hint: [test_path_or_filter]
---

请运行项目的测试套件。

步骤：
1. 检测项目类型（查看 package.json / pyproject.toml / Makefile 等）
2. 确定测试命令：
   - Python: `pytest` 或 `python -m unittest`
   - Node.js: `npm test` 或 `npx jest`
   - 有 Makefile: `make test`
3. 如果指定了测试路径或过滤条件，添加到命令中
4. 执行测试并报告结果

如果测试失败，请分析失败原因并给出修复建议。

$ARGUMENTS
