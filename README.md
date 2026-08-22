# Industrial Semantic Intelligence Platform

> **V2.9 Observability & SRE Control Plane** — W3C trace context, HTTP latency/error metrics, dependency health, SLOs, alert rules/incidents, Prometheus exposition, and an SRE operations UI. The UI version is sourced from `/health` and displays **V2.9.0** consistently.

## V2.9 highlights

- Unified `EnterpriseAuditEvent`: actor, tenant/site scope, resource, action, decision, status, before/after, provenance, correlation ID and timestamp.
- HTTP `X-Correlation-ID` propagation plus semantic-query child events for traceable request chains.
- Idempotent adapters normalize Authentication, Access, Secret, Runtime Query, Connector and DLQ history into the audit center.
- Built-in violation generation for denied/failed governed operations plus custom compliance match policies.
- Audit search, correlation trace, JSON/CSV export and configurable retention with dry-run enforcement.
- **审计与合规** UI for event search, policy/violation overview and retention configuration.

V2.7 Secret/Credential Management, V2.6 Authentication/SSO, and V2.5 Multi-Tenant Governance remain fully compatible.

## V2.5 Enterprise Identity & Multi-Tenant Governance

Tenant/Organization/Site hierarchy, governed Principals, resource-scoped Asset/Connector/Edge Agent/RCA/FMEA access, cross-tenant ConnectorBatch isolation, and append-only access audit.

## V2.4 highlights

- `draft → approved → retired` Connector lifecycle tied to approved Data Bindings.
- Standard `ConnectorBatch v1` carrying source, schema, cursor, records and diagnostics.
- Batch-level idempotency prevents duplicate domain writes on edge/network retries.
- Edge Agent registry with site, version, capabilities, heartbeat and stale detection.
- SDK contracts for InfluxDB, JDBC, REST, MQTT and File adapters without embedding vendor credentials in the platform core.
- Connector cursor/batch lineage and Operations Health summaries.

Key endpoints: `/connectors`, `/connectors/contract`, `/edge-agents`, `/edge-agents/{id}/heartbeat`, `/edge-agents/health`, `/integration/connector-batches`.

> **V2.1 Reliability Workflow UX** — Plant→Line→Asset tree navigation, selectable 7/30/90-day Health/Risk trends, a dedicated RCA Case workflow with Evidence Review and Engineer Confirm/Resolve/Close actions, plus maintenance linkage. UI version is sourced from `/health` and displays **V2.1.0** consistently.

## V1.9 Asset Reliability Cockpit

V1.9 turns the accumulated reliability capabilities into an engineer-facing asset operations view without duplicating domain state. Asset Registry owns only master data, hierarchy, components and sensor bindings; operational facts remain sourced from Reliability, RCA, CMMS, FMEA and Model Registry services.

Key endpoints: `/assets`, `/assets/hierarchy`, `/assets/{id}/components`, `/assets/{id}/sensors`, `/assets/{id}/cockpit`, `/reliability/fleet`.

## V1.9 highlights

- First-class Asset Registry with parent/child hierarchy.
- Component Registry and sensor-to-asset/component bindings.
- Fleet reliability ranking by latest Dynamic Risk.
- Single Asset Cockpit aggregating Asset Health, trend, Top Failure Mode, RUL, open RCA cases and pending CMMS candidates.
- Champion/Challenger model visibility in the same reliability context.
- New `资产可靠性` UI with fleet ranking and drill-down cockpit.
- Version number remains centralized in `app/version.py` and displayed from `/health`.

> **V1.8 Condition Model Platform & Governed Predictive Models** — reusable equipment templates, auditable feature pipelines and a versioned model registry on top of the V1.6 predictive-maintenance chain.

## V1.8 Model Evaluation & Production Monitoring

V1.8 adds governed model dataset registration, offline evaluation metrics, Champion/Challenger deployment slots, promotion/rollback, feature-drift monitoring, and a Model Operations UI. The UI reads the application version from `/health` and displays it consistently in the sidebar, top bar, system management page, and graph editor.


## V1.8 highlights

- Built-in Condition Model Templates for bearing, pump, compressor, motor, fan, PCS and battery assets.
- Templates declare recommended sensors and feature definitions, then generate normal governed Condition Indicators.
- Persisted Feature Pipeline jobs/runs for auditable `Raw Series → Features → Condition Indicators` execution.
- Governed Model Registry for rule/statistical/Darts/ONNX/external model versions and artifact references.
- Only approved model versions can execute inference; every run records model ID/version/type.
- Darts/ONNX are explicit adapter contracts in the core package, avoiding fake inference when a runtime adapter is absent.

Key endpoints: `/condition-models`, `/condition-models/{id}/apply`, `/feature-pipelines`, `/feature-pipelines/{id}/run`, `/models`, `/models/{id}/approve`, `/models/{id}/infer`.

## V1.6 Condition Analytics & Predictive Maintenance Integration

## V1.6 highlights

- Governed Condition Indicator Registry (`sensor + feature + window + threshold/baseline + weight`).
- Deterministic time-series feature engine: mean/std/min/max/range/RMS/slope/kurtosis/crest factor and rolling windows.
- Asset/indicator baseline profiles and threshold/baseline condition-risk normalization.
- End-to-end `Raw Time Series → Condition Indicators → V1.5 Reliability Assessment`.
- Pluggable RUL adapter contract with a transparent linear health-trend reference adapter.
- Maintenance decision service and vendor-neutral CMMS work-order candidate/dispatch contract.
- RUL remains explicitly an engineering estimate unless a calibrated external model is supplied.

Key endpoints: `/condition/definitions`, `/condition/baselines`, `/condition/analyze`, `/reliability/assess-timeseries`, `/predictive/rul`, `/maintenance/recommend`, `/cmms/work-order-candidates`.

## V1.5 Reliability Intelligence & Predictive Maintenance

> **V1.5 Reliability Intelligence & Predictive Maintenance** — explainable dynamic failure risk, condition indicators, asset health, maintenance priority, while preserving governed FMEA and RCA.

## V1.5 highlights

- Dynamic risk combines approved FMEA risk + condition + anomaly + failure history.
- Governed FailureMode↔Sensor mappings and normalized condition indicators.
- Asset Health Score and health trend from persisted reliability assessments.
- Maintenance priority (`P1-critical`..`P4-low`) and inspection recommendation.
- Scores are explicit decision-support indicators, not calibrated failure probabilities.

Key endpoints: `/reliability/assess`, `/reliability/assets/{asset}/health`, `/reliability/risk-ranking`, `/reliability/sensor-mappings`.

## V1.4 Industrial Failure Model & FMEA Studio

> **V1.4 Industrial Failure Model & FMEA Studio** — governed FMEA reliability modeling with S/O/D risk scoring, RPN prioritization, asset/component failure graphs, and graph-connected RCA.


## V1.4 highlights

- First-class FMEA records with `Severity / Occurrence / Detectability / RPN / Criticality`.
- Reliability hierarchy: `Asset → Component → FailureMode → Cause / Effect / Detection / Action`.
- Only approved FMEA records are projected into the Industrial Knowledge Graph.
- Risk ranking API for reliability and maintenance prioritization.
- FMEA graph provenance is preserved as `fmea:<id>@<version>`.

Key endpoints: `/fmea`, `/fmea/risk-ranking`, `/fmea/{id}/approve`, `/fmea/{id}/retire`.


## V1.3 Industrial Knowledge Graph & Causal Model

V1.3 keeps the V1.2 governed learning loop and adds an executable industrial knowledge graph:

- Unified nodes for `FailureMode / Component / Alarm / SensorPattern / MaintenanceAction / Knowledge / RCACase`
- Governed relations: `CAUSED_BY / INDICATED_BY / DETECTED_BY / RESOLVED_BY / SUPPORTED_BY`
- Correlation/time evidence remains explicitly non-causal (`CORRELATED_WITH / PRECEDES`)
- Approved FMEA/SOP/knowledge automatically promotes graph facts; candidate knowledge never does
- Resolved RCA cases with confirmed root cause become graph evidence
- Graph-based failure-mode ranking is fused with the existing deterministic RCA evidence score
- `causal_claim_supported` tells clients whether a strong causal edge exists

Key V1.3 endpoints: `/knowledge-graph`, `/knowledge-graph/reason`, `/knowledge-graph/failure-modes/{id}/explain`, and graph ingestion endpoints.

## V1.2 Knowledge Quality & Learning Loop

V1.2 keeps all V1.1 knowledge backends and adds a governed learning loop:

- Knowledge lifecycle: `draft/candidate → approved → superseded/retired`
- Only approved knowledge is used by default retrieval
- Stable chunk lineage with parent citation/provenance
- Offline retrieval evaluation with Recall@K and MRR
- Similar confirmed RCA case search
- Human-feedback-derived, bounded hypothesis calibration
- Resolved RCA Case → Knowledge Candidate → Approval → reusable industrial knowledge

Key V1.2 endpoints include `/knowledge/workflow/*`, `/knowledge/evaluate`, `/rca/similar-cases`, `/rca/calibration`, and RCA-to-knowledge promotion APIs.

## V1.1 Knowledge Infrastructure

V1.1 keeps the V1.0 Enterprise Pilot contracts and adds a productized knowledge plane:

```text
FMEA / SOP / Manual / Maintenance Report
            ↓
Version + Digest + Chunking
            ↓
Hybrid Retrieval
Lexical + Vector + Metadata Filter
            ↓
Qdrant / pgvector / Local
            ↓
RCA Evidence + Historical RCA Cases
            ↓
Hypothesis Ranking + Citation
```

The default `local` backend has no additional dependency. Enterprise deployments can set `KNOWLEDGE_BACKEND=qdrant` or `KNOWLEDGE_BACKEND=pgvector`. Confirmed RCA cases become a governed knowledge source and are returned with stable case provenance. See `docs/ARCHITECTURE_V1_1.md`.

### Version evolution

- **V0.5** — Generic Subject / ontology-driven semantic query engine
- **V0.6** — Multi-Metric / Dimension / Cross-Entity Filter / Comparison / Doris Physical Plan
- **V0.7** — Enterprise Governance / Cost Control / Semantic Version & Lineage / RCA Evidence Graph
- **V0.8** — Time-Series Analytics / Event Correlation / Knowledge Evidence / Hypothesis Ranking / Doris EXPLAIN
- **V0.9** — Temporal Chain / Sensor Lag Correlation / Operating Baseline / Versioned Citation / RCA Feedback
- **V1.0** — PostgreSQL Repository / RCA Case Management / Runtime Telemetry / Enterprise Pilot deployment
- **V1.1** — Knowledge Ingestion / Hybrid Retrieval / Qdrant & pgvector adapters / Historical RCA Case Retrieval
- **V1.2** — Knowledge Approval Workflow / Retrieval Evaluation / RCA Similarity / Learning Feedback Loop
- **V1.3** — Industrial Knowledge Graph / Governed Causal Relations / Graph-based RCA Reasoning
- **V1.4** — Industrial Failure Model / FMEA Studio / RPN Risk Prioritization / Asset-Component Failure Graph
- **V1.5** — Reliability Intelligence / Dynamic Risk / Asset Health / Sensor Mapping / Maintenance Priority
- **V1.6** — Condition Indicator Registry / Time-Series Features / Baseline / RUL Adapter / CMMS Contract
- **V1.8** — Condition Model Templates / Feature Pipeline / Governed Predictive Model Registry

## 应用场景

- **工业设备能耗分析** — 查询设备能耗趋势、单位产量能耗、峰值负荷等指标
- **生产异常诊断** — 关联告警事件、维修工单，自动定位能耗异常根因
- **跨系统数据联邦** — 统一查询分散在 MES（MySQL）、CMMS（PostgreSQL）、数据仓库（Doris）中的数据
- **语义模型管理** — 通过 UI 管理本体、指标、数据源映射，图形化编辑实体关系
- **能源管理** — 电表读数、费用统计、碳排放追踪
- **仓储物流** — 库存查询、出入库分析

## 系统架构

```
用户自然语言提问
       |
+------------------------------------------+
|  语义解析层                               |
|  Rules Engine / LLM Parser              |---> SemanticIntent
|  (LLM 只解析意图，不生成 SQL)             |
|  + 置信度评估 + 不确定性表达              |
+------------------------------------------+
       |
+------------------------------------------+
|  语义模型层                               |
|  Industrial Ontology + Aliases          |---> 逻辑实体 -> 物理表列映射
|  Metric Registry + Enums                |---> 指标/同义词/枚举值
|  JOIN Path Finder                       |---> 多跳关系自动推导
+------------------------------------------+
       |
+------------------------------------------+
|  查询治理层                               |
|  PolicyEngine + Query Cost             |---> RBAC/RLS/列权限/成本准入
|  QueryPlanner + Cache                   |---> 基于本体生成 SQL + 缓存
|  AST SQL Guardrail                      |---> 只读 + 表白名单 + 时间过滤
+------------------------------------------+
       |
+------------------------------------------+
|  执行层                                  |
|  Doris / MySQL / PostgreSQL             |---> 多数据源联邦查询
|  Health Monitor                         |---> 数据源连通性监控
+------------------------------------------+
       |
+------------------------------------------+
|  回答生成                                 |
|  Template / LLM Composer                |---> 结合数据生成分析回答
|  + 图表可视化 + 证据链溯源               |
+------------------------------------------+
       |
+------------------------------------------+
|  可观测性                                 |
|  Query Stats / Audit Log / Feedback     |---> 性能统计/审计/满意度
+------------------------------------------+
```

## 功能模块

### 💬 智能问答
- 自然语言输入，自动解析设备编码、指标同义词、时间窗口
- **多轮对话** — 支持 session 上下文，连续追问
- **图表可视化** — 趋势数据自动渲染 SVG 折线图
- **SQL 预览确认** — 可先查看 SQL 计划再决定是否执行
- **问题联想推荐** — 输入时自动提示相关问题
- **置信度评估** — 每次回答附带解析置信度，低信心时明确告知
- **证据链溯源** — 展示回答依据的数据源、SQL、JOIN 路径
- **查询缓存** — 相同问题 5 分钟内直接返回缓存，减少数据库负载
- **用户反馈** — 👍👎 按钮记录满意度，持续优化

### 🤖 大模型配置
- 支持 OpenAI / Azure OpenAI / Ollama / vLLM / DeepSeek 等 OpenAI 兼容 API
- 启用后驱动语义解析和对话回答
- 未启用时自动降级为规则引擎 + 模板回答
- UI 上一键测试连接

### 🗄️ 数据源管理
- 支持 Apache Doris、MySQL、PostgreSQL、EXCEL、API
- UI 配置连接参数、测试连通性
- 对数据源执行元数据扫描
- **数据预览** — 预览任意表的前 N 行数据
- **健康监控** — 自动检测所有数据源连通状态

### 🔗 语义图谱
- 可视化实体卡片（颜色编码 + 字段映射表格）
- UI 新建/编辑实体，动态增删字段行
- **图形化关系编辑** — 独立画布，拖拽节点、点击连线、右键菜单修改/删除
- **JOIN 路径自动推导** — BFS 发现实体间最短关联路径

### 📊 指标注册表
- 管理指标定义（表达式、单位、同义词）
- UI 创建/编辑/删除
- 候选模型审核通过时自动合并

### 🔍 元数据扫描
- **自动扫描** — 连接数据源，自动发现表结构并生成候选语义模型
- **手动添加** — 表单手动创建候选模型

### 📋 候选模型审核
- Tab 分类：待审核 / 已通过 / 已驳回
- 批准后自动合并到运行时本体和指标注册表
- 显示审核备注

### ⚙️ 系统管理
- **仪表盘** — 实体数、指标数、数据源数、查询成功率、平均耗时、满意度
- **失败问题列表** — 最近解析失败的问题，帮助优化语义模型
- **配置导出** — 一键导出全部配置为 JSON（密码自动脱敏）
- **配置导入** — 上传 JSON 恢复配置
- **审计日志** — 记录所有操作（谁、何时、做了什么）
- **缓存管理** — 查看/清空查询缓存

### 🏭 行业模板
- 制造业通用、能源管理、仓储物流三套预置模板
- 卡片浏览和详情抽屉：查看实体、关系、指标、别名
- 支持结构化新建/编辑模板，以及选择或拖放 JSON、YAML、YML 文件后预览创建
- 内置模板可编辑并恢复预置版本；自定义模板可编辑和删除
- 应用前展示新增/跳过影响，确认后安全合并，不覆盖任何同名配置
- 用户模板和内置模板覆盖保存在 `data/industry_templates.json`

模板文件示例：

```yaml
id: automotive-parts
name: 汽车零部件
description: 汽车零部件行业语义模板
entities:
  Machine:
    description: 生产设备
    properties:
      machine_id:
        type: string
relationships: []
metrics: {}
aliases:
  设备编号: machine_id
```

模板 ID 只允许小写字母、数字和连字符；上传文件必须使用 UTF-8 编码，最大 2 MiB。

### 🏷️ 字段别名与枚举映射
- 统一不同系统的字段叫法（设备编号/资产编号 → machine_code）
- 枚举值业务含义（machine_type="A" → "空压机"）


### 🧠 工业知识基础设施（V1.1）
- FMEA / SOP / Manual / 维修报告文档导入
- 文档版本、SHA-256 digest、稳定 chunk_id 与 citation/provenance
- Local Hybrid Retrieval：关键词 + deterministic vector
- 可选 Qdrant / pgvector 后端，不改变 RCA 上层接口
- 已确认 RCA Case 自动成为可复用历史知识
- API：`/knowledge/ingest`、`/knowledge/documents`、`/knowledge/search`、`/knowledge/stats`、`/knowledge/rca-cases/search`

## 技术方案

| 层面 | 技术选型 |
|------|---------|
| 后端框架 | FastAPI + Uvicorn |
| 数据模型 | Pydantic v2 |
| 配置格式 | YAML（本体/指标） + JSON（运行时数据） |
| 数据库驱动 | PyMySQL（Doris/MySQL），psycopg2（PostgreSQL 可选） |
| 语义解析 | 规则引擎（正则 + 同义词） / OpenAI-compatible LLM |
| 路径发现 | BFS 图遍历（JoinPathFinder） |
| SQL 安全 | Semantic Policy + AST/Structural Guardrail（只读、表白名单、时间边界） |
| 知识检索 | Local Hybrid / Qdrant / pgvector（可选） |
| 缓存 | 治理上下文 SHA-256 key + TTL 淘汰 |
| 前端 | 单页 HTML + 原生 JS + SVG 图表（无框架依赖） |
| 部署 | Python 3.10+，pip install 即可运行 |

## 安装与运行

### 环境要求

- Python 3.10+
- pip

### 安装

```bash
git clone https://github.com/KevinXu816/Industrial-Semantic-ChatBI.git
cd Industrial-Semantic-ChatBI
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 启动

```bash
uvicorn app.main:app --reload --port 8000
```

访问 http://127.0.0.1:8000/ 打开 Web UI，API 文档在 http://127.0.0.1:8000/docs

默认使用 Mock 模式，无需连接真实数据库即可体验完整流程。

### 快速开始

1. 打开 Web UI
2. (可选) 配置大模型：大模型配置 → 填写 API 地址 → 启用
3. (可选) 管理或应用行业模板：行业模板 → 查看详情 / 上传 / 新建 / 应用
4. 配置数据源：数据源管理 → 新建 → 填写连接参数 → 测试 → 扫描
5. 审核候选模型：候选模型审核 → 批准
6. 开始提问：智能问答 → 输入自然语言问题

### 配置大模型

示例（Ollama 本地）：
```
API 地址: http://localhost:11434/v1
模型名称: qwen2.5
```

示例（OpenAI）：
```
API 地址: https://api.openai.com/v1
模型名称: gpt-4o
API Key: sk-...
```

### 连接数据源（环境变量方式）

```bash
export METADATA_MODE=doris
export DORIS_HOST=127.0.0.1
export DORIS_PORT=9030
export DORIS_USER=root
export DORIS_PASSWORD='password'
```

## 项目结构

```
app/
  main.py                 # FastAPI 应用入口 + 全部路由
  semantic.py             # 语义注册中心（本体 + 指标 + 解析器）
  planner.py              # 基于本体的 SQL 查询规划器
  guardrail.py            # SQL 安全护栏
  executor.py             # 查询执行器（Mock / Doris）
  answer.py               # 回答生成器（模板 / LLM）
  llm_service.py          # LLM 服务（OpenAI 兼容接口）
  llm_planner.py          # LLM 语义解析器
  metadata.py             # 元数据扫描器（Mock / Doris）
  datasource.py           # 多数据源配置与扫描
  candidate_generator.py  # 候选语义模型生成
  review_store.py         # 候选模型审核存储
  chat_session.py         # 多轮对话会话 + 反馈存储
  join_path.py            # JOIN 路径 BFS 发现
  cache_audit.py          # 查询缓存 + 审计日志
  observability.py        # 查询统计 + 失败追踪
  config_manager.py       # 配置导入导出 + 密码加密
  field_aliases.py        # 字段别名 + 枚举值映射
  templates.py            # 行业模板（制造/能源/物流）
  template_models.py      # 行业模板校验模型
  template_store.py       # 内置覆盖与自定义模板持久化
  template_apply.py       # 模板应用预览与安全合并
  models.py               # Pydantic 数据模型
  static/
    index.html            # 主 Web UI
    graph-editor.html     # 图形化关系编辑器
    template-management.css # 行业模板管理样式
    template-management.js  # 行业模板管理交互
config/
  ontology.yaml           # 基础工业本体
  metrics.yaml            # 基础指标定义
data/
  semantic_reviews.json   # 候选模型审核数据
  datasources.json        # 数据源配置
  llm_config.json         # LLM 配置
  chat_sessions.json      # 对话历史
  feedback.json           # 用户反馈
  query_stats.json        # 查询统计
  query_cache.json        # 查询缓存
  audit_log.json          # 审计日志
  field_aliases.json      # 字段别名
  industry_templates.json # 用户模板与内置模板覆盖（首次保存后生成）
```

## API 概览

### 对话
| 方法 | 路径 | 说明 |
|------|------|------|
| POST | /chat | 完整对话（解析->规划->执行->回答） |
| GET | /chat/sessions | 对话历史列表 |
| GET | /chat/session/{id} | 查看会话详情 |
| POST | /chat/feedback | 提交反馈 |
| GET | /chat/feedback/stats | 反馈统计 |
| GET | /suggestions | 问题推荐联想 |

### 语义模型
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /ontology | 完整本体 |
| GET | /semantic/graph | 语义关系图 |
| PUT | /ontology/entities/{name} | 新建/编辑实体 |
| DELETE | /ontology/entities/{name} | 删除实体 |
| PUT | /ontology/relationships | 更新关系 |
| GET | /ontology/join-path | JOIN 路径推导 |
| POST | /semantic/resolve | 语义解析 |
| POST | /plan | 生成 SQL 计划 |

### 指标与别名
| 方法 | 路径 | 说明 |
|------|------|------|
| GET/POST/PUT/DELETE | /metrics | 指标 CRUD |
| GET/PUT | /aliases | 字段别名 |
| PUT/DELETE | /enums/{entity_field} | 枚举值映射 |

### 数据源
| 方法 | 路径 | 说明 |
|------|------|------|
| GET/POST/PUT/DELETE | /datasources | 数据源 CRUD |
| POST | /datasources/{id}/test | 测试连接 |
| POST | /datasources/{id}/scan | 元数据扫描 |
| POST | /datasources/{id}/preview | 数据预览 |
| GET | /datasources/health | 健康检查 |

### 候选模型
| 方法 | 路径 | 说明 |
|------|------|------|
| GET/POST | /semantic/candidates | 列表/手动创建 |
| POST | /semantic/candidates/{id}/review | 审核 |
| POST | /semantic/merge | 合并到本体 |
| POST | /metadata/scan | Mock 扫描 |

### LLM 与模板
| 方法 | 路径 | 说明 |
|------|------|------|
| GET/PUT | /llm/config | 大模型配置 |
| POST | /llm/test | 测试连接 |
| GET | /templates | 行业模板列表 |
| POST | /templates/validate | 解析并校验 JSON/YAML 模板，不保存 |
| POST | /templates | 创建自定义模板 |
| GET | /templates/{id} | 模板详情 |
| PUT | /templates/{id} | 编辑模板 |
| DELETE | /templates/{id} | 删除自定义模板 |
| POST | /templates/{id}/reset | 恢复内置模板预置版本 |
| GET | /templates/{id}/apply-preview | 预览安全合并影响 |
| POST | /templates/{id}/apply | 确认应用模板 |

### 系统管理
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /admin/overview | 系统仪表盘 |
| GET | /admin/stats | 查询统计 |
| GET | /admin/failures | 失败问题 |
| GET | /admin/audit | 审计日志 |
| GET | /admin/cache | 缓存状态 |
| POST | /admin/cache/clear | 清空缓存 |
| GET | /admin/export | 导出配置 |
| POST | /admin/import | 导入配置 |

## Smoke Test

```bash
pip install -r requirements-dev.txt
python -m unittest discover -s tests -p 'test_*.py' -v
python -m tests.smoke_test
```

## Screenshot 系统截图

### System

![System](docs/images/system.png)

### ChatBI

![ChatBI](docs/images/chat.png)

### Entity

![Entity](docs/images/entity.png)

### Relation

![Relation](docs/images/relation.png)

### Metric

![Metric](docs/images/metric.png)

### Template

![Template](docs/images/template.png)


## 作者

| | |
|---|---|
| **开发者** | 良晞 |
| **邮箱** | xhongliang@163.com |
| **GitHub** | [@KevinXu816](https://github.com/KevinXu816) |

如果这个项目对你有帮助，欢迎 ⭐ Star 支持，也欢迎提 Issue 和 PR 一起完善。

## License

[Apache License 2.0](LICENSE) — 可自由使用、修改和分发，包括商业用途。

---

## V0.4 — Semantic Execution Core Upgrade

This version introduces a governed metric dependency graph, ontology-driven required-entity/JOIN-path planning, field-level semantic override merging, an evidence-first RCA scaffold, and stricter read-only SQL guardrails.

See [`docs/ARCHITECTURE_V0_4.md`](docs/ARCHITECTURE_V0_4.md) for the architecture and next-step roadmap.

---

## V0.6 — Generic Semantic Analytics Engine

V0.6 extends the generic semantic engine with multi-metric queries, ontology-driven dimensions/grouping, cross-entity filters, previous-period comparisons, and Doris physical-plan metadata.

Example semantic request:

```json
{
  "raw_question": "F01工厂各产线最近30天能耗、产量和单位能耗与上期相比",
  "subject": {"entity": "Factory", "reference": "F01"},
  "metrics": ["energy_consumption", "production_output", "specific_energy_consumption"],
  "dimensions": ["ProductionLine.line_name"],
  "time_range": {"type": "relative", "value": 30, "unit": "day"},
  "comparison": {"type": "previous_period"},
  "analysis_mode": "descriptive"
}
```

Use `POST /plan/semantic` to compile an explicit governed `SemanticIntent` directly. See [`docs/ARCHITECTURE_V0_6.md`](docs/ARCHITECTURE_V0_6.md) and [`docs/V0_6_CHANGELOG.md`](docs/V0_6_CHANGELOG.md).


## V1.0 Enterprise Pilot

V1.0 turns the governed semantic/RCA engine into a deployable enterprise pilot.

- Pluggable persistence: local JSON by default, PostgreSQL for pilot/production-like deployments.
- RCA Case Management: open → analyzed → reviewed → resolved, with durable history.
- Human review and confirmed root-cause capture.
- Durable runtime query telemetry and operations health endpoints.
- Enterprise pilot Docker Compose with PostgreSQL.

### PostgreSQL pilot

```bash
pip install -e '.[postgres,governance]'
export PERSISTENCE_BACKEND=postgres
export DATABASE_URL='postgresql://industrial_semantic:industrial_semantic@localhost:5432/industrial_semantic'
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Or run:

```bash
docker compose -f docker-compose.enterprise.yml up --build
```

See `docs/ARCHITECTURE_V1_0.md` for the Enterprise Pilot architecture.


## V2.3 Data Binding Studio

V2.3 adds governed industrial data onboarding: source records from InfluxDB/historians/MES/CMMS adapters can be mapped, previewed, approved, and executed into Asset, Sensor, Condition, Alarm, and Work Order domain contracts. See `docs/ARCHITECTURE_V2_2.md`.

## V2.5 Enterprise Identity

V2.5 adds a second governance plane for enterprise resource scope while preserving the existing semantic RBAC/RLS engine. Existing installations remain compatible through the `default` tenant.

Key APIs: `/enterprise/contract`, `/enterprise/tenants`, `/enterprise/organizations`, `/enterprise/sites`, `/enterprise/principals`, `/enterprise/access/check`, `/enterprise/scoped/assets`, `/enterprise/scoped/connectors`, `/enterprise/scoped/edge-agents`, `/enterprise/scoped/fmea`, `/enterprise/scoped/rca-cases`.


## V2.7 Enterprise Secrets & Credential Management

Sensitive credentials should be referenced rather than persisted inline. Examples:

```bash
DORIS_PASSWORD_REF=secret://env/DORIS_PASSWORD
QDRANT_API_KEY_REF=secret://file/qdrant_api_key
AUTH_JWT_SECRET_REF=secret://file/auth_jwt_secret
```

Datasource and LLM configuration now support `credential_ref` / `api_key_ref`. The Secret Registry stores references and governance metadata only; secret values are resolved at runtime and are never returned by Secret APIs. See `docs/ARCHITECTURE_V2_7.md`.


## V2.8 Audit, Compliance & Policy Center

V2.8 adds a unified enterprise audit center with correlation tracing, legacy audit normalization, compliance policies/violations, retention governance and JSON/CSV export. Use `/audit/summary`, `/audit/events`, `/audit/traces/{correlation_id}`, `/compliance/*` and the **审计与合规** UI page.

## V2.9 Observability & SRE Control Plane

V2.9 adds runtime observability without conflating it with V2.8 compliance audit. Every HTTP request receives W3C-compatible trace context and can be queried through `/observability/traces/{trace_id}`. SRE APIs expose HTTP p95/error/availability, dependency health, configurable SLOs and alert incidents. Prometheus-format metrics are published at `/observability/prometheus`; `/metrics` remains the governed business Metric Registry. See `docs/ARCHITECTURE_V2_9.md`.
