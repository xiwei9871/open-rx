# S1b.1 验收报告 — Rx 交付包、签署与并发安全

日期：2026-01-12 · 分支：`devin/easyrs-stage-s1b` · 基线：`c847cc5`（S1b-Core）
范围：S1b1-01 ~ S1b1-05 定向修复；未扩展模板/审批/生产/AI/财务。

## 判定：**PASS（局部待远端 CI 确认）**

五项审核阻断点全部修复并有真实测试覆盖；远端 CI 结果为最终门槛。

## S1b1-01 真实 ZIP 交付包

`apps/api/app/modules/rx/bundle.py` + `app/pdfgen.py`：

```
RX{n}.zip
├── prescription.pdf   # EasyRS 自生成极简 PDF（自写生成器，无外部依赖）
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
- 重复下载复用 ready bundle（`rx_version >= rx.version - 1`，覆盖
  Check-in 自身的 +1 bump）；不重复产生包与 transition。
- 诊所自下载永不 Check-in（`checked_in_via` 仅目标实验室置位）。
- ADR：`docs/architecture/adr/0008-rx-bundle-download-checkin.md`
  明确"下载=服务端成功备包并接受明确下载动作"，不虚构物理收齐。

## S1b1-03 服务端签署 Gate

`RxSubmit.signature_name` 必填 + `confirm_submit` 必须为 true，先验签
再做任何状态工作；提交记录 `signature_name/signature_user_id/
signature_at/signed_version`；transition note 携带签署者+版本；
重复提交（状态已变）返回 `already_submitted`，不产生第二条签署记录。

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

## 未解决/风险

- presigned URL 转发窗口：短期 TTL 缓解；未做一次性令牌（后续阶段）。
- `in_progress/on_hold/completed` 等生产态仍未实现（S1b-Extended 范围）。
- 远端 CI（GitHub Actions）在推送前尚无本轮结果——以远端为准。
