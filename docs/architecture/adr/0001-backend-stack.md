# ADR-0001 后端栈：FastAPI（模块化单体）

- **状态**：PROPOSED（Stage A；可在首个迭代复审）
- **日期**：2026-10-24

## 背景
报告 §10 给出 NestJS 或 FastAPI 二选一，由团队成熟栈决定。需要：强 OpenAPI 契约、后台任务、PG 生态、与 Python 几何 worker 的同语言调试便利。

## 决策
**FastAPI + SQLAlchemy 2.x + Pydantic v2，单进程模块化单体**；模块边界 = Python 包 + 服务接口，禁用跨模块 ORM 写。

## 替代方案
| 方案 | 弃用/保留原因 |
|---|---|
| NestJS + TypeORM | 与前端同语言是优点；但几何/AI worker 仍是 Python，双语言增加心智成本 → 次选 |
| Django + DRF | 全家桶适合 CRUD，但 async/任务流与精细 OpenAPI 较弱 |
| 微服务（任意栈） | 阶段不符，分布式事务成本 > 收益 |

## 后果
+ 单语言贯穿 worker；pydantic schema 驱动 OpenAPI；async IO 友好。
− 类型约束弱于 TS 全栈一致；需自律维持模块边界（arch-test 检查导入）。
- 复审触发：团队主力为 TS 时切换 NestJS 成本评估。

## 备注
WS 实时通知、报表导出等长任务一律走队列，不在请求内完成。
