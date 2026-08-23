# V3.7 架构说明：自动工况分群与同类设备对标

V3.7 在 V3.6 单设备历史同工况基线之上增加跨设备 Peer Benchmark。平台先按产品类型、运行模式、负荷区间和环境温度区间形成可解释工况簇，再在簇内比较单位能耗等 KPI。

## 处理链

```text
可信时序 → Operating Context → Peer Cluster → Benchmark → RCA Candidate
```

对标结果保留当前值、Peer 中位数、百分位、最佳 Peer、差距和可比样本，避免跨产品或跨负荷直接比较。
