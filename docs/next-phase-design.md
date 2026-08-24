# 下一阶段产品与架构设计方案

> 本文档用于规划后续功能的实现顺序和架构设计，避免边开发边改方向。
> 目标功能：用户注册登录与数据隔离、攻略解析闭环、自然语言生成/调整行程。

---

## 1. 当前基础

- 已有 Supervisor 多 Agent 编排
- 已有 guide_parser / itinerary_gen / route_optimizer / fact_checker
- 已有 FastAPI + PostgreSQL + Alembic
- 已有 PostgresSaver 对话记忆，`thread_id = trip-{trip_id}`
- 已有前端行程创建、详情、地图、节点编辑、同天排序
- 已部署 Railway

当前缺少：

- 用户体系
- 用户级数据隔离
- 攻略解析结果的持久化与勾选确认
- 自然语言直接生成/调整行程的闭环
- 版本快照

---

## 2. 总体目标

```text
用户登录
  ↓
创建/管理自己的行程
  ↓
导入攻略 → 解析 → 候选列表 → 确认
  ↓
自然语言生成/调整行程
  ↓
地图可视化 + 节点编辑 + 时效校验
```

---

## 3. 模块设计

### 3.1 用户注册登录与数据隔离

#### 方案选择

| 方案 | 优点 | 缺点 |
|---|---|---|
| JWT + localStorage | 前后端分离简单，适合当前架构 | 需要处理 token 过期 |
| Session + Cookie | 服务端可控 | 前后端部署跨域稍复杂 |

推荐：**JWT + Bearer Token**。

#### 数据表

新增 `users`：

```text
id            UUID PK
email         String unique
password_hash String
nickname      String
created_at    DateTime
updated_at    DateTime
```

#### 鉴权方式

- `POST /api/v1/auth/register`
- `POST /api/v1/auth/login`
- `GET /api/v1/auth/me`
- 后端增加 `get_current_user` 依赖
- 所有业务接口校验当前用户

#### 数据隔离

- `trips` 增加/启用 `user_id`
- `fact_checks` 通过 trip 间接归属用户
- 后续 `source_documents`、`source_entities` 都带 `user_id`
- 查询时强制 `WHERE user_id = current_user.id`

---

### 3.2 攻略解析闭环

#### 当前现状

- 已有 `/sources/parse` 和 `/sources/merge`
- 但结果不落库，无法持久化、无法勾选确认

#### 新增数据表

`source_documents`：

```text
id            UUID PK
user_id       UUID FK
title         String
url           Text nullable
content       Text
created_at    DateTime
```

`source_entities`：

```text
id              UUID PK
source_id       UUID FK
poi_name        String
day_index       Integer
seq             Integer
lat             Float nullable
lng             Float nullable
suggested_duration_h Float nullable
best_time       String nullable
cost_estimate   String nullable
mention_count   Integer default 1
created_at      DateTime
```

#### 流程

```text
用户粘贴/导入攻略
  ↓
POST /sources
  ↓
保存 source_documents
  ↓
触发 guide_parser
  ↓
保存 source_entities
  ↓
前端展示候选列表
  ↓
用户勾选
  ↓
多源合并去重
  ↓
写入 itinerary_items
  ↓
生成/更新行程
```

#### 新增接口

```text
POST   /api/v1/sources
GET    /api/v1/sources
GET    /api/v1/sources/{source_id}
POST   /api/v1/sources/{source_id}/parse
GET    /api/v1/sources/{source_id}/entities
POST   /api/v1/sources/merge
POST   /api/v1/trips/{trip_id}/entities/import
```

---

### 3.3 自然语言生成/调整行程

#### 目标场景

- “帮我生成一个杭州 3 日游”
- “第二天改成去乌镇”
- “把第三天删掉”
- “调整一下顺序，把博物馆放上午”

#### 方案选择

| 方案 | 说明 | 推荐 |
|---|---|---|
| 全量替换 | Agent 每次返回完整行程，整体覆盖 | 简单但容易丢失用户手工修改 |
| Delta 更新 | Agent 返回要新增/修改/删除的节点 | 更安全，推荐 |

推荐：**结构化 Delta 更新**。

#### 交互流程

```text
用户文字
  ↓
POST /api/v1/chat
  ↓
Supervisor 识别意图
  ↓
调用 itinerary_gen / guide_parser / route_optimizer
  ↓
Agent 输出结构化 JSON
  ↓
服务层校验 + 应用到数据库
  ↓
生成版本快照
  ↓
前端刷新行程
```

#### Agent 输出示例

```json
{
  "action": "update_itinerary",
  "trip_id": "...",
  "changes": [
    {
      "type": "add",
      "day_index": 2,
      "poi_name": "乌镇",
      "city": "嘉兴",
      "start_time": "09:00:00"
    },
    {
      "type": "delete",
      "item_id": "existing-id"
    },
    {
      "type": "move",
      "item_id": "existing-id",
      "target_day_index": 1,
      "new_seq": 2
    }
  ]
}
```

#### 快照表

`itinerary_snapshots`：

```text
id         UUID PK
trip_id    UUID FK
version    Integer
payload    JSONB
created_at DateTime
```

每次修改行程后自动创建快照，支持后续“回滚/对比”。

---

### 3.4 前端改造

#### 用户模块

- 注册页
- 登录页
- 路由守卫
- 当前用户信息展示
- 退出登录

#### 攻略导入页

- 粘贴文本 / 输入 URL
- 展示解析后的候选 POI
- 勾选确认
- 合并多篇攻略

#### 行程对话页

- 行程详情页增加对话面板
- 用户可以输入自然语言修改行程
- 修改成功后自动刷新行程和地图

#### 版本历史

- 行程详情页增加“版本历史”入口
- 展示快照列表，支持回滚（后续）

---

## 4. 实现阶段规划

### Phase 1：用户注册登录与数据隔离
- users 表 + 鉴权接口
- trips.user_id 启用
- 前端登录/注册/路由守卫
- 目标：不同用户只能看到自己的行程

### Phase 2：攻略解析持久化闭环
- source_documents / source_entities 表
- sources 接口落库
- 前端候选列表 + 勾选
- 目标：用户可以导入攻略并选择 POI 生成行程

### Phase 3：自然语言生成/调整行程
- chat 接口支持结构化 Delta
- Agent 输出解析与校验
- 服务层应用变更
- 前端对话面板 + 自动刷新
- 目标：用户可以用一句话修改行程

### Phase 4：版本快照与回滚
- itinerary_snapshots
- 修改后自动快照
- 前端版本历史与回滚
- 目标：行程修改可追溯

### Phase 5（可选）：流式输出 / 异步任务
- chat 改成 SSE
- 行程生成异步化 + 进度条
- 解决外部 API 慢时的体验问题

---

## 5. 测试策略

每个 Phase 至少覆盖：

- 后端接口单元测试 / 集成测试
- 数据隔离测试：用户 A 不能访问用户 B 的数据
- Agent 结构化输出解析测试
- 前端 TypeScript / ESLint
- 关键路径人工验证

---

## 6. 风险与取舍

1. **LLM 结构化输出不稳定**
   - 需要 JSON Schema 校验
   - 失败时要求 Agent 重试或回退到人工确认

2. **自然语言修改可能覆盖用户手工编辑**
   - 采用 Delta 更新而不是全量替换
   - 每次修改前保存快照

3. **外部 API 超时**
   - 继续沿用降级策略
   - 后续异步化+进度条改善体验

4. **用户系统会扩大改动范围**
   - 建议严格按 Phase 推进，不一次做完

---

## 7. 面试可讲重点

- “我采用 JWT + 用户级数据隔离，所有资源查询强制 `user_id` 过滤。”
- “攻略解析不是一次性返回，而是落库形成候选列表，用户确认后再写入行程。”
- “自然语言修改行程采用结构化 Delta，而不是全量覆盖，避免破坏用户手工编辑。”
- “每次行程修改自动生成快照，为后续版本回滚打基础。”
