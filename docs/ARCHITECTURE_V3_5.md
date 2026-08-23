# V3.5 工业时序数据质量与对账架构

## 目标

V3.5 位于 V3.4 数据对齐之后、健康基线与 Reliability/RCA 之前。它解决真实工业时序数据长期运行中的 Gap、异常值、累计量重置、传感器冻结、设备时钟漂移、迟到数据、班次边界和维护窗口问题。

```text
客户原始数据
   ↓
V3.3 字段映射验证
   ↓
V3.4 资产 / 时间 / 粒度对齐
   ↓
V3.5 时序数据质量 Gate
   ├─ Gap
   ├─ Outlier
   ├─ Counter Reset
   ├─ Frozen Sensor
   ├─ Clock Drift
   ├─ Late Arrival
   ├─ Shift Tag
   └─ Maintenance Window
   ↓
Reconciled Records
   ├─ quality_flags
   ├─ shift
   └─ baseline_eligible
   ↓
Condition / Baseline / Reliability / RCA
```

## 关键设计原则

1. 不静默修复原始值；先检测、打标、留痕。
2. 迟到数据和设备时钟漂移分开判断。
3. 维护窗口数据保留用于追溯，但默认排除健康基线。
4. Counter Reset 只对明确标记或名称表现为累计量的传感器启用。
5. 质量结果持久化，可用于 Pilot 验收和后续数据治理趋势分析。
