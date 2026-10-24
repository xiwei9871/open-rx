# 权限矩阵 V1.0（PROVISIONAL — GAP-02 未关闭）

> **全部内容为临时设计**，未经 EasyRx 实际账号逐角色验证。标注 `?` 的格子表示行为待确认，实现时默认 **deny**。
> 原则：最小权限 + 显式授权边。跨机构访问必须经 `org_connection` 或限时 `access_grant`；URL/ID 猜测必须 403 且不泄露元数据（E2E-03）。
> 三层边界（tenant → connection → 对象授权）与测试编排见 `adr/0006-tenancy-and-authz.md` 与 `authz-test-matrix.md`。

## 1. 角色目录（拟议）

| 角色 | 归属 | 说明 | 证据 |
|---|---|---|---|
| practice_admin | 诊所 | 机构配置、地点、名册、连接、成员 | D1(IAM-001..007) |
| practice_doctor | 诊所 | 开处方、审批通知、本人患者 | D1 |
| practice_staff | 诊所 | 建患者/草稿、上传、收货确认；权限子集 ? | D2 |
| lab_admin | 实验室 | 接单、生产、价目、财务、模板下发 | D1(LAB/FIN) |
| lab_technician | 实验室 | 工单执行、工序完成、QC 录入 | ~ |
| lab_frontdesk? | 实验室 | Written check-in、物流、对账（可并入 technician） | ? |
| tenant_support | 平台 | 只读排障；默认无患者数据权限 | T(新系统) |
| api_client | 集成 | OAuth2 client credentials，scope 限定 | T(INT-011) |
| desktop_agent | 集成 | 设备级凭证，仅上传/同步范围 | T(INT-010) |

名册成员（ROSTER_MEMBER，如被记入处方的医生/护士）**不等于登录用户**；无登录者不能操作，仅作归属记录（IAM-004）。

## 2. 能力 × 角色矩阵

图例：✅ 允许 · ➖ 拒绝 · ⭕ 限定条件 · `?` 待验证（默认拒绝）

### 组织与成员

| 能力 | practice_admin | practice_doctor | practice_staff | lab_admin | lab_technician |
|---|---|---|---|---|---|
| 管理本机构信息/地点 | ✅ | ➖ | ➖ | ✅(本lab) | ➖ |
| 管理名册/成员/角色 | ✅ | ➖ | `?` | ✅ | ➖ |
| 发起/接受机构连接 | ✅ | ➖ | ➖ | ✅ | ➖ |
| 撤销机构连接 | ✅ | ➖ | ➖ | ✅ | ➖ |

### 患者与处方

| 能力 | practice_admin | practice_doctor | practice_staff | lab_admin | lab_technician |
|---|---|---|---|---|---|
| 建/改患者 | ✅ | ✅ | ✅`?` | ➖ | ➖ |
| 看本机构患者/Rx | ✅ | ✅(自己? / 全所 `?`) | ⭕按地点? | ➖仅连接诊所提交给自己的 Rx | ➖分派工单关联? |
| 创建/编辑 Rx 草稿 | ✅ | ✅ | ⭕`?` | ➖ | ➖ |
| 提交 Rx 至已连接 lab | ✅ | ✅ | `?` | ➖ | ➖ |
| Unsubmit（未 check-in） | ✅ | ✅(本人? `?`) | `?` | ➖ | ➖ |
| 已 check-in 后撤回 | ➖（SRC24 确认） | ➖ | ➖ | ➖ | ➖ |
| 提交后追加附件 | ✅ | ✅ | ✅`?` | ➖(接收方收到通知) | ➖ |
| 看他人机构 Rx | ➖（E2E-03） | ➖ | ➖ | ➖ | ➖ |

### 实验室与生产

| 能力 | lab_admin | lab_technician | practice_admin | practice_doctor |
|---|---|---|---|---|
| Check-in / 退单 | ✅ | `?` | ➖ | ➖ |
| 录入书面处方（Written check-in） | ✅ | ✅`?` | ➖ | ➖ |
| 建/改生产订单与工序 | ✅ | ⭕工序执行 | ➖ | ➖ |
| 标记工序完成/QC | ✅ | ✅ | ➖ | ➖ |
| Hold / 解除 Hold | ✅ | `?` | ➖ | ➖ |
| 发起 Remake/Repair/Refinement 子单 | ✅ | `?` | ⭕诊所侧发起申请 `?` | `?` |
| 出货登记/追踪号 | ✅ | ✅`?` | ➖ | ➖ |
| 收货/交付确认 | ➖（诊所侧操作 FLOW-013） | ➖ | ✅ | ✅`?` |

### 财务（全 P2）

| 能力 | lab_admin | lab财务?（角色未定） | 诊所 |
|---|---|---|---|
| 价目表/客户分层价 | ✅ | `?` | ➖（看适用价 `?`） |
| Proposal/Invoice/调整/月结 | ✅ | `?` | ➖查看己方单据 |
| 收款登记 | ✅ | `?` | ➖ |
| 报表 | ✅ | `?` | ➖ |

### 3D 与加工

| 能力 | 角色 | 条件 |
|---|---|---|
| 上传/查看己方 STL | practice_* / lab_* | 经 FILE_REFERENCE 授权 |
| 人工编辑并保存派生版 | lab technician / doctor? `?` | 产生新 FILE_ASSET + job 记录 |
| 配置 recipe/自动处理 | lab_admin | recipe 版本不可改（AI-015/017） |
| 触发/取消 job | 授权 lab 用户 | idempotency + 审计 |
| 打印标记 ready/downloaded/printed | lab_* | 与文件状态解耦（AI-016） |

### 共享与安全

| 能力 | 规则 |
|---|---|
| 模板分享 | lab_admin → 指定 practice org_connection 内医生；perm∈{view,copy,edit}（IAM-008/RX-012） |
| 临时下载链接 | 任何外发文件经 access_grant（限时/限次/可撤销）；接收人无需账号（SAFE-004） |
| Share-with-colleague | COM-011 D2，模型同上；`NEEDS_VERIFICATION` |
| 审计日志查看 | org_admin 看本机构；tenant_support 受限 `?` |
| 数据导出 | org_admin 申请（SAFE-009）；导出含 PHI 需二次确认+审计 |

## 3. 未决问题（V1.1 必答）

1. EasyRx 实际套餐（Free/Connected/Premium/Enterprise?）差异对矩阵的影响（GAP-07）。
2. practice_staff 可提交 Rx 与否；doctor 可见全所还是仅本人。
3. 诊所内多 doctor 互相可见性与默认医生规则（IAM-003）。
4. lab 内角色细分（是否有独立于 admin 的财务/前台角色）。
5. 诊所发起的 remake 申请与 lab 发起子单的关系（GAP-08）。
6. tenant_support 的合规边界（是否可触达 PHI）。

在这些问题被实测回答前，矩阵按**更严格**一侧实现，验收用例固定当前行为。
