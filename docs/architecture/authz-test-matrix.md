# 授权测试矩阵 V1.0（A3 纠偏 — 规格与测试设计，无实现）

> 对应 ADR-0006 三层边界。每条用例给出：前置编排 → 动作 → 期望 → 覆盖 Feature。
> 判定规则：**任何"无权"场景必须 403 且响应体不得泄露对象存在性**（不用 404 区分）；越权尝试必须落 audit_event。

## 1. 测试夹具（命名约定）

- 租户 T1：组织 PA（practice）、LA（lab）、LB（lab 未连接）
- 租户 T2：组织 PC（practice）、LC（lab）
- 用户：pa_admin、pa_doctor(Dr.甲)、pa_staff；la_admin、la_tech；pc_admin
- 连接：PA↔LA accepted；PA↔LB 无；PC↔LC accepted
- 数据：PAT-1(PA)、RX-1（PA→LA, submitted）、RX-2（PA→LA, draft）、RX-3（PC→LC, submitted）、STL-1（挂 RX-1）

## 2. 正常授权访问

| # | 编排 | 动作 | 期望 | Feature |
|---|---|---|---|---|
| AZ-01 | 上 | pa_doctor 读 PAT-1 | 200 完整字段 | PAT-001 |
| AZ-02 | 上 | la_admin 读 RX-1 | 200（lab 视角字段） | LAB-001 |
| AZ-03 | 上 | la_admin 下载 STL-1（有效 reference + grant） | 302 签名 URL | ASSET-005/SAFE-004 |
| AZ-04 | 上 | pa_doctor 提交 RX-2→LA | 200 rx.submitted | RX-020/E2E-04 |
| AZ-05 | 上 | la_tech 读 RX-1 的关联 file_reference 列表 | 200 仅与 RX-1 相关 | ASSET-005 |

## 3. 未授权访问（同租户，无授权边）

| # | 编排 | 动作 | 期望 | Feature |
|---|---|---|---|---|
| AZ-10 | LB 未连接 | lb_admin 读 RX-1 | **403，无对象存在性** | E2E-03 |
| AZ-11 | 上 | PA 提交 RX-2→LB | 422 NoAcceptedConnection | E2E-04 |
| AZ-12 | 上 | lb_admin 直接访问 STL-1（无 reference） | 403 | ASSET-009 |
| AZ-13 | pa_staff 无财务权限 | 读 LA 的 invoice 列表 | 403 | FIN-005 |
| AZ-14 | la_tech | 修改 RX-1 临床字段（lab 只可生产侧） | 403/422 | RX-002/权限矩阵 |

## 4. 撤销授权后

| # | 编排 | 动作 | 期望 | Feature |
|---|---|---|---|---|
| AZ-20 | PA↔LA revoked | PA 提交新 RX-4→LA | 422 | E2E-04 |
| AZ-21 | 上 | la_admin 读已接受的 RX-1 | **仍 200**（在途单继续，ADR-0006 §4） | IAM-007 |
| AZ-22 | 上 | la_admin 读 PA 其它 Rx | 403（连接从来不是全量授权） | ADR-0006 |
| AZ-23 | access_grant 过期/撤销 | 第三方访问该 URL | 403 + audit | SAFE-004/E2E-14 |
| AZ-24 | file_reference revoked | la_admin 下载 STL-1 | 403（在途单内文件授权被单独撤） | ASSET-005 |

## 5. 恶意 ID 枚举与注入

| # | 编排 | 动作 | 期望 | Feature |
|---|---|---|---|---|
| AZ-30 | lb_admin 遍历 uuid 空间 | 探测 RX ID | 全部 403 同构响应（时序/体一致，无 oracle） | E2E-03 |
| AZ-31 | 上，高频枚举 | 触发限速 | 429 + 告警事件 | IAM-012 |
| AZ-32 | pa_doctor 访问 T2 的 PC 对象 ID | 跨租户读 | 403（RLS 层拦截，应用层兜底） | SAFE-002 |
| AZ-33 | 篡改 org_id 参数 | PA 用 LA 的 orgId 调接口 | 403（服务端以 token 机构为准，不采信 body） | IAM-011 |
| AZ-34 | 伪造 access_grant token | 猜 token_hash | 403 + audit；token 仅存哈希 | SAFE-004 |
| AZ-35 | 提交重复 Idempotency-Key 但不同负载 | 语义重放 | 409（键冲突须负载一致） | E2E-07 |
| AZ-36 | 并发：PA unsubmit 与 LA check-in 同刻 | 竞态 | 恰一个成功；另一者 409（version） | FLOW-008 |

## 6. 实现要求（测试落地时）

- 矩阵每行 → 一个自动化测试（API 级）；RLS 层另有 SQL 级越权测试（AZ-32 双保险）。
- 403 响应统一结构 `{code:"forbidden", trace_id}`，无对象元数据；测试断言响应体不包含对象字段。
- 所有越权尝试断言 `audit_event` 存在（action=access_denied）。
- 夹具必须用合成数据（SAFE-008）。
- AZ-21 语义若与官方实测冲突，改 ADR-0006 并回归本矩阵——**测试随规则走，不反向**。
