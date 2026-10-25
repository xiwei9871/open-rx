# 安全基线 V1.0（工程控制清单，非法律意见）

> 适用于处理正畸患者数据（PHI 可能适用）的系统。**辖区合规结论未定**（GAP-18）：HIPAA/PIPEDA/GDPR 等适用性须按部署地与销售模式经专业审核。本基线是与辖区无关的工程底线。

## 1. 威胁模型（摘要）

| 威胁 | 场景 | 主要控制 |
|---|---|---|
| 跨机构越权 | 猜 URL/ID 读他方 Rx/STL | RLS+谓词、授权边、403 不泄元数据（E2E-03） |
| 凭据窃取 | 密码/凭据复用、钓鱼 | argon2 哈希、2FA（高危强制）、会话管理 |
| 恶意文件 | 上传带毒/畸形 STL/PDF | 隔离区+AV+网格校验+配额（ASSET-010/SAFE-005） |
| 数据泄露 | 外链失控、备份外泄 | access_grant 限时签名、备份加密、审计 |
| 抵赖 | "不是我批的" | E_SIGNATURE+approval 绑定版本+审计追加 |
| 供应链 | 依赖/镜像投毒 | 锁定版本、SBOM、CI 扫描、7 天成熟度惯例 |
| 逆向/IP | 复制对方资产 | clean-room 流程（ADR-0007）——**保护对方也保护本项目** |
| 内部滥用 | 员工读无关患者 | 最小权限+审计查询告警（SAFE-001） |

## 2. 身份与访问

- 密码：argon2id；登录限流+锁定；会话 HttpOnly+Secure+SameSite；可选 WebAuthn（IAM-012 扩展 ?）。
- 2FA：TOTP；对导出、财务、删除类操作强制（IAM-012, T）。
- 服务间：worker↔API mTLS 或签名令牌；适配器凭据 OAuth2 client credentials。
- API/桌面代理/Webhook：Bearer/OAuth2 + scope；webhook 请求体 HMAC-SHA256 签名+时间戳防重放（INT-011）。

## 3. 数据保护

- 传输：TLS1.2+ 全链路（含内网组件间）。
- 静态：PG 透明加密或卷加密；S3 SSE；备份加密（SAFE-003）。
- 最小化：文件名/日志/审计中禁止 PHI 明文；对象 key 匿名 hash。
- 软删除+retention_policy；导出走 data_export_request 审批+审计（SAFE-009）。

## 4. 审计与可追溯（SAFE-001/007）

- `audit_event` 追加型：登录、授权变更、连接、Rx 状态迁移、审批、导出、文件访问、配置变更。
- approval/签署含签名者、时间、对象版本哈希。
- job 溯源：input hash/recipe+engine 版本/参数快照/output hash。

## 5. 应用安全

- 输入校验边界（Pydantic/schema）；参数化查询；CSRF token（cookie 会话）；输出编码防 XSS。
- 上传：大小/类型/配额限制、扫描后才可引用、文件名净存储（不执行、不拼路径）。
- 速率限制：登录、提交、下载、webhook。
- 错误：对外不泄堆栈/SQL；请求 id 关联内部日志。

## 6. 依赖与构建

- 依赖锁定 + `pip-audit`/Dependabot；新依赖优先 ≥7 天发布的版本。
- 镜像：最小基础镜像、非 root 运行、CI 构建 SBOM + 漏洞扫描。
- 秘钥：环境注入/secret store；仓库零秘钥（CI grep + gitleaks）。

## 7. 隐私工程

- 测试/示例数据全部合成或脱敏授权（SAFE-008）；生产数据不进 dev/staging。
- 访问日志与下载行为可被机构管理员审计。
- 数据主体请求（访问/更正/删除）流程与 retention_policy 对齐 ?（辖区相关）。
- 数据迁移合法性：确认所有权与授权后再导（GAP-09；SRC28 §5 已核验存在副本交付条款）。

## 8. 合规 Gate（发布前必须全绿）

1. 辖区与适用法规清单确认（法审）。
2. DPIA/威胁建模复核。
3. 渗透测试或等效安全评审记录。
4. 事件响应预案 + 联系人。
5. 备份恢复演练最近 30 天内 PASS。
6. 许可证/clean-room Gate（ADR-0007）通过。
