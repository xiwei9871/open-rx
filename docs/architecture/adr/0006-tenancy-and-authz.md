# ADR-0006 多租户与授权：单库租户隔离 + 机构授权边（V1.1 纠偏）

- **状态**：REVISED（A3 纠偏：澄清 tenant/org 语义、跨租户结论、撤销语义、测试矩阵）
- **日期**：2026-10-24（修订于 Stage A.1）

## 背景

诊所↔实验室协作是显式授权（IAM-007、E2E-03/04、SAFE-002）。原稿的 tenant/org 边界含糊：未定义"实验室在另一租户"时怎么办，未定义撤销语义。

## 定义（冻结）

| 概念 | 定义 | 例 |
|---|---|---|
| **TENANT** | 数据所有与隔离边界。一个 tenant 是一个自闭合业务世界：含一组 clinic/lab 机构及其用户、患者、处方、资产。**自托管部署通常 = 1 tenant；SaaS 运营可有多 tenant。** | "微笑正畸+友诚技工所联盟" |
| **ORGANIZATION** | tenant 内的业务机构，kind ∈ {practice, lab, hybrid~} | 某诊所、某技工所 |
| **in-house lab** | 同一机构内的实验室职能 → `kind=hybrid`（~待证），**不**跨机构 | 诊所自营技工间 |
| **external lab** | tenant 内的另一 lab 机构，经 org_connection 授权 | 签约技工所 |

## 决策

1. **跨租户协作：V1 不支持。** tenant 之间无任何业务可见性，无连接、无共享、无搜索。理由：跨租户共享等于把隔离边界变成穿透面；若未来要"SaaS 上不同租户的诊所↔lab"，应走显式 **tenant federation**（另立 ADR），绝不靠放宽 RLS。
2. **租户隔离**：每表 `tenant_id`；PostgreSQL RLS 按 `app.tenant_id` 强制 + 应用层谓词双保险。RLS 是第一道（防跨租户），**不**替代机构级授权。
3. **机构间授权**：visibility = f(membership, org_connection, file_reference, access_grant)：
   - 本机构数据：成员按角色可见。
   - 跨机构 Rx：仅当 `org_connection(practice↔lab)=accepted` **且**该 Rx 已被提交给该 lab——连接是**能力**，Rx 实例授权是**事实**。非"连接即可见对方全部 Rx"。
   - 文件：asset 仅经 file_reference（绑定对象）或限时 access_grant 暴露。
4. **撤销语义（冻结为 PROVISIONAL，待 V1.1 实测校准）**：
   - `connection.revoked`：即刻禁止新提交（E2E-04 同径）；**已接受的 Rx 继续走完生命周期**（lab 已投入工作，强行断线会造成数据/费用悬空——此选择记录在案，若官方行为相反再改）。
   - `access_grant.revoked`：立即失效，再访问 403。
   - `file_reference.revoked`：即刻不可见；不影响 asset 本体。
   - 机构停用（suspended）：登录拒绝、API 拒绝；数据保留按 retention_policy。
5. **ID 枚举防护**：跨机构/跨租户请求不存在对象 → 一律 403（而非 404），不泄露存在性；对枚举行为限速+告警。
6. **RBAC**：membership→role→permissions；高危操作（导出/财务/批量）强制 2FA（IAM-012）。

## 替代方案

| 方案 | 弃用原因 |
|---|---|
| 每租户独立库/schema | 自托管可行但 tenant 内 lab↔practice 协作反而复杂；保留为部署形态选项而非隔离机制 |
| 跨租户自由连接 | 击穿隔离边界，不可逆风险 → 否 |
| 仅应用层过滤 | 漏一处即越权 → 仅作第二保险 |
| 撤销即终止在途单 | 造成悬空工单/费用争议 → 改为"禁新不杀旧"（PROVISIONAL） |

## 后果

+ 三层边界清晰：tenant（RLS 硬隔离）→ org_connection（能力）→ 对象授权（Rx/file_reference/grant）。
+ 恶意枚举无信息收益；撤销语义可审计。
− 三层判定带来实现复杂度 → 由统一"可见性谓词构造器"收敛，单测覆盖矩阵（见 authz-test-matrix.md）。
− in-house lab 跨组织边界的真实行为待证（GAP-07 相关）。

## 关联

- 测试矩阵：`docs/architecture/authz-test-matrix.md`
- 角色×能力：`permission-matrix.md`
- 安全控制：`security-baseline.md` §1/§3
