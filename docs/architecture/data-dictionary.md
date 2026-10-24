# 数据字典 V1.0（Stage A 冻结）

> 字段级**拟议**字典。标记：`?` = 未验证/待 V1.1 实测；`~` = 合理推断。
> 通用列（省略逐表重复）：`id uuid PK`、`tenant_id uuid FK→tenant`、`created_at`、`updated_at`、`created_by uuid?`。
> 未列出 = 官方未披露，**不允许编造默认值**。

## 命名与类型约定

- ID：UUIDv7（时间有序，索引友好）；对外编号单独列（如 `rx_number`）。
- 金额：`numeric(12,2)` + `currency char(3)`；禁止 float。
- 时间：`timestamptz`；业务日期 `date` + 机构时区换算（IAM-010）。
- 枚举：PG enum 或 check 约束；状态字段见 `state-machines.md`。
- JSONB 仅用于非关系型载荷（参数快照、表单答案），不作查询主键。

## 1. Organization & IAM

### tenant
| col | type | note |
|---|---|---|
| name | text | 部署内租户名（自托管场景通常=1） |

### organization
| col | type | constraint | note |
|---|---|---|---|
| kind | enum(practice,lab,hybrid~) | not null | in-house lab → hybrid 待证 |
| name | text | | |
| status | enum(active,suspended~) | | |
| settings | jsonb | | 时区、工作日历等 |

UK: (tenant_id, kind, name)~ ；IDX: (tenant_id, kind)

### location
| col | type | note |
|---|---|---|
| org_id | uuid FK | |
| name / address / phone | text | 送货地址来源（LAB-004） |
UK: (org_id, name)~

### user / membership / role
| table | key cols & constraints |
|---|---|
| user | `email citext UK`, `password_hash`（或外部 IdP subject）, `totp_secret_ref`（IAM-012）, `status` |
| membership | `(org_id,user_id) UK`, `role_id FK`, `status enum(invited,active,disabled)` |
| role | `(org_id,name) UK`, `permissions jsonb` — 矩阵见 permission-matrix.md（PROVISIONAL） |

### roster_member
| col | note |
|---|---|
| org_id FK / kind enum(doctor,staff) / display_name / credentials / is_default (IAM-003) / is_required_enabled (IAM-005) / linked_user_id? | 名册≠登录账号（IAM-004） |

### org_connection
| col | note |
|---|---|
| practice_org_id FK / lab_org_id FK / status enum(pending,accepted,revoked,expired~) / granted_scopes jsonb / requested_by | UK(practice_org_id, lab_org_id)；提交 Rx 前置条件（IAM-007, E2E-04） |

## 2. Patient & Case

### patient
| col | constraint | note |
|---|---|---|
| org_id FK | IDX(org_id, last_name, first_name)~ | 名称检索 |
| external_ref text | UK(org_id, external_ref) where not null | PAT-003；复合含来源机构 |
| dob date | | 同名识别辅助（PAT-004），**不作合并键** |
| deleted_at timestamptz | | 软删除 PAT-009；IDX partial where null |

### treatment_case
| col | note |
|---|---|
| patient_id FK / label? / stage enum(active,completed,cancelled)~? / opened_at / closed_at? |

## 3. Prescription & Templates

### prescription
| col | constraint | note |
|---|---|---|
| rx_number text | UK(tenant_id) | RX-003；格式 ?；**unsubmit-重提不变** |
| case_id FK / practice_org_id FK / lab_org_id FK / location_id FK / doctor_id FK→roster_member | | 提交时 lab 需 org_connection.accepted |
| form_type enum(standard,aligner,idb) | | 子表单 schema 按类型存 `form_payload jsonb` ? |
| status | 状态机 §1 | IDX(lab_org_id,status), IDX(practice_org_id,status), IDX(due_date) |
| due_date date | | RX-002 |
| version int | | 乐观锁 E2E-15 |
| submitted_at / checked_in_at / completed_at / shipped_at / received_at / delivered_at | | 状态时间戳分列以便审计 |

### rx_item
| col | note |
|---|---|
| rx_id FK / appliance_id FK / arch enum(upper,lower,both) / tooth_map jsonb（牙位+操作 extraction/ipr/reset, RX-016）/ options jsonb（RX-009）/ qty smallint |

### catalog_part / catalog_appliance / catalog_template
| table | cols |
|---|---|
| catalog_part | `code`, `name`, `category`, `tooth_compatible jsonb`, `license_note`(GAP-04), `source enum(custom,licensed)` |
| catalog_appliance | part↔appliance join `appliance_part(part_id,qty,options)` |
| catalog_template | `owner_org_id`, `name`, `payload jsonb`, `visibility enum(private,shared)` + `template_share(template_id, org_id, perm enum(view,copy,edit))`（IAM-008/RX-012） |

### rx_annotation / rx_pdf
| table | cols |
|---|---|
| rx_annotation | `kind enum(free_text,stroke,polyline,color_note)`, `payload jsonb`（RX-013/014/015） |
| rx_pdf | `rx_id`, `version`, `file_asset_id FK`, `generated_at` — 重生成留历史（E2E-11） |

## 4. Dashboard

| table | cols |
|---|---|
| saved_view | `org_id`,`user_id`,`name`,`filters jsonb`(FLOW-003 维度: office/doctor/lab/tag), `is_default`(FLOW-004 S) |
| tag / rx_tag | `tag(org_id,name,color)`（COM-009）；`rx_tag(rx_id,tag_id)` UK |

## 5. Communication

| table | key cols |
|---|---|
| rx_comment | `rx_id`,`author_membership_id`,`parent_id?`,`body`,`edited_at?` |
| clinical_notification | `rx_id`,`kind enum(info,ack_required,approval_required,email_only)`,`subject`,`body`,`file_reference_id?`(COM-006),`created_by_org_id` |
| approval | `notification_id UK`,`decision enum(approved,rejected,changes_requested)`,`signer_user_id`,`signature_id FK`,`rx_version int`（决策绑定版本，主报告§2.1-6）,`decided_at` |
| notification_pref | `user_id`,`org_id`,`channel_prefs jsonb`（COM-008；与 COM-005 冲突规则 ?） |
| rx_feedback | `rx_id UK?`,`score smallint`,`comment`,`lab_org_id`（COM-010 P2） |
| form_submission | `form_def_id`,`rx_id?`,`patient_id?`,`answers jsonb`,`signed_at?`（COM-012 D2） |

## 6. Digital Asset

### file_asset
| col | constraint | note |
|---|---|---|
| sha256 bytea | UK(tenant_id, sha256) | ASSET-008 内容去重 |
| parent_asset_id FK | | ASSET-009 版本链；原件 parent=null 且不可变 |
| kind enum(stl,pdf,image,other) / jaw enum(upper,lower,na) | | ASSET-001 颌位分类 |
| bytes bigint / storage_key text | | S3 key = hash 寻址，匿名命名（SAFE 设计） |
| scan_status enum(pending,clean,infected,failed) | | 隔离区 ASSET-010/SAFE-005 |
| provenance jsonb | | 产生该资产的 job/上传信息 |

### file_reference
| col | note |
|---|---|
| asset_id FK / subject_type enum(patient,rx,notification,order) + subject_id / role enum(original,optimized,processed,print_ready,attachment) / granted_by_org_id / revoked_at? | 授权边；撤权=置 revoked_at（E2E-14） |

### upload_session
`uploader`, `bytes_expected`, `bytes_received`, `state`, `expires_at`（E2E-12 断点续传/失败不产损坏资产）

## 7/8. 3D Processing

### processing_recipe
| col | note |
|---|---|
| org_id / name / version int（不可改，改=新版本 AI-015/AI-017） | |
| params jsonb | 已确认键集合见 domain-model §8（SRC04）；校验规则含 clearance < trim_margin − 0.5mm（待再验） |

### processing_job
| col | constraint | note |
|---|---|---|
| input_asset_id FK / recipe_id+recipe_version / engine enum(manual_edit,auto_pipeline,abr,blockout,pts) + engine_version / params_snapshot jsonb | | SAFE-007 溯源 |
| status 状态机§2 / idempotency_key UK / attempt int / error jsonb | | AI-017 重试/取消 |
| output_asset_id FK? / duration_ms | | |

### qa_report
`job_id UK`, `checks jsonb`（watertight/自交/边界/壁厚/体积… EDIT-014）, `verdict enum(pass,warn,fail)`, `reviewed_by?`

## 9. Lab MES

### production_order / order_item
| table | cols |
|---|---|
| production_order | `rx_id FK?`（纸质录入可空 LAB-003/005）, `lab_org_id`, `order_number UK`, `status`（状态机§3）, `priority?`, `promised_date`（LAB-016 计算存结果+依据?） |
| order_item | `order_id`, `product_id FK`, `qty`, `tooth_map jsonb`, `price_snapshot numeric`, `cost_snapshot?`（FIN-002 不回溯） |

### workflow / activity / production_option / production_step
| table | cols |
|---|---|
| workflow | `lab_org_id`,`name`,`is_default` |
| activity | `workflow_id`,`seq`,`name`,`planned_days`（LAB-012） |
| production_option | `activity_id`,`method enum(manual,print,outsource,…?)`,`cost_model jsonb`（非线性 LAB-013 ?） |
| production_step | `order_item_id`,`activity_id`,`option_id FK?`,`assignee`,`equipment_ref?`,`planned_start/end`,`actual_start/end`,`status`,`finished_by`（LAB-015） |

### work_ticket / hold_event / service_order / shipment
| table | cols |
|---|---|
| work_ticket | `order_id`,`step_id?`,`payload jsonb`,`printed_at`（LAB-014 D2） |
| hold_event | `order_id`,`reason`,`started/ended`,`created_by`（LAB-018） |
| service_order | `parent_order_id`,`kind enum(remake,repair,refinement)`,`charge_policy ?`,`rx_id`（LAB-017/GAP-08） |
| shipment / shipment_event | `order_id`,`carrier`,`tracking_no`,`events(ts,status)`；`delivered_at` 独立字段（收货≠交付） |

## 10. Finance

| table | cols |
|---|---|
| price_list / price_list_item | `lab_org_id`,`customer_tier?`,`currency`；item:`product_id`,`unit_price`（FIN-001） |
| proposal | `order_id?`,`status enum(draft,sent,accepted,expired)`,`lines jsonb`（FIN-004 D2） |
| invoice / invoice_item | `order_id`,`number UK`,`issue_date`,`due_date`,`tax_total`,`status`（FIN-005） |
| payment / payment_allocation | `method`,`amount`,`received_at`；allocation `(payment_id,invoice_id,amount)`（FIN-006） |
| adjustment | `invoice_id`,`kind enum(credit,debit)`,`amount`,`reason`（FIN-007） |
| statement | `customer_org_id`,`period`,`regen_of_id?`（FIN-009 重生成链） |
| tax_profile | `org_id`,`rules jsonb`（FIN-008 D2, ?） |
| report_run | `kind enum(sales,aging,orders,kpi)`,`params`,`file_asset_id`（FIN-013/014） |

## 11. Integration

| table | cols |
|---|---|
| integration_connection | `org_id`,`vendor`,`status`,`credentials_ref`（→秘钥存储，不入库明文）,`scope`,`last_sync_at` |
| inbound_scan_event | `connection_id`,`vendor_case_ref`,`asset_id`,`matched_patient_id?`,`state enum(unmatched,auto_attached,manual_matched,rejected)`（iTero 仅提交前自动挂 — SRC24） |
| desktop_agent_session | `org_id`,`device_label`,`sync_roots jsonb`,`last_seen`（INT-010） |
| webhook_endpoint / api_client | `org_id`,`url`,`secret_ref`,`event_filter`,`status`（INT-011 T） |

## 12. Security & Compliance

| table | cols |
|---|---|
| audit_event | `actor_user_id`,`org_id`,`action`,`object_type`,`object_id`,`before_hash`,`after_hash`,`ip`,`user_agent`,`ts`；**仅追加**；IDX(object_type,object_id,ts) |
| e_signature | `signer_user_id`,`meaning`,`object_type`,`object_id`,`payload_hash`,`signed_at` |
| access_grant | `asset_id`,`granted_to`,`expires_at`,`max_uses`,`revoked_at`,`token_hash`（SAFE-004） |
| backup_run / restore_drill | `kind`,`started/finished`,`bytes`,`verify_status`（SAFE-006） |
| data_export_request | `org_id`,`requested_by`,`scope`,`status`,`output_asset_id`（SAFE-009） |
| retention_policy | `org_id`,`entity`,`retention_days`,`legal_hold`（PAT-009） |

## 13. 索引策略

- 所有多租户表：`(tenant_id, …)` 前缀复合索引；高频列表（rx by lab+status、jobs by status）已列 IDX。
- `file_asset` 大对象只在对象存储；DB 仅存元数据。
- `audit_event` 分区按月（体量）；`processing_job` 按 status 部分索引。
- `patient(external_ref)` 部分唯一索引（where external_ref is not null）避免空值冲突。

## 14. 明确 UNKNOWN（V1.1 必须回写）

`rx_number` 格式；treatment_case 阶段全集；aligner/idb 表单字段；notification 与 COM-005/008 冲突优先级；production_option 成本公式；service_order 计费；tax 规则；rx↔order 映射基数；lab 各套餐可用的工作流分支（GAP-07）；VisualDLP 同步方向（GAP-15）。
