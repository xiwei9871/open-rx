# ADR-0008 Rx 交付包两阶段下载与 Check-in 语义界定（EasyRS 自有规则）

- **状态**：ACCEPTED（S1b.1）
- **日期**：2026-01-12
- **关联**：S1b1-02；`docs/research/v1.1-evidence/` SRC03（EasyRx 下载即 Check-in 的证据）

## 背景

EasyRx 官方证据（SRC03）证实：实验室侧点击/下载处方包会将 Rx 置为
Checked-In。S1b-Core 初版把该语义塞进 `GET /rx/{id}/bundle` 并在提交
状态后才生成 ZIP，产生三个缺陷：

1. GET 修改业务状态——预取、爬虫、重复请求都可能"接单"。
2. 先置 Checked-In 后打包——打包失败时处方已锁、交付不存在。
3. 无真实文件——ZIP 只有清单没有附件本体。

HTTP 服务端无法证明客户端"已完整收到字节"。因此必须把"下载触发
Check-in"界定为可复核的服务端事件，而非虚构物理下载完成。

## 决策

分两阶段：

- **阶段 A（隐式于 POST 内部）**：`POST /rx/{id}/bundle-download`
  先做权限/状态校验，再生成真实 ZIP（`prescription.pdf` +
  `manifest.json` + `attachments/*`，逐对象校验存在性、大小、
  SHA-256），上传对象存储。任一步失败 → Rx 保持 `submitted`，
  清理孤儿对象，不产生 transition/审计假成功。
- **阶段 B**：上传成功后同一事务内原子完成
  `submitted → checked_in`（`checked_in_via=download`）+ 追加
  `rx_transition` + 持久化 `rx_bundle` 记录，返回短期有效 presigned
  URL。浏览器随后的 `GET`（presigned URL 或 `GET /rx/{id}/bundle`
  列表）为纯读操作，永不改状态。

"下载触发 Check-in"在 EasyRS 中精确定义为：**交付包成功生成并落库 +
明确的已认证下载动作被接受**，而非字节到达对端。

幂等与复用：同内容版本（`rx.version` 或 `version-1`，因 Check-in 自身
只 bump 版本不改内容）的 ready bundle 直接复用；内容变更（条目、字段、
附件）一律 bump `rx.version` 使旧包失效。Check-in 与 Unsubmit 并发由
行锁 + 版本校验保证恰有一条转换成功。

诊所自下载同一路径但不触发 Check-in（`checked_in_via` 仅对目标实验室
置位）。

## 替代方案

| 方案 | 弃用原因 |
|---|---|
| GET 内改状态（S1b 初版） | 预取/重放副作用不可控，验收明确否决 |
| 预生成 + 独立确认端点 | 双端点状态机更复杂；bundle 过期需 GC，收益低 |
| 下载进度回执后才 check-in | 依赖客户端上报，不可验证；语义超出售方需要 |
| EasyRx 原始 GET 语义照搬 | 干净实现要求以安全 HTTP 语义重新表达同一业务结果 |

## 后果

+ 状态变更只发生在明确 POST；ZIP 内容与 Check-in 同一事务。
+ 附件缺失/哈希不符 → BundleError → 不 Check-in，处方维持 `submitted`。
+ bundle 记录（storage_key、sha256、bytes、rx_version）可独立审计。
− presigned URL 泄露窗口内可被转发（短期 TTL + 会话内生成缓解）。
− "接单"时间点 = 服务端接受下载动作，早于对端实际收齐字节——已在
  本文档明示，不声称更多。
