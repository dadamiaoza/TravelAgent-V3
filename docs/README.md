# 项目文档索引

> 本项目文档按用途分类维护，避免所有 Markdown 堆在 docs 根目录。

## 目录结构

```text
docs/
├── README.md
├── plans/              # 面向未来的方案、设计与规划
│   ├── next-phase-design.md
│   ├── ai-chat-collaboration-design.md
│   └── decisions.md
├── retrospectives/     # 已发生问题的复盘与开发记录
│   ├── development-notes.md
│   ├── factcheck-retrospective.md
│   └── scenic-routes-retrospective.md
├── adr/                # 架构决策记录
│   └── 0001-agent-api-integration.md
└── agents/             # Agent 协作相关的文档/约定
    ├── domain.md
    ├── issue-tracker.md
    └── triage-labels.md
```

## 文档说明

### 📐 方案与规划 `docs/plans/`

| 文档 | 内容 |
|---|---|
| [next-phase-design.md](./plans/next-phase-design.md) | 下一阶段产品与技术架构总规划 |
| [ai-chat-collaboration-design.md](./plans/ai-chat-collaboration-design.md) | 常驻 AI 对话、地图联动、长短期记忆方案 |
| [decisions.md](./plans/decisions.md) | 关键架构/技术决策汇总 |

### 🧾 复盘与开发记录 `docs/retrospectives/`

| 文档 | 内容 |
|---|---|
| [development-notes.md](./retrospectives/development-notes.md) | 开发过程中遇到的问题与解决方案记录 |
| [factcheck-retrospective.md](./retrospectives/factcheck-retrospective.md) | Fact Check 模块复盘 |
| [scenic-routes-retrospective.md](./retrospectives/scenic-routes-retrospective.md) | 城市/景区双模式路线规划复盘 |

### 🏛️ 架构决策 `docs/adr/`

| 文档 | 内容 |
|---|---|
| [0001-agent-api-integration.md](./adr/0001-agent-api-integration.md) | Agent-API 集成模式 |

### 🤖 Agent 文档 `docs/agents/`

| 文档 | 内容 |
|---|---|
| [domain.md](./agents/domain.md) | 领域文档与术语使用指南 |
| [issue-tracker.md](./agents/issue-tracker.md) | 本地 Issue 追踪器约定 |
| [triage-labels.md](./agents/triage-labels.md) | Issue Triage 标签定义 |