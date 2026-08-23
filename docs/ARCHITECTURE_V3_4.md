# V3.4 真实工业数据对齐与可信化架构

V3.4 不增加新的业务智能模块，重点解决真实 Pilot 数据进入 Reliability/RCA 前的语义和时间对齐问题。

## 核心链路

客户 MES / IoT / CMMS → Data Binding → V3.3 样例验证 → V3.4 对齐与可信化 → Integration Runtime → Reliability / RCA。

## 新增治理能力

- **设备 ID 统一**：通过 Asset Alias Registry 将 MES、CMMS、IoT 的设备编码映射到平台 canonical `asset_id`。
- **时间统一**：ISO 8601/秒/毫秒时间戳统一转换为 UTC；非 UTC 的无 offset 时间拒绝猜测。
- **粒度对齐**：将 tall-series 按可配置分钟 Bucket 聚合，便于 MES 与 IoT 对齐。
- **安全单位能耗**：仅在产量大于 0 且设备处于运行负荷时计算 `active_power / production_output`。
- **停机隔离**：低负荷或零产量 Bucket 不进入健康 Baseline 候选集。
- **传感器完整性**：检查 Pilot 必需信号是否齐全。
- **Failure Code 标准化**：将 CMMS 厂商/工厂代码映射到统一 canonical failure code。

## 设计边界

V3.4 只做标准化、诊断和治理元数据，不绕过 Data Binding 审批，不直接替代客户 Historian/MES/CMMS 的采集适配器。
