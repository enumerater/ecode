---
name: review
description: 审查代码变更
argument-hint: [file_or_commit]
---

请对指定的代码变更进行审查。

步骤：
1. 如果指定了文件，查看文件的最近变更
2. 如果指定了 commit，查看该 commit 的 diff
3. 如果没有参数，查看当前 unstaged 变更

审查要点：
- 代码逻辑是否正确
- 是否存在潜在 bug 或边界情况
- 代码风格和命名是否一致
- 是否有安全隐患
- 是否有更好的实现方式

请用中文输出审查结果，按严重程度分类：严重 / 建议 / 提示。

$ARGUMENTS
