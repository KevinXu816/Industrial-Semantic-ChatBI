# V4.7 架构：班次分析与运营报告

V4.7 新增只读 `OperationsReportService`，面向班长、运维主管和工厂经理生成班报/日报。服务从现有 Source of Truth 聚合：Operations Logbook、团队责任/SLA、RCA Case、CMMS Work Order、Escalation 与 Peer Benchmark。

```text
Shift / Daily Window
        ↓
Operations Logbook ─┐
Collaboration / SLA ─┤
RCA Cases ───────────┤
CMMS Work Orders ────┼→ OperationsReportService → Report Snapshot → UI / Markdown
Escalations ─────────┤
Peer Benchmark ──────┘
```

报告对象保存的是“某一时间窗口的审计型快照”，不会反向修改任何 RCA、CMMS、FMEA 或 Asset 生命周期。
