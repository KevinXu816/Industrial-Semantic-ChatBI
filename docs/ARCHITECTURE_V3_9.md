# V3.9 架构说明：Peer Benchmark 维护效果验证闭环

V3.9 在 V3.8 的 Peer Benchmark → RCA 基础上增加维护后效果验证服务。验证不会改变原始 Benchmark，而是生成独立 Outcome 记录。

```text
Peer Benchmark Assessment
        ↓
RCA Case
        ↓
Engineer Resolve / Close
        ↓
Maintenance Action
        ↓
Post-maintenance Samples
        ↓
Same Operating Cluster Filter
        ↓
Improvement / Peer Range Verification
        ↓
Peer Benchmark Outcome
```

正式 `verified_success=true` 需要同时满足：验证样本数量达到策略要求、改善幅度达到目标、维护后回到 Peer 正常偏差范围、关联 RCA 已处于 `resolved` 或 `closed`。
