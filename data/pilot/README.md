> **V3.8 同步说明：** 当前文档已按 V3.8 实际代码与部署方式更新；界面新增文案继续使用四语言资源包。

# Pilot 示例数据说明

本目录用于空压机“能效异常 + 预测维修”Pilot。

- `air_compressor_timeseries.json`：合成时序数据，前半段相对稳定，后半段逐步模拟过滤器阻力增加，并带来压差、温度、功率和单位能耗恶化。该数据仅用于流程演示，不代表真实设备故障模型。
- `customer_mapping.example.json`：客户 MES、IoT/Historian、CMMS 字段到平台标准字段的映射示例。现场实施时应根据客户真实字段修改，并先通过 V3.3 客户样例验证和 Dry-run，再审批 Binding。

真实 Pilot 建议优先使用 20～100 条脱敏样例验证字段映射，再接入 30～90 天历史数据。任何密码、Token、API Key 都不应写入本目录，应使用 Secret Reference。

## V3.5 时序数据质量建议

真实 Pilot 数据在完成字段映射和资产/时间对齐后，建议先调用 `/pilot/data-quality/assess`。重点检查 Gap、冻结传感器、累计量重置、设备时钟漂移、迟到数据和维护窗口。只有 `ready_for_baseline=true` 的数据才建议用于建立健康基线；被标记为维护窗口的数据保留用于追溯，但不进入正常基线。


## V3.6 同工况基线建议

通过 V3.5 时序数据质量检查后，建议为历史记录补充负荷、产量、环境温度、班次、产品类型和运行模式，再调用 `/pilot/operating-context/assess`。只有 `ready_for_rca=true` 的比较结果才建议用于能效异常和 RCA 判断，避免不同工况之间直接比较。
