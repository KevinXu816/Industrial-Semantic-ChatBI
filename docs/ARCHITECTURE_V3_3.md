# V3.3 架构说明：客户真实数据验证门

V3.3 在客户数据进入正式 Integration Runtime 之前增加一个只读验证门：

```text
客户脱敏样例
   ↓
Data Binding Mapping
   ↓
Customer Data Validator
   ├── 源字段存在性
   ├── 转换成功率
   ├── 空值率
   ├── Schema / Drift
   └── 时间字段候选
   ↓
Dry-run Preview（不写入）
   ↓
人工审核 / Binding Approve
   ↓
Schema / Watermark / Quality Rule
   ↓
Integration Runtime
```

该设计复用已有 Data Binding 和 Integration Runtime，不建立第二套数据写入路径。验证结果只作为实施与治理决策依据，真正业务写入仍要求 Binding 已批准。
