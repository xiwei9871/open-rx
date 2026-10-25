# EasyRS Stage A.1 纠偏验收报告

> 范围：A1 Git 历史修复 · A2 状态边界 · A3 多租户授权 · A4 MVP API 契约 · A5 统计与 CI · A6 V1.1 交接。
> 结论先行：**PASS** — 六项纠偏全部落地，本地与远端 CI 全绿；PR 建链与默认分支切换按任务书规定的降级路径（手动 URL/操作说明）交付。

## 1. A1 — Git 分支与 PR（完成）

| 项 | 结果 |
|---|---|
| 原始分支 | `devin/easyrx-stage-a-baseline-v1` 保留，commit `cd8ccef` + `66eee03` 未动 |
| 审核分支 | `devin/easyrx-stage-a-review`，自 `origin/main` 新建 |
| 共同祖先 | `0618b0f`（`git merge-base` 已验证，Compare 不再报 no common ancestor） |
| 内容核对 | 53 个文件逐一 `git diff --no-index` 字节级一致（非仅数量） |
| PR | `gh` 无 API token，未代建；手动 URL：https://github.com/xiwei9871/open-rx/pull/new/devin/easyrx-stage-a-review |
| 默认分支 | 远端 HEAD 仍指向 baseline 分支。手动改法：GitHub → Settings → General → Default branch → 选 `main` → Update。或 `gh api -X PATCH repos/xiwei9871/open-rx -f default_branch=main`（需 token） |

## 2. A2 — 状态边界（完成）

`state-machines.md` 重写为 §0 所有权总表 + 六套独立状态机 + §7 事件映射 + §8 事件目录：

- `rx.status` = 纯临床生命周期（rx 模块独写）；`shipped/received/delivered` 移除
- `rx.fulfillment_status` = 投影列，仅 `shipment.*` 事件驱动，禁止 API 直写
- `shipment` = 物流唯一事实源（created→dispatched→in_transit→received→delivered/exception）
- `processing_job.status` 止于 `released`；`ready/printed/downloaded` 迁往新实体 `print_queue_item`
- 铁律入文：跨模块影响只能"事件 → 投影消费者"写入，禁止模块直写他域状态
- `domain-model.md`、`data-dictionary.md`、`openapi.yaml`（Rx/ProcessingJob schema 与 fulfillment_status readOnly）同步对齐

## 3. A3 — 多租户与跨机构授权（完成）

`adr/0006-tenancy-and-authz.md` 重写（REVISED）：

- 定义冻结：TENANT = 数据隔离边界（自托管=1）；ORGANIZATION = tenant 内机构（practice/lab/hybrid~）
- **跨 tenant 协作 V1 不支持**（需另立 federation ADR，绝不靠放宽 RLS）
- 三层边界：RLS(tenant) → org_connection(能力) → 对象授权(Rx/file_reference/grant)
- 撤销语义（PROVISIONAL，V-14 待校）：禁新提交、在途单继续、grant/reference 即时失效
- ID 枚举防护：跨权一律 403 同构响应，无存在性 oracle + 限速告警
- 新增 `authz-test-matrix.md`：22 条用例覆盖正常/未授权/撤销/枚举四类（AZ-01~36，编号非连续）

## 4. A4 — MVP API 契约（完成）

`openapi.yaml` v0.2.0-draft：

- 45 个 MVP（S0–S2）操作全部带：requestBody schema（变更类）、2xx 响应 schema、≥1 个 4xx、`x-scope`
- `Idempotency-Key`：submitRx/checkInRx/decideNotification/requestOrgConnection（幂等键）+ declareUpload（natural key: sha256+bytes）
- 版本冲突：`If-Match` 头（updatePatient/updateRx/replaceRxItems/submitRx/unsubmitRx）或 `expected_version` 字段（transition*/decideNotification），冲突→409 `version_conflict`/`version_drift`
- 状态约束：变更类操作带 `x-state-transition`；非法迁移→422 `illegal_transition`
- 关键字段验证：FDI 牙位 `^[1-4][1-8]$`、sha256 `^[0-9a-f]{64}$`、枚举/必填/min-max 就位
- 非 MVP 操作保持占位（不凑数），全部响应结构经 `tools/validate_contract.py` 机检：**45/45 ops，0 违规**
- redocly lint：0 error（warning 均为非 MVP 操作缺 4xx，符合"不补齐非 MVP"要求）

## 5. A5 — MVP 统计与 CI（完成）

- 新单一事实源 `tools/feature_disposition.py` → 生成 `docs/backlog/feature-disposition.csv`（167 行）
- **唯一主处置**：CORE 56 · SIMPLIFY 11 · MANUAL 2 · DEFER 3 · NOT_IN_MVP 95（56+11+2+3=72=研究-MVP；95=48+39+8）
- 口径映射：KEEP-SEC→CORE+`security-critical`(12 项)；CORE+MANUAL→MANUAL；SIMPLIFY/DEFER 部分交付→SIMPLIFY
- 旧 55/5/3 口径与自身 72 行不对账的根因已写入 mvp-release-plan §3（KEEP-SEC 混入、部分交付计延期、P1 手工项混入）
- `validate_baseline.py` +6 项 disposition 机检；`mvp-scope.md` 生成处置汇总与对账说明
- CI：redocly 钉 `1.25.15`（去 `@latest`）、`ubuntu-24.04`、新增 bundle+契约结构检查步骤；actions 为 @v4/@v5 主版本标签（如需 SHA 钉可再加）

## 6. A6 — V1.1 交接（完成）

`docs/research/v1.1-verification-checklist.md`：14 项风险排序任务（🔴5/🟡6/🟢3）——Create Rx 全流程、Check-in/Unsubmit/Completed 精确条件、三角权限差、Templates/Parts/Appliance 字段、3D Profiles、导出迁移、**剩余 33 源逐一过堂**、撤销语义。每项含方法（doc-read/ui-observe/api-observe）、判定标准、失败影响。

## 7. 验证结果

| 门 | 命令 | 结果 |
|---|---|---|
| 基线校验 | `python3 tools/validate_baseline.py` | **36/36 PASS**（新增 6 项 disposition 检查 + 2 个必需文档） |
| 生成物漂移 | `python3 tools/gen_backlog.py --check` | 18 files in sync |
| OpenAPI lint | `redocly@1.25.15 lint` | 0 error / 36 warning（非 MVP 4xx，符合范围约定） |
| 契约结构 | `redocly bundle` + `validate_contract.py` | 45/45 MVP ops，0 violations |
| 秘钥/PHI | CI 内置扫描步骤 | 本地 grep 复查无命中 |
| 远端 CI | GitHub Actions run 40085471241 | **completed / success**（commit `7dcfc23`，含新契约门） |

## 8. 遗留与声明

- 远端 CI 已实测：run `40085471241` on `7dcfc23` → **success**（本报告此次追加提交将再触发一轮）。
- PR 创建与默认分支切换仍需 `gh`/API 认证或手动操作——如实报告，不推断。
- `x-status: provisional` 的端点仍是占位设计，未固化为承诺行为。
- ADR-0006 §4 撤销语义为 PROVISIONAL 选择，列入 V-14 待校。
- 未启动任何业务功能编码；研究基线（167 ID、哈希、审计历史）未变。

## 判定

**PASS** — 六项纠偏全部完成：本地 36/36 + 契约 0 违规；远端 Actions run `40085562541`（HEAD `3826c55`）success。
CLI 认证缺失下的 PR/默认分支按任务书降级路径交付（手动 URL + 操作说明），不计失败项。
