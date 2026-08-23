# V4.4 架构说明：团队协作与责任闭环

V4.4 在 V4.3 个人工作区和行动编排之上新增统一的团队协作责任层。该层只保存负责人、关注人、SLA、交接、评论和 @Mention 等协作元数据，不复制 RCA、CMMS、FMEA、Asset 的业务状态。

## 责任层模型

```text
Asset / RCA / Work Order / FMEA
              ↓
      Collaboration Item
      ├── Assignee
      ├── Watchers
      ├── SLA / Due At
      ├── Handoff Events
      └── Comments / @Mention
              ↓
      Team Accountability Board
```

## 状态边界

- RCA 的 `reviewed / resolved / closed` 仍由 RCA Case Store 管理。
- Work Order 的 `draft / approved / dispatched` 仍由 CMMS Candidate Store 管理。
- FMEA 的审批、退役仍由 FMEA Store 管理。
- Collaboration 只回答“谁负责、谁关注、什么时候完成、如何交接、沟通过什么”。

## SLA

系统实时根据 `due_at` 计算：

- `overdue`：已超过截止时间；
- `due_soon`：24 小时内到期；
- `on_track`：尚有超过 24 小时；
- `no_sla`：未设置 SLA。

## 多语言与 UI

团队协作页面沿用 V4.x 现代企业 UI 体系，新增文案全部进入 `zh-CN / en-US / de-DE / ja-JP` 四套资源包。
