# Kubernetes 生产部署说明

> 如果是单机私有化或单节点 SaaS，优先使用根目录 `./install.sh local` / `DOMAIN=... ./install.sh saas`，这是 V4.9 最简单的 1 条命令部署路径。Kubernetes 目录用于需要多副本、企业 Ingress、外部 PostgreSQL/Secret/OIDC 的 HA 场景。

# 工业语义智能平台 V4.9 Kubernetes 生产部署

# Kubernetes 生产部署说明

本目录提供工业语义智能平台 V4.9 的 Kubernetes **生产部署骨架**，不是零配置即可上线的完整生产清单。

## 部署前必须准备

- 将 `industrial-semantic:4.9.0` 替换为企业真实镜像仓库地址和不可变版本标签。
- 配置 PostgreSQL `DATABASE_URL`；多副本场景禁止使用本地 JSON Repository 作为共享持久化。
- 正式生产建议启用 OIDC，并配置 Issuer、Client ID、Audience。
- 如启用真实查询，配置 Doris 地址和只读账号。
- 如启用生产向量检索，配置 Qdrant 或 pgvector。
- 密码、Token、API Key 使用 Kubernetes Secret、Vault 或 Key Vault，不要写入 ConfigMap 或 Git。
- 根据企业网络配置 Ingress、TLS、NetworkPolicy、DNS 和出口访问策略。
- 根据压测结果调整 CPU、Memory、HPA 和副本数。

## 部署前检查

```bash
python -m app.production_cli preflight
python -m app.production_cli migrate
python -m app.production_cli upgrade-check --from-version 4.7.0
```

## 应用清单

```bash
kubectl apply -f deploy/kubernetes/configmap.yaml
kubectl apply -f deploy/kubernetes/deployment.yaml
kubectl apply -f deploy/kubernetes/service.yaml
kubectl apply -f deploy/kubernetes/pdb.yaml
kubectl apply -f deploy/kubernetes/hpa.yaml
```

## 健康探针

- Startup Probe：`/health/startup`，判断启动配置和迁移前置条件。
- Readiness Probe：`/health/ready`，判断当前实例是否可以接收业务流量。
- Liveness Probe：`/health/live`，只判断应用进程是否存活，避免外部数据库短暂故障导致 Pod 重启风暴。

## 高可用边界

Deployment 默认可使用多个副本，但真正 HA 必须依赖共享 PostgreSQL、外部 Doris/Qdrant 等服务。Pod 本地文件不应作为跨副本共享状态。生产环境还应根据 RPO/RTO 配置 PostgreSQL 备份、WAL 归档、PITR 和灾备演练。


## V3.6 前端多语言说明

四语言资源均随应用镜像打包在 `/app/app/static/i18n/`。不需要为不同语言构建不同镜像；语言切换发生在浏览器端。若通过反向代理发布 `/static/`，请确保 JSON 与 JavaScript 资源允许正常缓存更新，并在版本升级时刷新静态资源缓存。

## V4.9 部署核对说明

V4.9 不新增强制中间件，也没有改变基础部署拓扑。团队协作、SLA、值班、运行日志与交接班元数据继续使用现有 Repository/PostgreSQL 持久化。Kubernetes 清单仍然是生产部署骨架：应用多副本必须使用 PostgreSQL 共享持久化；真实查询只有在 `EXECUTION_MODE=doris` 且 Doris 依赖可用时启用；向量知识库只有在安装对应 optional extra 并设置 `KNOWLEDGE_BACKEND=qdrant` 或 `pgvector` 时启用；企业登录应配置 OIDC。部署前必须完成镜像地址、数据库、Secret、Ingress/TLS、资源限制、备份与灾备配置。

### V4.9 交接班数据说明

交接班、班次定义和 Operations Logbook 使用现有平台持久化层，不需要新增 Redis、Kafka 或独立日志数据库。多副本生产环境必须继续使用 PostgreSQL 共享持久化，避免不同 Pod 看到不同交接状态。交接确认不会替代 RCA/CMMS/FMEA 的领域审批动作。

## V4.9 两步数据接入与 SaaS 安全边界

V4.9 不新增 Redis/Kafka/独立 ETL Server。Excel/CSV 的浏览器上传需要应用镜像包含 `openpyxl` 与 `python-multipart`（基础 `requirements.txt` 已包含）。公网 REST API 的 SaaS Pull 默认仅允许 HTTPS，并建议保持 `ALLOW_PRIVATE_API_PULL=false`、`ALLOW_INSECURE_API_HTTP=false`。企业内网数据库、InfluxDB、MQTT、Historian、Private API 应优先部署 Edge/Data Agent，由企业网络主动出站提交 ConnectorBatch，不需要向 SaaS 开放数据库入站端口。凭据使用 Kubernetes Secret/Secret Provider 与 `secret://` 引用。
