# 研究基线审计报告 — EasyRx 开源替代系统 Stage A

> **审计日期**：2026-10-24
> **审计对象**：`research/` 目录下 V1.0 交付（主报告 MD、167 项功能 CSV、37 条来源 CSV、机器可读 JSON、交付说明 TXT）
> **审计性质**：结构与一致性审计 + 抽样内容核验。**不重新验证 EasyRx 系统行为**，不改写研究结论，不增删 Feature ID。
> **工具**：`tools/validate_baseline.py`（CI 可重复执行）；基线 SHA-256 固定于 `docs/audit/research-sha256.txt`。

## 1. 结论摘要

| 维度 | 结果 |
|---|---|
| 功能条目完整性 | 167/167，CSV 与 JSON 逐字段一致（0 处差异） |
| ID 结构 | 12 个前缀全部连续无跳号，前缀与模块映射一致 |
| 枚举字段 | evidence / phase / complexity / implementation_status 全部合法，无空必填项 |
| 来源引用 | 所有 `source_ids` 均存在于来源索引；`source_urls` 与索引逐条配对（`,`/ `;` 分隔约定一致） |
| 证据分布 | D1=118 / D2=23 / S=4 / T=22，与主报告 §0 一致 |
| 阶段分布 | MVP=72 / P1=48 / P2=39 / P3=8，与主报告一致 |
| 公开来源可达性 | 36/36 HTTP 200（2026-10-24）；SCR 为私有占位符，无 URL |
| 重名检查 | 无重复 feature 名称 |
| 内容抽样核验 | SRC24、SRC26、SRC28 正文核验通过（见 §4） |

**总体判断**：V1.0 数据基线在结构上是干净、自洽、可追溯的，可作为 Stage A 工程基线使用。审计发现 14 组功能重叠/边界待澄清项、32 项 NEEDS_VERIFICATION 标记，全部登记于 `docs/audit/audit-flags.csv`，不改动原始清单。

## 2. 机械校验明细（validate_baseline.py）

脚本执行 23 项检查：研究文件 5 个且哈希固定、CSV↔JSON 全字段对齐、ID 唯一/格式/前缀/连续性、枚举合法、必填非空、来源配对、证据与阶段分布、S 级条目仅引用 SCR、交付文档齐备、backlog 一致性、OpenAPI/Mermaid 结构、秘钥泄漏扫描。本次审计时研究侧 17 项全部 PASS。

**已固定的分隔约定**：`source_ids` 多值用英文逗号 `,`；`source_urls` 多值用 ` ; `。CI 已按此校验，后续维护不得变更。

## 3. 已确认功能 vs 新系统建议功能

- **EasyRx 已确认（D1）**：118 项 — 官方正文直接描述。措辞上仍须注意：官方文档可能有历史版本差异，D1 ≠ 已实测。
- **目录级确认（D2）**：23 项 — 主题存在，实现细节未确认。全部标记 `NEEDS_VERIFICATION`。
- **仅截图（S）**：4 项（FLOW-003、FLOW-004、FLOW-014、FIN-014）— 只引用 SCR 私有截图。标记 `NEEDS_VERIFICATION`；公开文档与代码注释中**不得引用截图内容**，只能引用 Feature ID。
- **新系统建议（T）**：22 项（IAM-011/012、PAT-008/009、FLOW-016、ASSET-008/009/010、EDIT-014、AI-017、LAB-020、INT-011、SAFE-001~010）— 标记 `PROPOSED`。**任何文档、Issue、代码注释不得把 T 项写成"EasyRx 已有功能"**。

另有 6 个 D1 项同时引用了 SCR 作为补充来源（FLOW-001/011/013/017、COM-009、AI-015）：其 D1 地位由公开来源独立支撑，合规；但截图侧的补充细节同样不可公开。

## 4. 来源内容抽样核验

| 来源 | 核验内容 | 结果 |
|---|---|---|
| SRC24（Unsubmit 规则） | 正文确认：Check-in 后不可 Unsubmit；撤回回 Saved；提交后可手动补传文件；iTero 自动附件仅限提交前 | 与 FLOW-005/008/009/010 一致 ✅ |
| SRC26（`/articles/in` 短 slug） | 实际为 "The Enhanced Invisalign Tracking Lab" 文章 | 与" Invisalign tracking "主题一致 ✅ |
| SRC28（Practice License Agreement） | §5 确认含 **$150 处理费** + 书面请求提供 User Content 数字副本条款；§6(c) 含禁止反向工程/反编译条款 | 与主报告 §11 引用一致 ✅ |

**局限**：KB 为前端渲染页面，HTTP 200 仅证明可达性；本轮只抽验 3 个来源正文，未逐篇核对 118 项 D1 引文。此限制已计入 GAP-19。

**抽样新发现（不修改清单，仅登记）**：SRC24 正文披露 Per-Script 计费按唯一 Prescription ID 计费，Unsubmit 后重提同一 Rx 只计 1 次 —— 该规则在 167 项中无对应条目，建议 V1.1 增补 FIN/RX 域条目（暂记为候选 `RX-BILLING-01`，不占用正式 ID）。

## 5. 功能重叠与边界待澄清（OVERLAP，14 组）

| 组 | 条目 | 待澄清问题 |
|---|---|---|
| 1 | ASSET-007 ↔ INT-010 | EasyFS 类访问在两个模块重复登记 → 合并为"桌面代理适配器"需求 |
| 2 | ASSET-002 ↔ ASSET-009 | D1 观察到的版本区分与 T 设计的版本链/不可变原件需统一验收口径 |
| 3 | FLOW-012 ↔ LAB-019 | Rx 端 Shipped 与实验室物流签收不能双写状态，需单一事实源 |
| 4 | FLOW-011 ↔ LAB-015 | Rx Complete 与 MES 完成者追踪的映射未验证（GAP-15） |
| 5 | EDIT-013 ↔ AI-006 | 人工/AI 去托槽共享牙面质量验收标准，但为独立实现路径 |
| 6 | RX-019 ↔ ASSET-001 | 处方附件上传与 STL 颌位分类上传需统一为同一管线 |
| 7 | IAM-008 ↔ RX-012 | 实验室→医生模板授权边与模板权限需合并建模 |
| 8 | COM-006 ↔ LAB-002 | 附件级问题通知与实验室审核问题工作流需共用通知对象 |
| 9 | COM-005 ↔ COM-008 | "仅 Email"与偏好设置存在冲突场景，需优先级规则 |
| 10 | FLOW-007 ↔ FLOW-006 | ZIP 下载自动 Check-in 属旧行为；新系统显式区分"下载"与"接单" |
| 11 | INT-005 ↔ ASSET-001 | 通用扫描仪导入应复用资产管线而非独立通道 |
| 12 | SAFE-005 ↔ ASSET-010 | 恶意文件扫描与配额隔离重复登记，合并到上传管线 |
| 13 | IAM-012 ↔ SAFE-001 | 2FA 访问审计与全局审计日志需统一审计事件模型 |
| 14 | FIN-013 ↔ FIN-014 | 财务报表与业务绩效统计的指标口径需定义边界 |

处理方式：不合并、不改 ID；在 `feature-traceability.csv` 中把同组条目映射到同一开发任务，由任务规格统一口径。

## 6. 20 项差距登记处置（GAP-01 ~ GAP-20）

| GAP | 处置 | 落点 |
|---|---|---|
| 01 信息架构不全 | 保留 OPEN，列入 V1.1 实测 | `audit-flags.csv` + mvp-release-plan §风险 |
| 02 角色权限矩阵不全 | 已建**临时**矩阵，未确认项标 `PROVISIONAL` | `architecture/permission-matrix.md` |
| 03 Rx 表单字段缺失 | 数据字典只登记已确认字段，其余 `UNKNOWN` | `architecture/data-dictionary.md` |
| 04 500+ 部件库不可复用 | 自建许可清晰目录，首批由医生审查 | backlog EPIC-03 任务 |
| 05 模板并发行为 | 并发冲突纳入状态机与验收用例 | `state-machines.md` + EPIC-03 |
| 06 签署/审批法律流程 | 审批状态机 + 审计签名归属，法律审查待定 | `state-machines.md` + SAFE-001 |
| 07 Lab 等级差异化工作流 | 工作流配置化，不硬编码节点 | `state-machines.md` §Lab |
| 08 返工/维修/Refinement | 建模为关联原件的子单，不改写历史 | `domain-model.md` + LAB-017 |
| 09 数据迁移渠道 | SRC28 §5 已核验；导出任務列入 MVP 后段 | SAFE-009 任务 + `security-baseline.md` |
| 10 STL 输入差异 | 样本集 30–50 份列入 PoC 验收 | `poc/stl-processing-poc-plan.md` |
| 11 ABR 误差/样本 | 独立高风险研发线，不进 MVP | PoC §AI 风险 + EPIC-08 |
| 12 自动底座/Blockout 公差 | PoC 门槛 + 实物对照 | PoC 计划 |
| 13 PTS 机器协议 | P3 推迟，需厂商授权样本 | EPIC-08 PTS 任务 |
| 14 厂商 API 授权 | MVP 仅手动导入；适配器先行 | EPIC-11 + ADR |
| 15 VisualDLP↔Rx 同步 | 独立 MES 域，映射规则 UNKNOWN | `domain-model.md` §MES |
| 16 排程/计价细则 | 模型留扩展位，规则 PROVISIONAL | `data-dictionary.md` |
| 17 财税合规 | FIN 整体 P2，会计负责人定义模型 | mvp-release-plan |
| 18 隐私辖区 | 部署基线 + 威胁建模，法审待做 | `security-baseline.md` |
| 19 教程过期风险 | 证据须记录修订日期，AGENTS.md 强制 | `AGENTS.md` |
| 20 许可/clean-room | ADR-0007 给比较建议，不宣告可安全发布 | `adr/0007-license-strategy.md` |

## 7. 追踪关系模型

```
Feature ID (research CSV/JSON，永不修改)
   │  source_ids → SRCxx（公开）/ SCR（私有，不入公开仓库）
   │  evidence   → D1 / D2 / S / T
   ▼
audit-flags.csv        → NEEDS_VERIFICATION / OVERLAP / PROPOSED
   ▼
Spec docs              → domain-model / data-dictionary / state-machines / permission-matrix
   ▼
tasks.json + tasks/*.md → Task ID 关联 1..n Feature ID；含验收与测试场景
   ▼
feature-traceability.csv → feature_id ↔ task_id ↔ epic_id（CI 校验 167 全覆盖）
   ▼
E2E 用例（Stage B 起）→ 引用 Task ID 与 Feature ID
```

规则：Feature 无对应任务或 UNKNOWN 说明时视为追踪断点，CI FAIL。

## 8. 本审计不能确认的事项

- 未逐篇重读 36 个来源正文来复核全部 118 项 D1 描述（抽验 3 篇）。
- 未核实 EasyRx 现行 UI/字段/状态与官方文档版本的一致性。
- SCR 截图内容不可复核，亦不可公开。
- KB 页面 HTTP 200 ≠ 文章存在且为主题所声称者（已对最短 slug SRC26 单独验明）。
- 167 项是研究拆分口径，非 EasyRx 功能全集。

## 9. 审计结论

**PASS（附条件）**：基线数据可信、可追踪，条件为：① 全部 NEEDS_VERIFICATION / OVERLAP / PROPOSED 标记在开发中保持可见；② `validate_baseline.py` 纳入 CI 并在每次改动后通过；③ 后续实测证据必须回写到对应 Feature ID 的备注而非新建平行清单。
