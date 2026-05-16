# Issue 追踪器：本地 Markdown

本项目 Issue 和 PRD 以 Markdown 文件形式存放在 `.scratch/` 目录下。

## 约定

- 每个功能一个子目录：`.scratch/<功能缩写>/`
- PRD 文件：`.scratch/<功能缩写>/PRD.md`
- 实现 Issue：`.scratch/<功能缩写>/issues/<NN>-<简短标题>.md`，从 `01` 开始编号
- Triage 状态记录在每个 Issue 文件顶部的 `Status:` 行（具体标签名见 `triage-labels.md`）
- 评论和讨论记录追加在文件末尾的 `## 讨论` 标题下

## 当 skill 说"发布到 Issue 追踪器"

在 `.scratch/<功能缩写>/` 下创建新文件（如目录不存在则先创建）。

## 当 skill 说"获取相关的 Issue"

读取对应路径的文件。用户通常会直接传路径或 Issue 编号。
