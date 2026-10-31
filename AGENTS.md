# AGENTS.md — 本仓库的人与 AI 协作契约

任何在本仓库工作的开发者或 AI Agent（Devin/Codex/其他）必须遵守以下规则。违反视为任务未完成。

## 1. 追踪是硬约束

- **Feature ID**（`IAM/PAT/RX/FLOW/COM/ASSET/EDIT/AI/LAB/FIN/INT/SAFE-NNN`，见 `research/easyrx_feature_inventory_v1.csv`）是唯一追踪键。
- 每个 PR/Issue/任务必须引用其覆盖的 Feature ID；代码中实现某规则处注释引用对应 ID。
- `docs/backlog/tasks.json` + `tasks/*.md` 由 `tools/gen_backlog.py` 生成：**改 `tools/backlog_tasks.py`，不要改生成物**。
- 每次提交前必须全绿：
  ```bash
  python3 tools/validate_baseline.py && python3 tools/gen_backlog.py --check
  ```

## 2. 证据纪律

- 证据等级：`D1` 官方正文 / `D2` 目录提纲 / `S` 私有截图 / `T` 新系统建议。**永远不得把 T 写成"EasyRx 已有功能"**。
- 未验证规则保持 `UNKNOWN`/`PROVISIONAL`/`NEEDS_VERIFICATION` 标记（`docs/audit/audit-flags.csv`）；验证后**回写到对应 Feature 条目**，不新建平行清单。
- 证据不足 ≠ 功能不存在。宁可标 OPEN 也不编造。
- 引用官方资料时记录访问日期；教程可能过期（GAP-19）。

## 3. 测试与验收

- 不允许"无测试标记完成"：每个 Task 的验收标准和测试场景（tasks/*.md）是 DoD 的一部分。
- 状态机、权限、幂等、文件版本链必须有自动化测试。
- E2E-01~16（见研究主报告 §9）是 MVP 出口的固定验收集。

## 4. AI 生成代码

- AI 生成/修改的代码必须经 `validate_baseline.py` + 项目测试 + 人工或自动化审查后才可合入。
- Agent 交付必须给出：分支名、commit hash、变更文件清单、运行的验证命令与结果。未见证据不得宣称完成。

## 5. 隐私与数据红线

- **零 PHI**：真实患者数据、可识别身份的截图、临床 STL、任何秘钥/凭据，一律不得提交。
- 测试/示例数据必须合成或脱敏且获授权（SAFE-008）；`SCR` 私有截图不进公开内容。
- 文件名与对象键匿名化；日志禁止 PHI。

## 6. 知识产权与 clean-room

- 不复制 EasyRx 的代码、专有素材、文档原文、500+ 部件库、模型权重；实现只依据公开需求级描述与自研设计。
- 新依赖优先 ≥7 天发布版本；许可证经审计后才可引入（ADR-0007 gate）。
- 项目命名不得暗示与 EasyRx 官方关联。

## 7. 工作流

- 分支：`devin/<scope>-<desc>` 或 `feat/<task-id>-<desc>`；任务分支推送后创建 PR 并附验收证据。
- 提交信息说明"为什么"；关联 Task/Feature ID。
- 研究报告类变更（`research/`）默认禁止——那是哈希固定的基线；更新走新版本文件而非原地修改。

## 8. 环境

- Python ≥3.11（脚本零三方依赖）；Node ≥20（仅文档 lint/工具链用）。
- 所有验证脚本必须 `python3 tools/…` 一条命令可跑，无需联网。

## 9. Project Continuity (Devin V1.0.1)
- 会话开始先读 `docs/agent_governance/{PROJECT_STATE.yaml,DECISIONS.md,HANDOFF.md}`，仓库文件优先于聊天记忆。
- 状态声明前跑 `python3 tools/gov/orx_gates.py all`；未验证一律 NOT_VERIFIED。
