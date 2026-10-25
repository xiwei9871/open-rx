# S1b.1 验收报告 — Rx 交付包、签署与并发安全

日期：2026-10-24（Final Gate 修订）· 分支：`devin/easyrs-stage-s1b` · 基线：`c847cc5`（S1b-Core）
范围：S1b1-01 ~ S1b1-05 定向修复；未扩展模板/审批/生产/AI/财务。

## 判定：**PASS（局部待远端 CI 确认）**

五项审核阻断点全部修复并有真实测试覆盖；远端 CI 结果为最终门槛。

## S1b1-01 真实 ZIP 交付包

`apps/api/app/modules/rx/bundle.py` + `app/pdfgen.py`：

```
RX{n}.zip
├── prescription.pdf   # reportlab 生成；患者/双方/医生/到期日/部件明细/备注/签署/附件
├── manifest.json      # 每条文件：entry/文件名、asset_id、kind、jaw、role、bytes、sha256
└── attachments/<jaw|attachment>-NN.<ext>   # 实际字节，逐条 S3 读取
```

- 逐对象校验：head 存在性 + ContentLength == 期望字节；流式 `iter_chunks`
  写入 ZIP（`ZipFile.open`，`force_zip64`），写后 SHA-256 复核。
- 文件名经 `_safe_name` 清理（`basename` 仅作用于文件名部分，
  `attachments/` 前缀保留——修掉了目录被 basename 吞掉的缺陷）。
- 临时 ZIP 用 `tempfile` 落盘，失败即 `unlink`；S3 上传成功但 DB 持久化
  失败时清理孤儿对象。
- 仅授权 FileReference 进入包（`subject_type="rx"` + granted_by 记录）。

## S1b1-02 两阶段下载 / Check-in 语义

- `POST /rx/{id}/bundle-download`：权限+状态校验 → 生成并上传 ZIP →
  同事务内原子 `submitted→checked_in`（`via=download`）+ transition +
  `rx_bundle` 落库 → 返回短期 presigned URL。
- `GET /rx/{id}/bundle` 改为**只读列表**（bundle 元数据）；presigned
  GET 天然只读。预取/重放不再触发接单。
- 打包失败 → 502/4xx，Rx 保持 `submitted`（测试
  `test_bundle_missing_object_aborts_without_checkin`）。
- 重复下载按 `content_fingerprint`（内容字段+部件配置+有效引用集合
  的 sha256）复用 ready bundle；状态 bump 不失效、内容变更必重建
  （Final Gate F2 修复：`rx_version >= version-1` 启发式已移除）。
- 诊所自下载永不 Check-in（`checked_in_via` 仅目标实验室置位）。
- ADR：`docs/architecture/adr/0008-rx-bundle-download-checkin.md`
  明确"下载=服务端成功备包并接受明确下载动作"，不虚构物理收齐。

## S1b1-03 服务端签署 Gate

`RxSubmit.signature_name` 必填 + `confirm_submit` 为**必填字段**
（无默认值，缺省 422——Final Gate F1），先验签再做任何状态工作。
实际持久化的签署事实（Final Gate 核对，不夸大）：`rx.signature_name`、
`rx.submitted_by_user_id`、`rx.submitted_at`（UTC timestamptz）、
`rx.signed_rx_version`（迁移 0008 新增列）；transition 行记录
`draft→submitted`；审计事件携带 `after_hash`。重复提交返回
`already_submitted`，不产生第二条签署记录。

## S1b1-04 并发与幂等

- `If-Match` 对 updateRx / replaceRxItems / submitRx / unsubmitRx /
  checkInRx **全部强制**：缺失 → 428，不符 → 409。
- `idempotency_record` 持久化首响应快照（status + json），key 唯一；
  同 key + 同请求 → 返回**首次快照**（不是最新态）；同 key + 不同
  载荷（含不同 If-Match）→ 409。
- Check-in 与 Unsubmit 并发：`FOR UPDATE` 行锁 + 状态机校验，恰一条
  转换成功（`test_concurrent_checkin_vs_unsubmit` 双独立会话）。
- `rx_transition.seq`（迁移 0007，BigInteger Identity）替代 created_at
  排序——修掉微秒并列导致历史顺序不稳定的问题。

## S1b1-05 CI 强制门

`asset-integration` Job 现执行 `test_assets.py + test_rx_s1b1.py` 并对
skipped=0 做 junit 硬门（REQUIRE_S3=1；rustfs service 常驻）。

## 测试结果

| 套件 | 结果 |
|---|---|
| `apps/api` 全量 | **99 passed, 6 skipped**（skip 仅本地无 S3 门控项） |
| `test_rx_s1b1.py` | 7 passed（真实 ZIP 字节、SHA-256 一致、check-in、
  幂等快照、428/409、签名 gate、并发） |
| `test_rx.py` | 18 passed |
| `test_contract.py` | 3 passed（op id 对齐） |
| Playwright | **9 passed**（新增 lab "Download & Check-in" 真实
  浏览器闭环：POST → presigned URL 新标签 → Checked-In via download） |
| `npm run build` | 通过 |

## 迁移

- `0006_s1b1_bundle_idem`：`rx_bundle`、`idempotency_record`（RLS）
- `0007_s1b1_transition_seq`：`rx_transition.seq` + `(rx_id, seq)` 索引

## Final Gate 定向修复（F1–F5，2026-10-24）

每项均先写失败测试再修复（修复前 10/12 红，修复后 12/12 绿）：

| # | 缺陷（负测证据） | 修复 |
|---|---|---|
| F1 | 无 `confirm_submit` 字段提交仍返回 200（默认值绕过）；签署版本未持久化 | `confirm_submit` 改为必填；新增 `rx.signed_rx_version` 列并在 submit 写入；`RxOut`/OpenAPI 同步 |
| F2 | 按钮 Check-in 后建包 → 追加 STL → 再次下载**复用了无附件旧包** | `content_fingerprint`（字段+部件+引用集 sha256）作为唯一复用键；`rx_version-1` 启发式移除 |
| F3 | PDF `Items: 0`、无患者/实验室/明细；非 Latin-1 静默变 `?` | build_bundle 真实查询（Patient/Organization/RosterMember/RxItem+CatalogItem）；reportlab 渲染，非 Latin-1 行用 CID 字体 STSong-Light；pypdf 提取验证中文不被替换 |
| F4 | flush 失败（无补偿范围）与 presign 失败（commit 之后才生成 URL）会留孤儿对象或假 Check-in | flush、presign、commit 全部纳入补偿区；任一失败删除已传对象且 Rx 不变；补偿边界写入 ADR-0008，不声称跨 S3/PG 单事务 |
| F5 | `idempotency_record.key` 全局唯一：他用户用同 key 提交被 409 碰撞 | 复合唯一 `(tenant_id, org_id, user_id, endpoint, key)`（迁移 0008）；回放核对 actor+endpoint+request_hash+对象授权 |

测试：`tests/test_rx_finalgate.py` 12 项；API 全量 111 passed /
6 skipped（skip 仅本地无 S3 门控）。迁移 `0008_finalgate`。

## 文档一致性修正（2026-10-24 追加）

- **A 指纹↔PDF 一致性**：`rx_snapshot()` 单一快照构造函数统一供给
  指纹与 PDF/manifest 渲染——患者姓名、双方机构名、医生显示名、
  目录 code/name 等可变展示字段全部纳入指纹。更名即产生新包；
  旧包以独立 storage_key 永久保留（GET 列表可见全部历史，禁止覆盖）。
  负测：患者改名后旧包被复用 → 修复后新包渲染新名（
  `test_pdf_reflects_patient_rename`）；目录改名同样重建
  （`test_display_rename_of_catalog_item_invalidates`）。
- **状态快照语义**：PDF/manifest 将状态标注为 `Status at generation`，
  并显式列出 `Signed version`。Check-in 只改变状态不改变内容 → 指纹
  排除 status/rx_version，Check-in 后重复下载仍复用同一历史包，PDF
  如实显示生成时刻的 `submitted`（`test_bundle_status_marked_as_
  generation_snapshot`）。
- **B 签署版本精确断言**：`test_signature_persisted_on_row` 改为逐项
  精确比较——建单 v1 → 加项 v2 → 提交绑定 v2（`signed_rx_version=2`、
  `version=3`），并核对持久化行。
- API 全量 **114 passed / 6 skipped**；E2E 9 passed；远端 CI 见最终报告。

## 未解决/风险

- presigned URL 转发窗口：短期 TTL 缓解；未做一次性令牌（后续阶段）。
- `in_progress/on_hold/completed` 等生产态仍未实现（S1b-Extended 范围）。
- 远端 CI（GitHub Actions）在推送前尚无本轮结果——以远端为准。
