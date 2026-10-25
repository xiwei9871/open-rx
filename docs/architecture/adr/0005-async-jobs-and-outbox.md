# ADR-0005 异步与事件：PG Outbox + Redis 队列（不引 Kafka）

- **状态**：ACCEPTED
- **日期**：2026-10-24

## 背景
状态迁移需可靠通知（通知、计数、webhook、job 触发）；要求幂等、重试、死信、可回放（主报告 §4.4）。

## 决策
- 领域事件先写业务同事务的 `outbox_event` 表 → relay 进程转发到 Redis 队列（arq/自研轻量）→ 消费者。
- 每事件含 `event_id`；消费者表 `processed_event(event_id PK)` 保证 exactly-once 语义（at-least-once 投递 + 幂等消费）。
- 重试指数退避；超限进 `dead_letter` + 告警；事件可回放（admin 工具）。

## 替代方案
| 方案 | 原因 |
|---|---|
| Kafka/RabbitMQ | 体量不符，运维成本高 → 事件量超阈值再议 |
| 仅同步调用 | 通知/加工不可靠，违背 §4.4 |
| 双写（DB+直接发队列） | 丢事件风险 → 否 |

## 后果
+ 事件与状态同 tx，不会"状态变了没通知"；可审计可回放。
− relay 是新组件需监控；消费者必须真正幂等（CI 提供测试辅助）。
- 外部 webhook 投递同样走该管道 + HMAC 签名（INT-011）。

## 备注
上传扫描、报表导出、PDF 生成、几何 job 全部同一管道，无第二套异步机制。
