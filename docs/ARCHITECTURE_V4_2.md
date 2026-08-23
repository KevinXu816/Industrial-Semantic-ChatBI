# V4.2 架构说明：角色化工作台与上下文行动编排

V4.2 在 V4.1 全局搜索与统一待办的基础上增加个人工作区层。核心原则是：业务事实继续来自 Asset、RCA、FMEA、CMMS、Model、Edge Agent 等现有 Source of Truth；V4.2 只持久化用户偏好，如最近访问、收藏和固定快捷入口。

## 主要能力

- 角色化今日重点：可靠性工程师、维护计划员、运行人员使用不同的优先排序。
- 最近访问与收藏：存储到 `workspace_preferences`，不复制业务状态。
- 上下文导航：以 Asset/RCA 为上下文，快速跳转资产、RCA、Peer Benchmark 和维护工单。
- 深链操作：统一搜索、Inbox、个人工作区都可以携带资产/RCA 上下文进入目标模块。

## 新增 API

- `GET /workspace/personalized`
- `GET /workspace/preferences`
- `POST /workspace/preferences`
- `POST /workspace/preferences/recent`
- `POST /workspace/preferences/favorite`
- `GET /workspace/context`
