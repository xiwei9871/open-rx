# S1b-Core 验收报告 — Rx 核心处方闭环

分支：`devin/easyrs-stage-s1b`（基线 `devin/easyrs-v11-evidence` @ `4697ffc`）
范围：**仅限** 创建 → 保存 → 提交 → 实验室 Check-in → 禁止撤回。
未实现：高级模板、通知审批、生产、财务、`transitionRx` 高级迁移、PDF 渲染、分享链接。

## 1. 证据修正（V1.1 四项差异）— 已提交 `4697ffc`

| 差异 | 修正来源 | 落点 |
|---|---|---|
| 实验室侧断连存在 | 2024-01 官方更新（SRC-D9） | connections-and-sharing.md、permission-matrix、feature map（V-14 部分升级） |
| 分享链接 24h→**72h**，逗号分隔多收件人 | 2023-09 官方更新（SRC-D8） | files-and-3d.md、rx-rules；5 次打开上限未见废止，保留 |
| 部件选项可强制必填（Prompt for Bands） | 2023 官方更新 | parts-templates-library.md、rx-rules；实现为 `catalog_item.option_schema.required` |
| 处方恢复工具 + 按账号删除权限 | 2025-01 官方更新 | rx-lifecycle.md、rx-rules、permission-matrix |
| 附带 | 默认医生/诊室/收货地址自动填充、AI Profile 保存（AI-015→CONFIRMED）、RM/RP/RF 标签、部分公开 API 存在 | 同批文档 |

Feature 证据分布：**129 CONFIRMED / 25 PARTIAL / 10 PROVISIONAL / 3 UNKNOWN**（167 项 ID 全保留）。

## 2. 实现清单

| 层 | 内容 |
|---|---|
| 迁移 | `0005_s1b_rx_core`：`catalog_item`（通用库 + lab 自有，`owner_org_id` 可空）、`rx`、`rx_item`、`rx_transition`（追加式状态轨迹）、`rx_comment`；全表 RLS；`rx_number_seq` |
| 模型 | `app/modules/rx/models.py` |
| API | `createRx / listRx(过滤器+counts) / getRx / updateRx(草稿+If-Match) / replaceRxItems(草稿) / submitRx(Idempotency-Key+签名) / unsubmitRx / checkInRx(幂等) / downloadRxBundle(下载即 check-in) / attachToRx / listRxComments / createRxComment / listRxTransitions / patientRxHistory / listParts / listAppliances` |
| 权限 | `rx:read`、`rx:write`；lab_technician 获得 rx 读写（接单是实验室侧写操作）；lab 不可签发处方 |
| 前端 | `RxList`（诊所列表+状态过滤+counts / 实验室收件箱+行内 Check-in）、`RxCreate`（患者/实验室/医生/部件+牙弓+必填选项）、`RxDetail`（草稿编辑、Save、Sign & Submit、Unsubmit、bundle 下载、评论、历史轨迹） |
| 规则落实 | check-in 后撤回 = 409 `already_checked_in`；lab 下载 bundle 自动 `checked_in_via=download`；提交需 ≥1 项 + `accepted` 连接；必填部件选项服务端校验；草稿对实验室不可见 |

## 3. 契约变更

- `checkInRx` 摘要修正（旧假设"下载≠接单"与 SRC03 矛盾，V1.1 已勘误，本次同步修正 spec）。
- 新增 `downloadRxBundle`、`listRxTransitions` 端点声明。
- `Rx` 增加 `patient_id / notes / checked_in_via / signature_name / items`；`RxSubmit` 增加 `signature_name`；`RxCreate` 增加 `notes`。
- `REQUIRED_SPEC_OPS` 登记全部 15 个新 op。

## 4. 测试结果（实跑计数）

| 套件 | 结果 |
|---|---|
| API 全套（含新 `test_rx.py` 15 项） | **89 passed, 6 skipped**（skip 仅限非 S3 环境下的 s3-compat 门控套件） |
| `test_rx.py` 明细 | 完整闭环 / 撤回回草稿 / bundle 下载 check-in（via=download）/ 诊所下载不触发 / 未连接实验室 422 / 无实验室或无部件 422 / 幂等重放+改体 409 / 必填部件选项 422+通过 / 草稿对实验室 403 / 实验室不可签发·不可撤回·不可改 / 诊所不可 check-in / 第三方法务实验室 403 / If-Match 冲突 + 患者 rx-history / 双方评论 / 附件授权后实验室可下载 |
| E2E（Chromium 实栈） | **8 passed**——含 rx.spec.ts 两例：浏览器全程 `创建→选部件→Save draft→Sign & Submit→实验室收件箱→Check in→诊所 Unsubmit 被拒（清晰错误提示）`；及 `提交→Check-in 前撤回→回 Saved→可再编辑` |
| 前端构建 | `tsc --noEmit && vite build` 通过 |

## 5. 状态机对齐

```
draft ──submit──▶ submitted ──check-in(button)──▶ checked_in
  ▲                  │
  └─────unsubmit─────┘         └─bundle download─┘(via=download, SRC03)
```

- `checked_in_via` 区分 button/download；`rx_transition` 表留全量审计轨迹。
- 撤回仅在 `submitted` 且 `checked_in_at IS NULL` 时允许。
- `in_progress` 保留为 EasyRS 内部态（无 EasyRx 官方等价，已在 V1.1 标注）。

## 6. 已知边界与遗留

- `transitionRx`（in_progress/on_hold/complete/cancel/reopen）、PDF、通知审批、模板 CRUD、分享链接、Rx 删除/恢复：均已在契约中定义但**本轮未实现**（契约测试只要求已实现 ⊆ spec，未实现 spec op 不构成漂移）。
- EasyRS 自有策略（非 EasyRx 事实）：提交需 ≥1 item；`notes` 长度限制；必填选项取自 `option_schema.required`。
- 撤回后重新提交是允许的（版本递增，幂等键清空后可重新签发）。

## 7. 结论

核心闭环在 API 与真实浏览器两端验证通过，满足进入下一轮（高级模板/通知/生产）前的最小可用处方管道。**建议状态：READY（S1b-Core 闭环完成）。**
