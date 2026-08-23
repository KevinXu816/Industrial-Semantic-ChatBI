# V4.9 一键生产部署架构

V4.9 在现有生产 Runtime 之上增加 Deployment Orchestrator，不改变业务领域架构。

```text
./install.sh local | saas
        ↓
Docker / Compose Preflight
        ↓
随机 PostgreSQL Password + JWT Secret
        ↓
PostgreSQL + Application + Caddy
        ↓
Auto Migration
        ↓
Startup / Readiness / Liveness
        ↓
临时 Bootstrap Admin Token（24h）
        ↓
浏览器 URL Fragment 自动写入 sessionStorage 并立即清除 Fragment
```

SaaS 模式由 Caddy 负责公网 HTTPS。企业私网数据继续采用 Edge Agent Outbound Push。真实 Doris/Qdrant/OIDC 仍按需配置，快速部署脚本不会弱化这些生产边界。
