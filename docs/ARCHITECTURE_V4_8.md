# V4.8 架构：两步式企业数据接入与 SaaS 安全连接

V4.8 增加 `EnterpriseOnboardingService`，只作为接入编排层，不替代 DataSource/Data Binding/Integration Runtime。

两步流程：Step 1 Discover（Excel/API/Edge）→ 自动 schema/样例/字段推荐；Step 2 Confirm → 创建 DataSource + Approved Binding。

安全默认：SaaS API Pull 仅 HTTPS 公网；私网地址默认阻断；企业内网数据库、IoT、Private API 使用 Edge Agent 主动出站。凭据使用 Secret Reference，不在 onboarding/session 中保存明文 Secret。
