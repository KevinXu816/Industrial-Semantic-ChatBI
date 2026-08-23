# V3.8 架构说明：Peer Asset Decision Intelligence

V3.8 在 V3.7 同类设备对标基础上增加“可比性透明解释、异常优先级和 RCA 升级”闭环。

```text
Operating Context
      ↓
Peer Cluster
      ↓
Comparable / Excluded Explanation
      ↓
Peer Median / Percentile / Gap to Best
      ↓
Priority Score (P1–P4)
      ↓
RCA Candidate
      ↓
RCA Case
```

## 设计原则

1. 不同产品、运行模式、负荷区间或环境区间的设备不会进入同一 Peer 集合。
2. `baseline_eligible=false` 的数据不会进入对标样本。
3. 每一个被排除的 Peer 都保留明确原因，避免黑盒筛选。
4. 对标结果只作为 RCA 入口，不直接宣称根因。
5. 一键升级 RCA 时把对标结果作为结构化证据写入 Case。
