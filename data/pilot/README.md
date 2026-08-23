# Pilot 示例数据说明

本目录用于空压机“能效异常 + 预测维修”Pilot。

- `air_compressor_timeseries.json`：合成时序数据，前半段相对稳定，后半段逐步模拟过滤器阻力增加，并带来压差、温度、功率和单位能耗恶化。该数据仅用于流程演示，不代表真实设备故障模型。
- `customer_mapping.example.json`：客户 MES、IoT/Historian、CMMS 字段到平台标准字段的映射示例。现场实施时应根据客户真实字段修改，并先通过 V3.3 客户样例验证和 Dry-run，再审批 Binding。

真实 Pilot 建议优先使用 20～100 条脱敏样例验证字段映射，再接入 30～90 天历史数据。任何密码、Token、API Key 都不应写入本目录，应使用 Secret Reference。
