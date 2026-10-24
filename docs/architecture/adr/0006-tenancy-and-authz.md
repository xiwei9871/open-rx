# ADR-0006 多租户与授权：单库 + RLS + 显式授权边

- **状态**：PROPOSED
- **日期**：2026-10-24

## 背景
自托管场景租户数少（常=1），云端多租户需强隔离；诊所↔实验室共享是**显式授权**而非全局可见（IAM-007、E2E-03/04、SAFE-002）。

## 决策
- 单库多租户：每表 `tenant_id`；PostgreSQL Row-Level-Security 按 `app.tenant_id` 强制 + 应用层谓词（双保险）。
- 跨机构可见性只有两个机制：`org_connection(status=accepted, scopes)` 与 `file_reference/access_grant`；无第三种路径。
- RBAC：membership→role→permissions(jsonb)；高危操作（导出、财务、批量）强制 2FA + 二次确认（IAM-012）。
- 对象级：每次查询经"可见性谓词构造器"，单测覆盖越权矩阵。

## 替代方案
| 方案 | 原因 |
|---|---|
| 每租户独立库/模式 | 自托管友好但跨机构协作（lab-practice）变复杂 → 否 |
| 仅应用层过滤 | 漏一处即越权 → 否（仍保留应用层作为二保险） |
| 行级安全唯一依赖 | 迁移/运维复杂，保留但与谓词并用 |

## 后果
+ 默认拒绝、授权边可审计可撤销；隔离可用 SQL 级测试证明。
− RLS 调试与迁移有学习成本；连接 scopes 粒度需实测校准（GAP-02/07）。
- 角色矩阵全部 PROVISIONAL，实现取严格侧（permission-matrix.md）。

## 备注
`rx.lab_org_id` 可见性 = 连接接受后**按 Rx 实例**授权，非全量共享。
