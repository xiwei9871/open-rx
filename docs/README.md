# docs/ — 文档索引

## 审计
- [research-baseline-audit.md](audit/research-baseline-audit.md) — V1.0 研究资产审计：结构校验、来源核验、重叠登记、GAP 处置
- [audit-flags.csv](audit/audit-flags.csv) — NEEDS_VERIFICATION / OVERLAP / PROPOSED 标记（82 条）
- [research-sha256.txt](audit/research-sha256.txt) — research/ 基线哈希钉

## 架构
- [domain-model.md](architecture/domain-model.md) — 12 域实体与关系
- [data-dictionary.md](architecture/data-dictionary.md) — 字段/约束/索引 + UNKNOWN 登记
- [permission-matrix.md](architecture/permission-matrix.md) — 角色×能力（PROVISIONAL）
- [state-machines.md](architecture/state-machines.md) — Rx / 加工 / 生产三套状态机
- [erd.mmd](architecture/erd.mmd) — ER 图（mermaid）
- [system-design.md](architecture/system-design.md) — 模块化单体+worker 设计
- [deployment.md](architecture/deployment.md) — 拓扑/环境/备份/上线清单
- [security-baseline.md](architecture/security-baseline.md) — 威胁模型与工程控制
- [authz-test-matrix.md](architecture/authz-test-matrix.md) — 跨机构授权/越权/枚举测试矩阵（A3）
- [research/v1.1-verification-checklist.md](research/v1.1-verification-checklist.md) — V1.1 风险排序核验任务（A6）
- [adr/](architecture/adr/) — 0001~0007 架构决策记录

## API
- [openapi.yaml](api/openapi.yaml) — OpenAPI 3.1 契约草案（redocly lint 通过）

## Backlog（生成物，源在 tools/backlog_tasks.py）
- [epics.md](backlog/epics.md) — 12 Epic 总览
- [tasks/](backlog/tasks/) — 51 个任务规格（每 Epic 一文件）
- [tasks.json](backlog/tasks.json) — 机器可读任务
- [feature-traceability.csv](backlog/feature-traceability.csv) — 167 Feature ↔ Task 映射
- [dependency-graph.mmd](backlog/dependency-graph.mmd) — 任务依赖图
- [mvp-scope.md](backlog/mvp-scope.md) — MVP 任务级视图

## 规划
- [mvp-release-plan.md](planning/mvp-release-plan.md) — 72 项 MVP 再审结论与切片

## PoC
- [stl-processing-poc-plan.md](poc/stl-processing-poc-plan.md) — STL 加工链技术方案与验收
