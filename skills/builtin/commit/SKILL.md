---
name: commit
description: 根据 staged 变更创建 git commit
argument-hint: [message]
---

请根据当前 git staged 变更创建一个 commit。

步骤：
1. 运行 `git diff --cached` 查看 staged 变更
2. 运行 `git status` 确认暂存区状态
3. 编写简洁准确的 commit message
4. 执行 `git commit`

提交信息规范：
- 使用中文
- 第一行简述变更（50 字以内）
- 如有必要，空一行后补充详细说明

$ARGUMENTS
