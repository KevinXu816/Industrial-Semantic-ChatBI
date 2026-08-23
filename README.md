# 工业语义智能平台

> **当前版本：V4.9.0 —— 一键生产部署与 SaaS/本地统一交付版**  
> 面向工业企业的语义数据、跨系统查询、设备可靠性、RCA、FMEA、预测维修、企业治理与 Pilot 验收一体化平台。

V4.7 在 V4.6 交接班与 Operations Logbook 基础上增加班次分析和运营班报/日报：系统只读聚合班次日志、团队责任、SLA/升级、RCA、Work Order 与 Peer Benchmark，形成风险 Top 5、未闭环事项、完成维护、能效异常和下一班重点；报告不修改 RCA、CMMS、FMEA、Asset 的领域状态。








## V4.9 最简单部署：1 条命令启动生产基线

V4.9 的目标是把安装门槛降到最低。首次使用无需手工编辑几十个环境变量，脚本会自动完成 Docker 检查、随机数据库密码与 JWT Secret、PostgreSQL、应用镜像、数据库迁移、健康检查、反向代理和临时管理员登录入口。

### 私有化 / 企业内网

```bash
./install.sh local
```

部署完成后终端会打印访问地址和一个 **24 小时有效的临时管理员快速登录链接**。默认入口为 `http://服务器IP:8080`。如果企业已有 Nginx、F5、WAF 或统一 TLS 网关，可以直接在其前面转发。

### 云端 SaaS / 公网域名

先把域名 DNS 指向服务器，然后执行：

```bash
DOMAIN=ai.example.com ./install.sh saas
```

SaaS 模式通过 Caddy 自动申请并续期 HTTPS 证书，同时默认启用 PostgreSQL 持久化、JWT 认证、随机 Secret、Readiness/Liveness、自动迁移，以及 V4.8 的公网 API SSRF 防护。企业私网数据库/InfluxDB/MQTT/API 仍推荐 Edge/Data Agent 主动出站，不要求客户开放数据库入站端口。

### 一键部署实际会启动什么

| 能力 | `local` | `saas` |
|---|---|---|
| PostgreSQL 持久化 | ✅ | ✅ |
| 强随机 JWT Secret | ✅ | ✅ |
| 自动迁移 / Readiness | ✅ | ✅ |
| 反向代理 | Caddy/HTTP 8080 | Caddy/HTTPS 443 |
| 临时管理员快速登录 | ✅ | ✅ |
| 私网 API Pull | 默认禁止 | 默认禁止 |
| 真实 Doris 查询 | 需显式配置 | 需显式配置 |
| Qdrant | 可选 | 可选 |
| 企业 OIDC/SSO | 可后续切换 | 推荐生产切换 |

> **重要边界**：V4.9 可以一键部署完整平台生产运行底座，但不会把默认 `EXECUTION_MODE=mock` 伪装成真实企业数仓。ChatBI 如需执行真实生产 SQL，请配置 Doris；企业正式长期使用建议把临时 JWT 管理员切换到 Keycloak / Microsoft Entra ID 等 OIDC。

### 常用运维

查看状态：

```bash
cd deploy/quickstart
docker compose --env-file .env.production -f docker-compose.production.yml ps
```

停止但保留数据：

```bash
./deploy/quickstart/uninstall.sh
```

停止并删除数据卷（**危险**）：

```bash
./deploy/quickstart/uninstall.sh -v
```

运行时敏感文件同时被 `.gitignore` 与 `.dockerignore` 排除，既不会提交到 Git，也不会进入 Docker Build Context：

```text
deploy/quickstart/.env.production
deploy/quickstart/runtime-secrets/
deploy/quickstart/bootstrap-admin.token
```


## V4.4 主要升级

- **团队协作责任层**：Asset、RCA、Work Order、FMEA 统一支持负责人、关注人和团队责任看板。
- **SLA 管理**：支持按小时或明确截止时间设置 SLA，并实时计算 `overdue / due_soon / on_track / no_sla`。
- **交接记录**：负责人变更使用显式 Handoff，保留原负责人、新负责人、操作者和交接说明。
- **评论与 @Mention**：协作线程支持评论和 `@principal` 提及，方便跨可靠性、维护和运行岗位沟通。
- **职责边界不变**：协作层只维护责任元数据；RCA Review/Resolve、CMMS 审批/下发、FMEA 生命周期仍由原领域服务治理。
- **四语言同步**：新增团队协作 UI 文案继续维护简体中文、英文、德语和日语资源包。
- **部署兼容**：V4.4 不新增强制中间件，可以从 V4.3 原地升级。

### V4.4 新增 API

```text
GET  /collaboration/board
GET  /collaboration/resources/{resource_type}/{resource_id}
POST /collaboration/resources/{resource_type}/{resource_id}/assign
POST /collaboration/resources/{resource_type}/{resource_id}/handoff
POST /collaboration/resources/{resource_type}/{resource_id}/watch
POST /collaboration/resources/{resource_type}/{resource_id}/sla
POST /collaboration/resources/{resource_type}/{resource_id}/comments
```

### 从 V4.3 升级

```bash
python -m app.production_cli preflight
python -m app.production_cli upgrade-check --from-version 4.3.0
```

V4.4 不新增数据库或外部中间件。Docker Compose 企业 Pilot 默认仍为 **PostgreSQL + Mock Query + Local Knowledge**；真实 Doris、Qdrant、OIDC 仍需显式配置。`deploy/kubernetes/` 仍是生产部署骨架，部署前必须补齐真实镜像、PostgreSQL、OIDC、Doris/Qdrant、Secret、Ingress/TLS、备份和监控。

## V4.3 主要升级

- **可配置个人首页**：按照角色保存工作台卡片的显示与顺序，可随时恢复角色默认布局；仅持久化个人偏好，不复制业务状态。
- **统一行动中心**：把 Critical Asset、Open RCA、待办工单和 Edge Agent 异常组织成可执行步骤，减少工程师跨模块判断下一步的成本。
- **治理边界不变**：行动中心只负责引导与深链，RCA Review/Resolve、CMMS 审批与下发仍调用原有受治理 API，不绕过审批。
- **快捷操作可固定**：个人偏好继续支持 `pinned_actions`，为后续个人化首页扩展保留稳定契约。
- **四语言同步**：V4.3 新增 UI 文案继续维护简体中文、英文、德语和日语资源包。
- **部署兼容**：V4.3 不新增强制中间件，可从 V4.2 原地升级。

### V4.3 新增 API

```text
GET  /workspace/dashboard
POST /workspace/dashboard
GET  /workspace/action-center
POST /workspace/preferences/pin-action
```

### 从 V4.2 升级

```bash
python -m app.production_cli preflight
python -m app.production_cli upgrade-check --from-version 4.2.0
```

V4.3 不新增数据库或外部中间件。Docker Compose 企业 Pilot 默认仍为 PostgreSQL + Mock Query + Local Knowledge；真实 Doris、Qdrant、OIDC 需要显式配置。`deploy/kubernetes/` 仍是生产部署骨架，部署前必须补齐真实镜像、PostgreSQL、OIDC、Doris/Qdrant、Secret、Ingress/TLS、备份与监控。

## V4.2 主要升级

- **角色化今日重点**：可靠性工程师、维护计划员、运行人员看到不同排序的 Critical Asset、Open RCA、待办工单与边缘异常。
- **我的工作区**：增加最近访问与收藏；只保存个人偏好，不复制 Asset/RCA/工单业务状态。
- **上下文导航**：从资产或 RCA 一键联动资产可靠性、RCA 工作流、Peer Benchmark 与维护工单。
- **深链操作**：全局搜索、Command Palette、统一 Inbox 与个人工作区都可以携带 Asset/RCA 上下文进入目标页面。
- **四语言同步**：新增 UI 文案继续维护 `zh-CN`、`en-US`、`de-DE`、`ja-JP` 四套语言资源。
- **部署兼容**：V4.2 不新增强制中间件，可从 V4.1 原地升级。

### V4.2 新增 API

```text
GET  /workspace/personalized
GET  /workspace/preferences
POST /workspace/preferences
POST /workspace/preferences/recent
POST /workspace/preferences/favorite
GET  /workspace/context
```

### 从 V4.1 升级

```bash
python -m app.production_cli preflight
python -m app.production_cli upgrade-check --from-version 4.1.0
```

V4.2 不新增数据库或外部中间件。Docker Compose 企业 Pilot 的默认运行模式仍然是 PostgreSQL + Mock Query + Local Knowledge；真实 Doris、Qdrant、OIDC 仍需显式配置。Kubernetes 目录仍是生产部署骨架，部署前必须补齐真实镜像、PostgreSQL、OIDC、Doris/Qdrant、Secret、Ingress/TLS、备份和监控。

## V4.1 主要升级

- **全局搜索与 Command Palette**：在任意页面使用 `Ctrl+K` / `⌘K` 搜索资产、RCA、FMEA、待办工单和模型，或直接执行常用页面跳转。
- **统一待办与通知中心**：自动汇总 Critical Asset、风险恶化设备、Open RCA、待办维护工单和 Edge Agent 异常；该视图只读聚合现有 Source of Truth，不复制业务状态。
- **工作台快速操作**：可靠性工作台增加资产、RCA、Peer Benchmark、企业 Pilot 快捷入口，并直接显示统一待办摘要。
- **跨模块上下文跳转**：搜索结果和 Inbox 项可以直接进入对应资产、RCA、模型或数据接入页面。
- **四语言同步**：新增 UI 文案同步进入 `zh-CN`、`en-US`、`de-DE`、`ja-JP` 四套语言资源包。
- **部署兼容**：V4.1 不新增强制数据库或中间件，可从 V4.0 原地升级。

### V4.1 新增 API

```text
GET /workspace/search?q=...
GET /workspace/inbox
GET /workspace/quick-actions
```

## V4.0 主要升级

- **产品品牌统一**：左上角正式使用“工业语义智能平台”，不再显示 ChatBI。
- **现代企业 UI**：重构导航、顶部栏、卡片、表格、表单、按钮、状态、空状态、滚动条与响应式布局，强调易用、美观和专业性。
- **四语言持续同步**：简体中文、英文、德语、日语资源包同步维护，新 UI 文案必须经过 i18n 资源管理。
- **全功能 UI 验证**：逐一访问所有一级功能页面，检查可达性、渲染、语言切换、版本号、页脚作者信息与控制台错误。
- **全功能真实截图**：`docs/images/` 保存当前 V4.0 实际运行页面的全功能截图，便于 README、客户演示和验收。

## V3.9 主要新增能力

- **维护后效果验证**：维护完成后使用原 Benchmark 的同工况口径重新验证设备表现。
- **闭环成功门槛**：同时要求验证样本充分、改善幅度达到目标、设备回到 Peer 正常区间，并且关联 RCA Case 已进入 `resolved` 或 `closed`。
- **效果量化**：记录维护前值、维护后中位数、改善百分比以及维护后相对 Peer 中位数的偏差。
- **历史 Outcome 沉淀**：每次验证形成 `Peer Benchmark Outcome`，可用于后续相似案例、维护策略和可靠性经验复用。
- **专业化 UI**：同类设备对标中心新增“维护后效果验证”区域；所有新增界面文案同步到 `zh-CN`、`en-US`、`de-DE`、`ja-JP`。
- **README 同步**：本文继续使用简体中文，并按 V3.9 当前代码实际行为维护部署说明。

### V3.9 推荐闭环

```text
Peer Benchmark
      ↓
P1/P2 异常设备
      ↓
创建 RCA Case
      ↓
工程师 Review / Resolve
      ↓
Maintenance Action
      ↓
采集维护后同工况样本
      ↓
Peer Outcome Verification
      ↓
Verified Success / Continue Investigation
```

### V3.9 API

```text
GET  /pilot/peer-outcomes/policy
POST /pilot/peer-outcomes/policy
POST /pilot/peer-benchmark/{assessment_id}/verify-outcome
GET  /pilot/peer-outcomes
```

## V3.8 主要新增能力

- **Peer 可比性透明解释**：明确展示产品类型、运行模式、负荷区间、环境区间等可比条件，并记录每个被排除 Peer 的原因。
- **异常优先级**：综合同群中位数偏差、Peer 百分位和样本充分性生成 0–100 优先级分数和 P1–P4 等级。
- **Peer Benchmark → RCA 闭环**：满足条件的异常设备可以从对标中心直接创建正式 RCA Case，并把对标上下文作为结构化证据写入 Case。
- **专业对标中心 UI**：新增可比性解释、异常优先级和 RCA 操作区；所有新增界面文案同步进入简体中文、英文、德语、日语资源包。
- **产品真实截图**：`docs/images/` 保存由当前 V3.8 实际运行页面重新生成的 5 张产品截图，README 可直接用于项目介绍和客户演示。

### V3.8 推荐分析链路

```text
V3.5 数据质量可信
        ↓
V3.6 单设备历史同工况基线
        ↓
V3.7 多设备自动工况分群 / Peer Benchmark
        ↓
V3.8 可比性解释 / 异常优先级
        ↓
一键创建 RCA Case
        ↓
Reliability / RCA / Maintenance
```

### V3.8 API

```text
POST /pilot/peer-benchmark/assess
GET  /pilot/peer-benchmark/assessments
POST /pilot/peer-benchmark/{assessment_id}/promote-to-rca
```

## V4.0 UI 基线全功能界面截图

以下截图来自 V4.0 实际运行页面，不是设计稿。为了便于项目验收和客户演示，所有一级功能页面均保存在 `docs/images/`。

| 功能 | 截图 |
|---|---|
| 可靠性工作台 | ![可靠性工作台](docs/images/01-workspace.png) |
| 智能问答 | ![智能问答](docs/images/02-chat.png) |
| 大模型配置 | ![大模型配置](docs/images/03-llm.png) |
| 数据源管理 | ![数据源管理](docs/images/04-datasources.png) |
| 数据绑定 | ![数据绑定](docs/images/05-bindings.png) |
| 语义图谱 | ![语义图谱](docs/images/06-graph.png) |
| 指标注册表 | ![指标注册表](docs/images/07-metrics.png) |
| 元数据扫描 | ![元数据扫描](docs/images/08-scan.png) |
| 候选模型审核 | ![候选模型审核](docs/images/09-candidates.png) |
| 行业模板 | ![行业模板](docs/images/10-templates.png) |
| 资产可靠性 | ![资产可靠性](docs/images/11-assets.png) |
| RCA 工作流 | ![RCA 工作流](docs/images/12-rcaworkflow.png) |
| 模型运维 | ![模型运维](docs/images/13-modelops.png) |
| 身份与租户 | ![身份与租户](docs/images/14-identity.png) |
| 审计与合规 | ![审计与合规](docs/images/15-auditcenter.png) |
| 企业 Pilot | ![企业 Pilot](docs/images/16-pilot.png) |
| 同类设备对标 | ![同类设备对标](docs/images/17-benchmark.png) |
| 可观测性 / SRE | ![可观测性与 SRE](docs/images/18-observability.png) |
| 系统管理 | ![系统管理](docs/images/19-admin.png) |
| 图形化语义关系编辑 | ![图形化语义关系编辑](docs/images/20-graph-editor.png) |

## 1. V3.6 主要新增能力

- **同工况可比基线**：按照负荷、产量、环境温度、班次、产品类型和运行模式筛选可比历史样本。
- **工况归一化偏差**：避免简单“今天 vs 昨天”把产品、负荷或环境变化误判成设备故障。
- **RCA 使用门槛**：可比样本数量不足时返回 `ready_for_rca=false`，不输出看似精确但缺乏可比依据的结论。
- **可配置工况策略**：负荷容差、产量容差、环境温度容差、最小样本量以及是否要求同班次/同产品/同模式均可治理。
- **专业化界面**：统一导航、卡片、表单、状态、空状态、响应式布局和视觉层级，改善现场工程师操作效率。
- **四语言资源包**：提供 `zh-CN`、`en-US`、`de-DE`、`ja-JP` 独立资源文件，界面可即时切换并记住用户选择。
- **统一作者信息**：主界面与图谱编辑器底部均展示作者/项目维护信息。
- **README 同步**：项目内 README 继续全部使用简体中文，部署说明保持与当前代码、Compose、Kubernetes 清单的真实行为一致。

### 1.1 推荐的真实工业分析链路

```text
V3.3 字段 Mapping 验证 / Dry-run
          ↓
V3.4 Asset / 时间 / 粒度对齐
          ↓
V3.5 时序数据质量 Gate
          ↓
V3.6 Operating Context / 可比基线
          ↓
Condition / Reliability / RCA / 能效分析
```

### 1.2 V3.6 工况上下文 API

```text
POST /pilot/operating-context/policies
GET  /pilot/operating-context/policies
POST /pilot/operating-context/assess
GET  /pilot/operating-context/assessments
```

默认策略强调：同产品类型、同运行模式，负荷和产量保持在可配置容差范围内；只有满足最小可比样本量时，工况归一化偏差才建议进入 RCA。

### 1.3 多语言资源

语言资源位于：

```text
app/static/i18n/
├── zh-CN.json
├── en-US.json
├── de-DE.json
└── ja-JP.json
```

运行时由 `/static/i18n.js` 加载。默认语言为简体中文，用户选择保存在浏览器本地；如果某个新文案尚未提供目标语言翻译，会回退到简体中文原文，不阻断界面使用。

## 1. V3.5 主要新增能力

- **工业时序质量 Gate**：在 Baseline、Reliability、RCA 之前统一执行时序质量检查。
- **数据 Gap 检测**：根据期望采样周期与 Gap 系数识别缺测区间。
- **Robust Outlier 检测**：基于 Median/MAD 识别异常点，降低极端值对检测阈值的反向污染。
- **Counter Reset 检测**：识别累计电量、运行小时、计数器等累计量回零或重置。
- **Sensor Frozen 检测**：识别连续多个采样点完全不变化的传感器冻结。
- **Clock Drift 与 Late-arriving 分离**：设备时钟漂移和网络/链路迟到数据采用独立证据字段与阈值。
- **MES 班次标记**：按可配置班次起始时间标记时序记录，便于后续按班次对账。
- **维护窗口治理**：维护期间数据保留用于追溯，但默认不进入健康 Baseline。
- **Reconciliation 输出**：每条记录带质量标记、班次和 `baseline_eligible`，可直接交给后续分析层。
- **README 全量同步**：根目录、Pilot 数据目录和 Kubernetes 部署目录 README 均保持简体中文，并同步 V3.5 的真实部署与使用说明。

## 1.1 V3.5 时序数据质量与对账能力

- **Gap 检测**：根据期望采样周期识别长时间缺测。
- **Robust Outlier**：使用 Median/MAD 检测异常值，避免均值/标准差被极端值本身污染。
- **Counter Reset**：对累计电量、运行小时、计数器等累计量识别回零/重置。
- **Sensor Frozen**：识别连续多个采样点完全不变化的传感器冻结。
- **Clock Drift**：独立比较源设备时钟与接收端时钟，识别设备时钟漂移。
- **Late-arriving Data**：识别事件时间与平台接收时间之间的长延迟，不与 Clock Drift 混淆。
- **Shift Boundary**：按可配置班次起始小时为每条记录标注班次。
- **Maintenance Window**：维护窗口数据保留用于追溯，但默认禁止进入健康 Baseline。
- **Reconciliation Output**：每条数据带 `quality_flags`、`shift`、`baseline_eligible`，供后续 Reliability/RCA 使用。
- **质量评分**：输出 `quality_score`、关键问题数量和 `ready_for_baseline`。

推荐真实数据进入分析前执行：

```text
V3.3 Mapping Validate / Dry-run
          ↓
V3.4 Asset/Time Alignment
          ↓
V3.5 Time-Series Quality Gate
          ↓
Baseline / Condition / Reliability / RCA
```

## 2. 产品架构

```text
MES / EMS / CMMS / IoT / Historian / ERP
                 ↓
Connector / Edge Agent / Data Binding
                 ↓
客户样例验证 / Schema / Data Quality / Watermark
                 ↓
Semantic Model / Ontology / Metric Graph
                 ↓
Governed Query / Doris Federation
                 ↓
Condition Analytics / FMEA / RCA
                 ↓
Knowledge / Reliability / RUL
                 ↓
Asset Cockpit / Maintenance
                 ↓
Identity / Secrets / Audit / SRE / Production Runtime
```

当前优先 Pilot 场景为**空压机能效异常 + 预测维修**：MES 提供产量，IoT/Historian 提供功率、过滤器压差、排气温度和负载，CMMS 提供告警与工单，平台计算单位能耗异常并通过结构化证据支持 Filter Restriction RCA。

## V4.1 部署说明（与当前仓库实际行为一致）

V4.1 是工程师效率与统一工作入口升级，**没有新增强制中间件**，因此 V4.0 的部署拓扑可以原地升级。升级前建议：

```bash
python -m app.production_cli preflight
python -m app.production_cli upgrade-check --from-version 4.0.0
```

部署边界继续保持：本地 Demo 默认使用 JSON + Mock Query + Local Knowledge；Docker Compose 企业 Pilot 默认使用 PostgreSQL + Mock Query + Local Knowledge；真实 Doris、Qdrant、OIDC 必须显式配置；`deploy/kubernetes/` 是生产部署骨架，仍需要企业镜像、PostgreSQL、OIDC、Doris/Qdrant、Secret、Ingress/TLS、备份与监控。

## 3. 环境要求

### 3.1 本地 Demo / 开发环境

建议使用 Python 3.12，最低 Python 3.10。默认不要求 PostgreSQL、Doris、Qdrant 或 OIDC。

默认运行模式：

```text
PERSISTENCE_BACKEND=json
EXECUTION_MODE=mock
KNOWLEDGE_BACKEND=local
AUTH_MODE=disabled
```

### 3.2 企业 Pilot

建议至少使用 PostgreSQL 16 作为共享持久化。Doris 只有在验证真实 SQL/Federation 时才需要启用；Qdrant 只有在验证生产向量检索时才需要启用；企业身份接入时再配置 OIDC/Keycloak/Microsoft Entra ID。

### 3.3 生产 / HA

生产多副本部署要求 PostgreSQL 共享持久化，JSON Repository 不支持真正 HA。认证应使用 OIDC 或受控 JWT，Secret 应使用 `secret://file/...`、Vault 或 Azure Key Vault 等引用方式。Kubernetes 使用 `/health/startup`、`/health/ready`、`/health/live` 三类探针。

## 4. 本地最小启动

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Windows PowerShell：

```powershell
.\.venv\Scripts\Activate.ps1
```

启动后检查：

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/health/live
curl http://127.0.0.1:8000/health/ready
```

浏览器访问：`http://127.0.0.1:8000/`

运行测试：

```bash
pip install -r requirements-dev.txt
pytest -q
```

V3.6 当前交付构建验证结果：**186 passed**。

## 5. 空压机 Pilot

服务启动后可运行：

```bash
./deploy/pilot/run-air-compressor-pilot.sh
```

也可手工执行：

```bash
curl -X POST http://127.0.0.1:8000/pilot/scenarios/air-compressor-energy-maintenance/bootstrap
curl -X POST http://127.0.0.1:8000/pilot/run-demo
curl http://127.0.0.1:8000/pilot/readiness
curl http://127.0.0.1:8000/pilot/report
```

Pilot GO/NO-GO 不是以“Demo 能运行”为标准，而是同时检查技术准备度、客户数据 Binding 审批、RCA 证据质量和五项业务 KPI。



## V3.5 工业时序数据质量与对账

V3.5 推荐在 V3.4 数据对齐完成后、建立健康 Baseline 之前运行。

新增 API：

```text
POST /pilot/data-quality/policies
GET  /pilot/data-quality/policies
POST /pilot/data-quality/maintenance-windows
GET  /pilot/data-quality/maintenance-windows
POST /pilot/data-quality/assess
POST /pilot/data-quality/reconcile
GET  /pilot/data-quality/assessments
```

默认质量策略包括：

```text
期望采样周期          300 秒
Gap 判定系数          2.5 倍采样周期
MAD 异常阈值          6.0
冻结最少连续点        4
Clock Drift 阈值      120 秒
Late Arrival 阈值     900 秒
班次开始小时          00:00 / 08:00 / 16:00 UTC
```

注意：`received_at - timestamp` 用于判断迟到数据；`source_clock_at - received_at` 用于判断源设备 Clock Drift，两者是不同的数据质量问题。

维护窗口示例：

```json
{
  "asset_id": "A101",
  "start": "2026-08-23T08:00:00Z",
  "end": "2026-08-23T10:00:00Z",
  "reason": "更换空气过滤器"
}
```

维护窗口内数据不会被删除，但会带：

```text
quality_flags = ["maintenance_window"]
baseline_eligible = false
```

因此可以继续用于维修前后追溯，同时避免污染正常健康基线。

## V3.4 真实数据对齐与可信化

V3.3 解决“样例数据能不能正确映射”，V3.4 继续解决“不同系统的数据能不能在同一个资产、同一个时间轴、同一个运行状态下可信比较”。

推荐现场链路：

```text
MES / IoT / CMMS
      ↓
V3.3 Validate / Dry-run
      ↓
Asset Alias（统一设备 ID）
      ↓
UTC Timestamp Normalize
      ↓
5min Bucket Alignment
      ↓
Sensor Completeness
      ↓
Operating / Stop State Gate
      ↓
Safe Specific Energy
      ↓
Baseline / Reliability / RCA
```

新增 API：

```text
POST /pilot/data-alignment/asset-aliases
GET  /pilot/data-alignment/asset-aliases
POST /pilot/data-alignment/failure-codes
GET  /pilot/data-alignment/failure-codes
POST /pilot/data-alignment/normalize
POST /pilot/data-alignment/assess-series
```

例如 MES 使用 `CMP-01`、IoT 使用 `compressor_001`、CMMS 使用 `EQ000781` 时，应分别登记 Alias，统一映射到平台资产 `A101`，不要依赖字符串猜测。

时间戳统一转换为 UTC。对于 `2026-08-23 16:00:00` 这种没有时区信息的非 UTC 本地时间，平台不会静默猜测；应先转换为 `2026-08-23T16:00:00+08:00` 等带 offset 的 ISO 8601。

单位能耗只在 `production_output > 0` 且设备满足运行负荷阈值时计算。零产量/低负荷 Bucket 会被标记为停机或非生产状态，不进入健康 Baseline，避免 `kWh/unit` 被除零或停机功耗污染。

## 6. V3.3 真实客户数据验证流程

先生成客户数据 Binding：

```bash
curl -X POST http://127.0.0.1:8000/pilot/onboarding/prepare \
  -H 'Content-Type: application/json' \
  -d '{"site_id":"F01"}'
```

获取 Binding ID 后，使用少量脱敏真实记录验证。例如 IoT：

```bash
curl -X POST http://127.0.0.1:8000/pilot/customer-data/<binding_id>/validate \
  -H 'Content-Type: application/json' \
  -d '{
    "records":[
      {"asset_id":"A101","sensor":"filter_dp","value":12.4,"timestamp":"2026-08-23T08:00:00Z"}
    ]
  }'
```

系统返回重点字段：

```text
missing_source_fields
null_rates
transform_success_rate
schema
schema_drift
timestamp_candidates
warnings
readiness_score
ready_for_approval
```

在写入任何业务数据前，建议先执行 Dry-run：

```bash
curl -X POST http://127.0.0.1:8000/pilot/customer-data/<binding_id>/dry-run \
  -H 'Content-Type: application/json' \
  -d '{"records":[...]}'
```

Dry-run 永远返回：

```text
write_performed = false
```

推荐现场流程：

```text
客户提供 20～100 条脱敏样例
        ↓
字段 Mapping
        ↓
V3.3 Validate
        ↓
修正 Missing / Null / Schema 问题
        ↓
Dry-run Preview
        ↓
数据工程师确认
        ↓
Binding Approve
        ↓
Schema / Watermark / Quality Rule
        ↓
Integration Runtime Run
```

## 7. Docker Compose 企业 Pilot（推荐客户 POC）

复制配置：

```bash
cp .env.enterprise.example .env
docker compose -f docker-compose.enterprise.yml up --build
```

**默认真实行为**是启动 PostgreSQL 16 和平台 API，但应用仍使用：

```text
EXECUTION_MODE=mock
KNOWLEDGE_BACKEND=local
AUTH_MODE=disabled
DEPLOYMENT_ENV=development
```

因此该方式适合企业 Pilot 和 PostgreSQL 持久化验证，**不代表已经启用真实 Doris、Qdrant 和企业 SSO**。

## 8. Docker Compose 启用 Qdrant

应用镜像必须安装 `qdrant` 可选依赖：

```bash
INSTALL_EXTRAS=postgres,governance,auth,qdrant \
KNOWLEDGE_BACKEND=qdrant \
docker compose -f docker-compose.enterprise.yml --profile qdrant up --build
```

有 API Key 时使用 Secret Reference，不要把真实 Key 提交到 Git。

## 9. 连接真实 Doris

在 `.env` 配置：

```bash
EXECUTION_MODE=doris
DORIS_HOST=<doris-host>
DORIS_PORT=9030
DORIS_USER=<只读用户>
DORIS_DATABASE=industrial_ai
DORIS_PASSWORD_REF=secret://env/DORIS_PASSWORD
DORIS_PASSWORD=<运行时密码>
```

然后执行：

```bash
docker compose -f docker-compose.enterprise.yml up --build
```

生产环境建议 Doris 使用最小权限只读账号，并通过 `/health/ready` 验证依赖可用性。

## 10. 可选依赖

```bash
pip install -e '.[postgres]'                 # PostgreSQL
pip install -e '.[governance]'               # SQL AST 治理
pip install -e '.[auth]'                     # OIDC/JWT
pip install -e '.[qdrant]'                   # Qdrant
pip install -e '.[pgvector]'                 # pgvector
pip install -e '.[secrets]'                  # Vault / Azure Key Vault
pip install -e '.[postgres,governance,auth,qdrant,secrets]'
```

## 11. Kubernetes 生产部署（生产骨架，部署前必须补齐外部依赖）

部署骨架位于 `deploy/kubernetes/`。这些 YAML **不是零配置生产清单**。部署前必须替换真实镜像地址、`DATABASE_URL`、OIDC、Doris、Qdrant、Secret、Ingress/TLS 以及资源限制。

建议先执行：

```bash
python -m app.production_cli preflight
python -m app.production_cli migrate
python -m app.production_cli upgrade-check --from-version 3.7.0
```

再执行：

```bash
kubectl apply -f deploy/kubernetes/configmap.yaml
kubectl apply -f deploy/kubernetes/deployment.yaml
kubectl apply -f deploy/kubernetes/service.yaml
kubectl apply -f deploy/kubernetes/pdb.yaml
kubectl apply -f deploy/kubernetes/hpa.yaml
```

详细说明见 `deploy/kubernetes/README.md`。

## 12. 生产配置原则

推荐生产环境至少满足：

```text
DEPLOYMENT_ENV=production
PERSISTENCE_BACKEND=postgres
AUTH_MODE=oidc
EXECUTION_MODE=doris
KNOWLEDGE_BACKEND=qdrant 或 pgvector
```

生产环境不要使用 JSON Repository 做多副本共享状态，不建议使用 `AUTH_MODE=disabled/dev`，不要把数据库密码、API Key、OIDC Client Secret 直接写入 Git。

## 13. PostgreSQL 备份与恢复

仓库提供：

```text
deploy/scripts/postgres-backup.sh
deploy/scripts/postgres-restore.sh
```

应用元数据 Backup API 不等同于数据库灾备。正式生产建议使用 `pg_dump`，并根据 RPO/RTO 配置 Base Backup、WAL Archive 和 PITR。

## 14. Pilot 数据契约

推荐客户至少准备：

| 数据源 | 最小数据 |
|---|---|
| MES | 设备主数据、产量、时间戳 |
| IoT/Historian | `active_power`、`filter_dp`、`discharge_temp`、`load_pct` |
| CMMS | 告警、工单、维护动作历史 |

建议至少 30 天历史数据，优先 90 天；Process/Energy 建议 1～5 分钟粒度，Alarm/Work Order 保留真实事件时间。

客户字段映射示例见 `data/pilot/customer_mapping.example.json`。

## 15. Pilot 主要接口（V3.3 起）

```text
GET  /pilot/data-contract
POST /pilot/onboarding/prepare
GET  /pilot/onboarding/status
POST /pilot/customer-data/{binding_id}/validate
POST /pilot/customer-data/{binding_id}/dry-run
GET  /pilot/customer-data/validation
GET  /pilot/evidence-quality
POST /pilot/run-demo
GET  /pilot/readiness
POST /pilot/kpis
GET  /pilot/kpis
GET  /pilot/report
GET  /pilot/report.md
```

健康检查：

```text
GET /health
GET /health/live
GET /health/startup
GET /health/ready
```

Semantic Query、Ontology、FMEA/RCA、Asset Cockpit、Connector/Edge Agent、Identity/SSO、Secrets、Audit/Compliance、SRE、Model Registry 等既有能力继续保留。

## V4.5 SLA 策略、升级机制与值班协同

V4.5 在 V4.4 团队协作基础上新增 SLA Policy、On-call 值班表、超时升级和通知适配器契约。平台核心只生成通知意图，不会假装邮件、Teams 或 Slack 已经发送成功，也不会绕过 RCA/CMMS/FMEA 的正式审批。

主要接口：

```text
GET/POST /collaboration/sla-policies
GET/POST /collaboration/oncall
POST     /collaboration/escalations/evaluate
GET      /collaboration/escalations
GET      /collaboration/notifications
GET      /collaboration/notifications/contract
```

### 从 V4.4 升级到 V4.5

V4.5 不新增强制中间件，责任、SLA、值班和通知意图继续使用现有 Repository，因此可以原地升级。升级前建议：

```bash
python -m app.production_cli preflight
python -m app.production_cli upgrade-check --from-version 4.4.0
```

### 部署说明

- 本地 Demo 仍为 JSON Repository + Mock Query + Local Knowledge + `AUTH_MODE=disabled`。
- `docker-compose.enterprise.yml` 默认仍为 PostgreSQL + Mock Query + Local Knowledge；不会自动启用 Doris、Qdrant 或 OIDC。
- 真实 Doris 必须显式设置 `EXECUTION_MODE=doris` 及 Doris 连接参数。
- Qdrant 必须安装 `qdrant` optional extra 并设置 `KNOWLEDGE_BACKEND=qdrant`。
- Kubernetes 目录仍是生产部署骨架，企业生产需要补齐真实镜像、PostgreSQL、OIDC、Doris、Qdrant/pgvector、Secret、Ingress/TLS、备份与监控。
- Email / Teams / Slack / Webhook 在 V4.5 是 Adapter Contract；核心平台生成 `Notification Intent`，真实发送必须由企业适配器完成。

## 16. 当前边界

- `mock` 查询不能代表真实 Doris Federation 的性能和稳定性。
- Local Knowledge 不能代表 Qdrant/pgvector 的生产容量与召回效果。
- 合成空压机数据只用于流程演示，不能替代现场数据。
- V3.3 的客户数据验证针对**已取得的样例记录**，平台核心不会擅自直连客户数据库；真实采集仍应由 Connector/Edge Agent/受控适配器完成。
- RUL 仍属于趋势工程估算，不等同于经过大量 run-to-failure 数据校准后的故障概率模型。
- Pilot GO/NO-GO 必须基于客户真实业务 KPI。

## 17. 推荐客户 Pilot 实施顺序

```text
第 1 天：确认资产、信号、业务 KPI 和数据责任人
第 2 天：获取 20～100 条脱敏样例，完成字段映射与 V3.3 Validate
第 3 天：Dry-run、Schema、Watermark、Quality Rule、Binding 审批
第 4～5 天：接入历史数据，运行 Condition / Reliability / RCA
第 2 周：工程师审核 RCA、修正 FMEA/证据链
第 3～4 周：记录维护动作和修复后单位能耗
最终：输出 Pilot Acceptance Report，形成 GO / NO-GO 决策
```

## 18. 版本与许可证

当前版本统一由 `app/version.py` 提供：`4.8.0`。前端版本号从 `/health` 读取。许可证以仓库根目录 `LICENSE` 文件为准。



## V4.6 交接班日志与责任连续性

V4.6 在 V4.5 的 SLA、升级和值班能力上增加正式电子交接班。系统会在交班时从现有团队责任看板生成未闭环事项快照，并保留本班运行日志、SLA 状态和开放升级；交班人与接班人分别留下确认记录。交接班模块只记录责任连续性，不自动关闭 RCA、不审批工单，也不修改 FMEA 生命周期。

主要接口：

```text
GET/POST /operations/shifts
GET/POST /operations/logbook
GET/POST /operations/handovers
POST     /operations/handovers/{handover_id}/acknowledge
GET      /operations/handover-dashboard
```

### 从 V4.5 升级到 V4.6

V4.6 不新增强制中间件，班次、日志和交接确认继续使用现有 JSON/PostgreSQL Repository，因此可以原地升级：

```bash
python -m app.production_cli preflight
python -m app.production_cli upgrade-check --from-version 4.5.0
```

### V4.6 部署说明

- 本地 Demo 仍为 JSON Repository + Mock Query + Local Knowledge + `AUTH_MODE=disabled`。
- `docker-compose.enterprise.yml` 默认仍为 PostgreSQL + Mock Query + Local Knowledge。
- 真实 Doris 仍需显式设置 `EXECUTION_MODE=doris` 和 Doris 连接参数。
- Qdrant 仍需安装 `qdrant` optional extra 并配置 `KNOWLEDGE_BACKEND=qdrant`。
- V4.6 不新增 Redis、消息队列或新的数据库要求。
- Kubernetes 目录仍是生产部署骨架，生产环境必须补齐企业镜像、PostgreSQL、OIDC、Doris、Qdrant/pgvector、Secret、Ingress/TLS、备份、监控与通知适配器。



## V4.8 两步式企业数据接入与 SaaS 安全连接

V4.8 的目标是把企业数据接入门槛压缩成两步：**第 1 步连接/上传数据源；第 2 步确认系统自动识别的字段映射并完成接入**。确认后系统自动创建现有 `DataSource` 与 `Approved Data Binding`，后续继续复用 Schema Drift、Watermark、Data Quality、DLQ、Integration Runtime，不建立第二套数据链。

### 最简单的两步接入

1. 在“数据源管理”点击“开始两步接入”，选择 Excel/CSV、REST API 或企业内网/Edge Agent。Excel 会自动识别 Sheet、表头和样例；API 会识别 JSON 对象字段和 `data_path`；内网数据库/InfluxDB/MQTT/Historian 推荐 Edge Agent。
2. 检查系统推荐的 `Asset / Condition / Alarm / Work Order` 字段映射，确认后即创建 DataSource + Approved Binding。

### Excel / CSV

浏览器直接上传 `.xlsx` 或 `.csv`（默认上限 25MB），系统自动识别 Sheet、表头、样例数据和常见字段别名，例如 `device_id/equipment_code → asset_id`、`tag_name → sensor`、`event_time → timestamp`。大文件和持续增量数据不建议通过浏览器上传，应使用 Edge Agent/Connector Runtime。

### REST API

公网 API 推荐 SaaS HTTPS Pull；可配置 URL、HTTP Method、JSON `data_path`、样例响应。认证 Header 必须使用 `secret://` Secret Reference，禁止在普通 DataSource/Onboarding 配置里持久化明文 Token/API Key。

### SaaS 与企业内网安全连接

生产 SaaS 默认：`ALLOW_PRIVATE_API_PULL=false`、`ALLOW_INSECURE_API_HTTP=false`。平台会阻断 localhost、RFC1918 私网、link-local、云 Metadata 等目标，降低 SSRF/内网探测风险。企业内网 MySQL/PostgreSQL/Doris/InfluxDB/MQTT/Historian/Private API 推荐部署现有 Edge/Data Agent，由企业侧主动通过 TLS 出站提交 `ConnectorBatch`：**无需开放数据库入站端口，数据库/PLC/API 凭据可以留在企业网络或通过 Secret Provider 管理**。

### V4.7 → V4.8 升级

V4.8 新增基础依赖 `openpyxl` 与 `python-multipart`，但不新增 Redis/Kafka/独立 ETL Server。升级后执行：

```bash
pip install -r requirements.txt
python -m app.production_cli preflight
python -m app.production_cli upgrade-check --from-version 4.7.0
```

Docker Compose 企业 Pilot 仍默认 PostgreSQL + Mock Query + Local Knowledge；真实 Doris/Qdrant/OIDC 仍需显式配置。Kubernetes 仍是生产部署骨架，SaaS 私网数据优先通过 Edge Agent 出站，不应为了“方便”直接暴露企业数据库端口。

## V4.7 班次分析与运营班报 / 日报

V4.7 在 V4.6 电子交接班基础上增加面向班长、运维主管和工厂经理的运营报告。报告层从现有 Source of Truth 实时聚合，不复制业务状态。

主要能力：

- 自动生成班报和日报；
- 汇总新增运行日志、未闭环 RCA、待办/完成工单、SLA 超时和开放升级；
- 展示风险 Top 5 与 Peer 能效异常候选；
- 自动生成下一班/下一工作日重点；
- 保存报告窗口与来源数量，便于复核；
- 支持 Markdown 导出。

主要接口：

```text
POST /operations/reports/generate
GET  /operations/reports
GET  /operations/reports/{report_id}
GET  /operations/reports/{report_id}/markdown
```

### 从 V4.6 升级到 V4.7

V4.7 不新增强制中间件，报告继续使用现有 JSON/PostgreSQL Repository，因此可以原地升级：

```bash
python -m app.production_cli preflight
python -m app.production_cli migrate
python -m app.production_cli upgrade-check --from-version 4.6.0
```

### V4.7 部署说明

- 本地 Demo 仍为 JSON Repository + Mock Query + Local Knowledge + `AUTH_MODE=disabled`。
- `docker-compose.enterprise.yml` 默认仍为 PostgreSQL + Mock Query + Local Knowledge。
- 真实 Doris 必须显式设置 `EXECUTION_MODE=doris` 与 Doris 连接参数。
- Qdrant 必须安装 `qdrant` optional extra 并设置 `KNOWLEDGE_BACKEND=qdrant`。
- V4.7 不新增 Redis、Kafka、独立报表数据库或 BI Server。
- Kubernetes 目录仍是生产部署骨架；生产环境需要真实企业镜像、PostgreSQL、OIDC、Doris、Qdrant/pgvector、Secret、Ingress/TLS、备份、监控和通知适配器。

## V4.8 → V4.9 升级与部署兼容

V4.9 新增 `deploy/quickstart/` 一键部署编排和 Caddy 网关，但**没有强制增加 Redis、Kafka 或新的业务数据库**。已有 V4.8 Docker/Kubernetes 部署可以原地升级。推荐升级前：

```bash
python -m app.production_cli preflight
python -m app.production_cli upgrade-check --from-version 4.8.0
```

新安装用户优先直接使用 `./install.sh local` 或 `DOMAIN=... ./install.sh saas`，无需手工复制 `.env.enterprise.example` 才能完成首次启动。


## 作者信息

| | |
|---|---|
| **开发者** | 良晞 |
| **邮箱** | xhongliang@163.com |
| **GitHub** | [@KevinXu816](https://github.com/KevinXu816) |
