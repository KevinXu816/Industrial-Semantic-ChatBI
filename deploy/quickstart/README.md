# V4.9 一键部署

最简单的私有化安装只有一条命令：

```bash
./deploy/quickstart/install.sh local
```

云端 SaaS（已准备域名并将 DNS 指向服务器）：

```bash
DOMAIN=ai.example.com ./deploy/quickstart/install.sh saas
```

脚本会自动完成 Docker 检查、强随机 Secret/PostgreSQL 密码生成、镜像构建、PostgreSQL、JWT 认证、迁移、Readiness 检查、反向代理以及 24 小时临时管理员登录链接生成。

> `local` 模式默认使用 HTTP `8080`，适合企业内网/反向代理之后的私有化部署；`saas` 模式通过 Caddy 使用域名并自动申请 HTTPS 证书。生产 ChatBI 如需查询真实数仓，仍需配置 Doris；脚本不会把 `mock` 查询伪装成真实 Doris。
