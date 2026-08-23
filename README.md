# 工业语义智能平台

> **当前版本：V3.3.0 —— 企业 Pilot 真实数据验证版**  
> 面向工业企业的语义数据、跨系统查询、Ontology/指标、FMEA/RCA、设备可靠性、预测维修、企业治理与 Pilot 验收一体化平台。

V3.3 在 V3.2 的客户接入与验收能力上，重点增加**真实客户样例数据验证、字段映射诊断和安全 Dry-run**。目标不是继续增加平台模块，而是让实施团队可以拿客户的 InfluxDB/MES/CMMS 样例数据，在真正写入平台之前发现字段、Schema、空值和映射问题。

## 1. V3.3 主要新增能力

- **客户样例数据验证**：按 Binding 检查真实样例记录的字段、映射、Schema、空值率和转换成功率。
- **接入准备度评分**：输出 0–100 分，并判断 `ready_for_approval`。
- **Dry-run**：执行字段转换和预览，但明确 `write_performed=false`，不写业务域数据。
- **映射错误诊断**：发现 Mapping 引用了不存在的源字段、关键字段空值过高、时序数据缺少时间字段等问题。
- **继续复用治理链**：验证通过后仍走 `Draft → Preview → Approve → Schema/Watermark/Quality → Run`，不建立第二套数据接入体系。
- **README 全面中文化**：项目根目录、Pilot 数据目录和 Kubernetes 部署目录的 README 均改为简体中文，并按当前代码实际行为描述部署方式。

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

V3.3 当前交付构建验证结果：**174 passed**。

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

## 7. Docker Compose 企业 Pilot

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

## 11. Kubernetes 生产部署

部署骨架位于 `deploy/kubernetes/`。这些 YAML **不是零配置生产清单**。部署前必须替换真实镜像地址、`DATABASE_URL`、OIDC、Doris、Qdrant、Secret、Ingress/TLS 以及资源限制。

建议先执行：

```bash
python -m app.production_cli preflight
python -m app.production_cli migrate
python -m app.production_cli upgrade-check --from-version 3.2.0
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

## 15. V3.3 Pilot 主要接口

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

当前版本统一由 `app/version.py` 提供：`3.3.0`。前端版本号从 `/health` 读取。许可证以仓库根目录 `LICENSE` 文件为准。
