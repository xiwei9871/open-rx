# EasyRS — 开源正畸处方与技工室生产协同平台

> 独立开发、可自托管的 EasyRx 替代系统。**当前阶段：Stage A — 工程基线与需求冻结**。仓库内尚无可运行应用代码。

## 这是什么

基于对 EasyRx Practice / Lab / 3D / VisualDLP 公开资料的独立研究，重建一个覆盖 **诊所处方 → 实验室生产 → 3D 加工 → 交付** 闭环的开源系统。

- 目标用户：正畸诊所、技工室（lab）、开发者/自托管部署者
- 架构：模块化单体业务后端 + 独立 3D 几何计算 worker（见 `docs/architecture/system-design.md`）
- 技术方向（ADR 拟议，未最终锁定）：React+TS+Three.js / FastAPI / PostgreSQL / Redis / S3(MinIO) / Docker

## 仓库结构

```
research/          V1.0 研究基线（167 项功能清单 + 来源索引，哈希固定，勿改）
docs/
  audit/           研究审计报告 + 标记（NEEDS_VERIFICATION/OVERLAP/PROPOSED）
  architecture/    领域模型、数据字典、权限矩阵、状态机、系统设计、ADR、部署、安全
  api/             OpenAPI 3.1 契约草案
  backlog/         12 Epic / 51 Task / 167 Feature 全量追踪（生成产物）
  planning/        MVP 发布计划（72 项再审）
  poc/             STL 加工 PoC 技术方案
tools/             验证与生成脚本（全部 stdlib）
```

## 快速验证

```bash
python3 tools/validate_baseline.py   # 基线+追踪一致性（CI gate）
python3 tools/gen_backlog.py --check # 生成物与源数据漂移检查
npx @redocly/cli lint docs/api/openapi.yaml  # API 契约 lint
```

## 本地运行（Stage B0 工程地基）

```bash
cp .env.example .env                  # 开发默认值，无真实密钥
docker compose -f infra/docker-compose.yml up -d --build
# web: http://localhost:5173  (nginx → /api/* 反代到 api:8000)
# api: http://localhost:8000  (启动时自动 alembic upgrade + 合成数据 seed)
```

合成登录：`admin@pa.dev` / `Passw0rd!dev`（practice_admin），另有 `doctor@pa.dev`、
`staff@pa.dev`、`admin@la.dev`、`tech@la.dev` 同密码。仅合成数据，禁止真实患者信息。

本地后端开发（不经容器）：Python 3.11+，`cd apps/api && pip install -r requirements.txt
&& ENV=dev uvicorn app.main:app --port 8000`；测试 `python -m pytest -q`（需要 compose
的 postgres 在 55432）。前端开发：`cd apps/web && npm ci && npm run dev`（vite 把
`/api/*` 代理到 localhost:8000）。

## 关键数字（研究基线，非完成度）

167 功能项 · 12 模块 · 12 Epic · 51 Task · MVP 候选 72→再审保留 55 项核心 · 20 项未决差距登记在册

## 规则速览（详见 AGENTS.md / CONTRIBUTING.md）

- Feature ID（如 `RX-008`）是全仓库唯一追踪键；代码/测试/文档引用必须带 ID。
- `NEEDS_VERIFICATION / OVERLAP / PROPOSED` 标记在 `docs/audit/audit-flags.csv`；未验证规则不得静默固化。
- **零 PHI**：不得提交真实患者数据、可识别截图或临床 STL。
- clean-room：不复制 EasyRx 代码、素材、文档正文、模型权重。
- 开源许可证：**未决定**（ADR-0007 审查 gate 未过前，本仓库不授予复用权）。

## 状态门

- [x] 研究基线导入与审计
- [x] 领域模型/状态机/权限矩阵（含 PROVISIONAL 标记）
- [x] 12 Epic / 51 Task 可追踪 backlog
- [x] MVP 范围再审（真实闭环，零厂商依赖）
- [ ] V1.1 实测核验（GAP-* 关闭）
- [ ] STL PoC 引擎裁决（仅方案已就绪）
- [ ] 首个可运行迭代
