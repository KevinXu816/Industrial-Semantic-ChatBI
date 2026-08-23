# V3.6 架构说明：同工况可比基线与专业多语言界面

V3.6 在 V3.5 时序质量 Gate 之后增加 Operating Context 层。该层不修改原始工业数据，而是根据负荷、产量、环境温度、班次、产品类型和运行模式筛选历史可比样本，并计算工况归一化 KPI 偏差。

```text
V3.3 Mapping Validate
      ↓
V3.4 Asset / Time Alignment
      ↓
V3.5 Time-Series Quality
      ↓
V3.6 Operating Context
      ↓
Comparable Baseline
      ↓
Condition / Reliability / RCA
```

界面层新增独立国际化资源包：`zh-CN`、`en-US`、`de-DE`、`ja-JP`。运行时通过 `i18n.js` 加载语言资源，用户选择保存在浏览器本地。后端 API、字段名和行业技术标识不做语言改写，避免破坏集成契约。
