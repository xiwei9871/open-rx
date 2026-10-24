# 领域模型 — EasyRx 开源替代系统 V1.0（冻结基线）

> **状态**：Stage A 冻结的**拟议模型**，不是 EasyRx 真实数据库结构。
> **惯例**：`= CONFIRMED` 官方/截图证据支持；`~ PROVISIONAL` 合理推断待验证；`? UNKNOWN` 不得编造。
> **覆盖**：12 个业务域。所有多租户表必须携带 `tenant_id`。

## 0. 12 域总览

| # | 域 | 核心实体 | 主要 Feature 前缀 |
|---|---|---|---|
| 1 | Organization & IAM | TENANT, ORGANIZATION, LOCATION, USER, MEMBERSHIP, ROLE, ORG_CONNECTION, ROSTER_MEMBER | IAM, SAFE-002 |
| 2 | Patient & Case | PATIENT, TREATMENT_CASE | PAT |
| 3 | Prescription & Templates | PRESCRIPTION, RX_ITEM, CATALOG_PART/APPLIANCE/TEMPLATE, RX_ANNOTATION | RX |
| 4 | Rx Dashboard & Status | （状态在 PRESCRIPTION）, SAVED_VIEW, TAG | FLOW, COM-009 |
| 5 | Communication | RX_COMMENT, CLINICAL_NOTIFICATION, APPROVAL, NOTIFICATION_PREF, RX_FEEDBACK, FORM_SUBMISSION | COM |
| 6 | Digital Asset | FILE_ASSET, FILE_REFERENCE, UPLOAD_SESSION | ASSET, RX-019, INT-005, SAFE-004/005 |
| 7 | 3D Editing | （交互式操作 → PROCESSING_JOB 输入） | EDIT |
| 8 | 3D AI Processing | PROCESSING_RECIPE, PROCESSING_JOB, QA_REPORT | AI, EDIT-014, SAFE-007 |
| 9 | Lab Production (MES) | PRODUCTION_ORDER, ORDER_ITEM, WORKFLOW, ACTIVITY, PRODUCTION_OPTION, PRODUCTION_STEP, WORK_TICKET, SHIPMENT, SERVICE_ORDER, HOLD_EVENT | LAB, FLOW-012/013 下游 |
| 10 | Finance & Reporting | PRICE_LIST, PROPOSAL, INVOICE, PAYMENT, ADJUSTMENT, STATEMENT, REPORT_RUN | FIN |
| 11 | External Integration | INTEGRATION_CONNECTION, INBOUND_SCAN_EVENT, WEBHOOK_ENDPOINT, DESKTOP_AGENT_SESSION | INT, PAT-007, ASSET-007 |
| 12 | Security & Compliance | AUDIT_EVENT, E_SIGNATURE, ACCESS_GRANT, BACKUP_RUN, DATA_EXPORT_REQUEST, RETENTION_POLICY | SAFE, IAM-012 |

## 1. Organization & IAM

```
TENANT 1─n ORGANIZATION 1─n LOCATION
ORGANIZATION 1─n MEMBERSHIP n─1 USER
MEMBERSHIP n─1 ROLE
ORGANIZATION 1─n ROSTER_MEMBER        # 医生/临床员工名册，不一定是登录用户
ORGANIZATION n─n ORGANIZATION  via ORG_CONNECTION (practice↔lab 授权边)
```

- `ORGANIZATION.kind ∈ {practice, lab, hybrid}` — in-house lab 存在（SRC: 截图/KB 提及 In-house lab），`hybrid` 为 `~ PROVISIONAL`。
- `ORG_CONNECTION` 是**显式授权边**：诊所提交 Rx 给实验室必须先存在 status=accepted 的连接（IAM-007 = CONFIRMED）。不允许凭 URL/ID 猜测访问。
- `ROSTER_MEMBER`（IAM-003/004/005）：医生、临床员工名册；`is_login_user` 区分名册记录与登录账号。医生禁用后历史处方与签署必须仍可审计（IAM-003 验收）。
- `MEMBERSHIP.role`：角色集合见 `permission-matrix.md`，全部 `~ PROVISIONAL`（GAP-02）。

## 2. Patient & Case

```
PATIENT 1─n TREATMENT_CASE 1─n PRESCRIPTION
```

- `PATIENT.id` = 内部随机 ID（不编码任何个人信息）。
- `PATIENT.external_ref + source_org_id` 复合唯一（PAT-003）；**禁止凭同名自动合并**（PAT-004 的生日只作人工识别辅助）。
- `TREATMENT_CASE`（PAT-008, T）：一个治疗过程含多次处方；阶段枚举 `? UNKNOWN`（暂 {active, completed, cancelled} PROVISIONAL）。
- `PATIENT.deleted_at` 软删除（PAT-009, T）：保留期、恢复与最终清除由 `RETENTION_POLICY` 控制，删除不物理移除审计与已交付记录。

## 3. Prescription & Templates

```
PRESCRIPTION 1─n RX_ITEM
PRESCRIPTION 1─n RX_ANNOTATION
PRESCRIPTION n─1 TREATMENT_CASE, n─1 ORG (issuing practice), n─1 ORG (receiving lab), n─1 LOCATION, n─1 ROSTER_MEMBER (doctor)
CATALOG_PART ⊂ CATALOG_APPLIANCE ⊂ CATALOG_TEMPLATE
CATALOG_TEMPLATE.owner_org_id + shared_with edges  (IAM-008 / RX-011 / RX-012)
```

- `PRESCRIPTION.rx_number` 唯一（RX-003）；格式 `? UNKNOWN`。Unsubmit→重提**保持同一 rx_number**（SRC24 确认按 Prescription ID 计费）。
- `RX_ITEM`：部件/器械 + 牙弓画布位置（RX-006..009）+ 牙位操作（拔牙/IPR/Resets，RX-016）。
- `CATALOG_*` 自建部件库（GAP-04）：不复制 EasyRx 500+ 库；字段含 `license_note`，首批经医生审查。
- `CATALOG_TEMPLATE`：保存（RX-010）、来源区分 lab/practice（RX-011）、分享权限 view/copy/edit（RX-012）；并发复制-再编辑不得污染原模板（E2E-13）。
- `RX_ANNOTATION`：自由文字（RX-013）、手绘线/折线（RX-014）、亚克力颜色（RX-015）。
- 专用表单：`PRESCRIPTION.form_type ∈ {standard, aligner, idb}`（RX-017/018，P1），子表单字段 `? UNKNOWN`。
- `RX_PDF`：版本化导出（RX-021），再生成保留历史（E2E-11）。

## 4. Rx Dashboard & Status

- Rx 状态机见 `state-machines.md` §1。工作台不是独立实体：`SAVED_VIEW`（FLOW-004, S）、`TAG`+`RX_TAG`（COM-009）。
- "Needed Soon" 预警（FLOW-014, S）= `due_date` 阈值派生，阈值规则 `? UNKNOWN`。

## 5. Communication & Collaboration

```
RX_COMMENT 1─n (threaded, ?层级深度 UNKNOWN)
CLINICAL_NOTIFICATION 1─0..1 APPROVAL
CLINICAL_NOTIFICATION n─0..n FILE_REFERENCE   # 附件级问题通知 COM-006
NOTIFICATION_PREF per USER per ORG
RX_FEEDBACK (rating, COM-010, P2)
FORM_SUBMISSION (EasyRx Forms, COM-012, P2)
```

- `CLINICAL_NOTIFICATION.kind ∈ {info, ack_required, approval_required, email_only}`（COM-002..005）。`approval_required` 必须产生结构化 `APPROVAL{decision, signer, version_binding}` —— 通知不是聊天（主报告 §2.1-6）。
- Share-with-colleague（COM-011, D2）：建模为限时 `ACCESS_GRANT`，细节 `NEEDS_VERIFICATION`。

## 6. Digital Asset Management

```
FILE_ASSET (immutable blob; sha256 dedup; parent_asset_id → version chain)
FILE_REFERENCE (asset → patient|rx|notification|order 授权边; role: original|optimized|processed|print_ready|attachment)
UPLOAD_SESSION (断点续传/分块, E2E-12)
```

- **原件永不覆盖**（主报告 §4.2）：任何"修改"产生新 FILE_ASSET + parent 链。
- 上传即入隔离区：AV/恶意网格检查 + 配额（ASSET-010/SAFE-005 合并口径）。
- 同一 FILE_ASSET 可经多条 FILE_REFERENCE 暴露给患者/Rx（ASSET-005）；撤权即删 reference，不删资产（E2E-14）。
- 下载一律走 `ACCESS_GRANT` 限时签名 URL（SAFE-004）。

## 7/8. 3D Editing & Processing

```
PROCESSING_RECIPE 1─n PROCESSING_JOB n─1 FILE_ASSET(input) 1─n FILE_ASSET(output)
PROCESSING_JOB 1─1 QA_REPORT
```

- `PROCESSING_RECIPE`（AI-015）：版本化参数集。已官方确认的参数（SRC04）：`processing_mode, trim_type, trim_margin_mm, base_height_mm, model_type, wall_thickness_mm, label_position, preserve_occlusion, extrude_palate, pts_type, gingival_clearance_mm, preserve_molars, molar_edge_distance_mm, include_normals`。
- **已确认约束**：PTS gingival clearance 至少比 trim margin 小 0.5mm（SRC04 页面所述，需按现行版本再验）。
- `PROCESSING_JOB` 记输入 hash、recipe 版本、引擎版本、参数快照、输出 hash、执行时长、QA 结论（SAFE-007）。
- 人工编辑（EDIT-*）= 交互会话产出"参数+结果"也落 PROCESSING_JOB，类型 `manual_edit`，与自动管线同一溯源模型。
- 打印流转标记 `print_status ∈ {ready, downloaded, printed}`（AI-016）独立于文件加工状态。

## 9. Laboratory Production (MES)

```
PRODUCTION_ORDER 1─n ORDER_ITEM (product+qty+teeth+price_snapshot)
WORKFLOW 1─n ACTIVITY 1─n PRODUCTION_OPTION
PRODUCTION_ORDER 1─n PRODUCTION_STEP (scheduled/actual, operator, equipment, cost)
PRODUCTION_ORDER 1─1 WORK_TICKET (per step per day?)
PRODUCTION_ORDER 1─n SHIPMENT 1─n SHIPMENT_EVENT
SERVICE_ORDER → 父 PRODUCTION_ORDER / Rx（Remake/Repair/Refinement 子单）
HOLD_EVENT (on-hold 原因历史)
```

- **Rx 状态 ≠ 生产订单状态**（主报告 §2.1-3）：映射表 `? UNKNOWN`（GAP-15），默认 1 Rx → 1 order `~ PROVISIONAL`。
- `ACTIVITY` 可换 `PRODUCTION_OPTION`（人工/打印/外包），各自工时成本，允许非线性单价（SRC09 确认存在，公式 UNKNOWN）。
- `SERVICE_ORDER.kind ∈ {remake, repair, refinement}`（LAB-017, D2）：必须关联原件，计费规则 `? UNKNOWN`。
- 收货与交付是两事件（主报告 §4.3）。

## 10. Finance & Reporting

```
PRICE_LIST (per lab, customer tier) 1─n PRICE_LIST_ITEM
PROPOSAL → INVOICE 1─n INVOICE_ITEM
PAYMENT n─n INVOICE via PAYMENT_ALLOCATION
ADJUSTMENT (credit/debit, 不回溯改历史)
STATEMENT (月结单, 可重生成)
```

- 价格为**下单时快照**（FIN-002 确认：变价不回溯）。
- 税额/免税客户（FIN-008, D2）`NEEDS_VERIFICATION`；币种、账期 `? UNKNOWN`（GAP-17）。
- Per-Script 计费观察（SRC24 抽验新发现）：按唯一 Prescription ID 计费 → 若本系统实现用量计费，Unsubmit-重提不重复计数。记 `RX-BILLING-01` 候选。

## 11. External Integrations

```
INTEGRATION_CONNECTION (vendor, auth_ref→secret store, status, scope)
INBOUND_SCAN_EVENT (vendor scan → patient/rx 关联; iTero auto-attach 仅提交前 — SRC24 确认)
DESKTOP_AGENT_SESSION (EasyFS 类本地代理; ASSET-007/INT-010 合并)
WEBHOOK_ENDPOINT / API_CLIENT (INT-011, T)
```

- MVP 仅有手动导入通道；任何厂商 API 需独立授权（GAP-14）。适配器模式，品牌逻辑不进入领域核心（ADR-0001/0006）。

## 12. Security & Compliance

```
AUDIT_EVENT (actor, action, object, before/after hash, ip, ts — 追加型)
E_SIGNATURE (签署归属: APPROVAL/RX 提交)
ACCESS_GRANT (限时、限次、可撤销)
BACKUP_RUN / RESTORE_DRILL (SAFE-006)
DATA_EXPORT_REQUEST (SAFE-009; 迁移出口, GAP-09)
RETENTION_POLICY (PAT-009 等的保留/清除规则)
```

## 13. 横切规则

1. `tenant_id` 存在于除字典表外所有表；任何查询默认带租户谓词（行级隔离，见 ADR-0006）。
2. 删除策略：患者/处方软删除；FILE_ASSET 原件不删；AUDIT_EVENT 永不删改。
3. 幂等：提交、check-in、webhook、job 触发全部要求 idempotency key（E2E-07）。
4. 并发：Rx/模板编辑用乐观锁（version 列），冲突不得静默覆盖（E2E-15）。
5. 事件：状态迁移一律写领域事件（outbox），事件名见 `state-machines.md` §4。
