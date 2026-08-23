# V4.5 架构：SLA 策略、升级机制与值班协同

V4.5 在 V4.4 团队责任层之上增加运行治理，不改变 RCA、CMMS、FMEA 的领域状态机。

```text
Collaboration Item
    ↓
SLA Policy
    ↓
SLA State: on_track / due_soon / overdue
    ↓
Escalation Evaluation
    ├─ 固定 escalation recipient
    └─ 当前 On-call 回退
    ↓
Notification Intent
    ├─ in_app
    ├─ email
    ├─ teams
    ├─ slack
    └─ webhook
    ↓
External Adapter
```

核心原则：平台只生成受治理的通知意图，外部 Adapter 才负责真正发送；升级不会绕过 RCA/CMMS/FMEA 审批流程。
