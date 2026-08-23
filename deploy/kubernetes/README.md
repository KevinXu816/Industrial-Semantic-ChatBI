# Kubernetes 生产部署说明

本目录提供工业语义智能平台 V3.3 的 Kubernetes **生产部署骨架**，不是零配置即可上线的完整生产清单。

## 部署前必须准备

- 将 `industrial-semantic:3.3.0` 替换为企业真实镜像仓库地址和不可变版本标签。
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
python -m app.production_cli upgrade-check --from-version 3.2.0
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
