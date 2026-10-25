# MVP 任务范围（任务级视图）

> 与 `docs/planning/mvp-release-plan.md` 配套：后者解释**为什么**是这些，本文列出任务级事实。
> `DEFERRED_IN_TASK` = 任务内被推迟的 Feature（研究阶段 > MVP）。
> Feature 级唯一处置结论见 `feature-disposition.csv`（本目录，机器可校验）。

MVP 任务数：**24/51**；覆盖 Feature（含被推迟部分）：**83**。

## Feature 级处置统计（167 项，口径统一）

| 处置 | 数量 | 含义 |
|---|---:|---|
| CORE | 56 | MVP 内按验收口径实现 |
| SIMPLIFY | 11 | MVP 内简化交付（削减点见 CSV detail） |
| MANUAL | 2 | MVP 内以人工操作替代 |
| DEFER | 3 | 研究-MVP 项移出首个闭环（落点见 CSV） |
| NOT_IN_MVP | 95 | 研究阶段 P1/P2/P3，本就不属 MVP 候选 |

对账：研究-MVP 72 = CORE+SIMPLIFY+MANUAL+DEFER；NOT_IN_MVP = 95（48+39+8）。
旧口径 55 核心/5 延期/3 手工 把 KEEP-SEC 混入 CORE、把两个部分交付项算作延期、
并把两个 P1 期手工项计入——本表已统一为 Feature 级唯一主处置。

| Task | 标题 | Epic | Feature | 其中 >MVP 的 Feature |
|---|---|---|---|---|
| TASK-0001 | 租户/机构/地点数据模型与行级隔离 | EPIC-01 | 3 | — |
| TASK-0002 | 登录认证、RBAC、2FA 与账号安全设置 | EPIC-01 | 5 | — |
| TASK-0003 | 医生与临床员工名册（非登录实体） | EPIC-01 | 3 | — |
| TASK-0004 | 诊所↔实验室连接握手 | EPIC-01 | 1 | — |
| TASK-0005 | 患者注册与去重辅助 | EPIC-02 | 4 | — |
| TASK-0006 | 治疗病例（Case）与患者处方历史 | EPIC-02 | 2 | — |
| TASK-0007 | 患者生命周期与直接扫描附件 | EPIC-02 | 2 | — |
| TASK-0008 | Rx 骨架：创建/草稿/编号/并发版本 | EPIC-03 | 4 | — |
| TASK-0009 | 部件/器械目录与牙弓画布 | EPIC-03 | 6 | RX-005, RX-016 |
| TASK-0010 | 处方模板：保存/调用/来源/分享权限 | EPIC-03 | 4 | RX-012 |
| TASK-0012 | 处方附件、Checkout/Submit 与 PDF 导出 | EPIC-03 | 3 | — |
| TASK-0015 | Rx 状态机核心：提交→接单→完成 + 撤回/版本/审批事件 | EPIC-04 | 8 | FLOW-007 |
| TASK-0016 | 履约状态：出货/收货/交付 | EPIC-04 | 2 | — |
| TASK-0017 | 工作台仪表盘：视图/计数/筛选/标签/到期预警 | EPIC-04 | 6 | FLOW-004, COM-009 |
| TASK-0019 | Rx 评论、站内消息中心与通知偏好 | EPIC-05 | 4 | COM-005, COM-008 |
| TASK-0020 | 临床通知与结构化审批（含附件级） | EPIC-05 | 4 | COM-003, COM-006 |
| TASK-0013 | 文件管线：上传/哈希去重/不可变版本/隔离扫描/通用扫描仪导入 | EPIC-06 | 8 | — |
| TASK-0014 | 3D 资产访问：浏览器预览、Optimize、打印列表、跨上下文引用 | EPIC-06 | 4 | ASSET-004, ASSET-006 |
| TASK-0033 | 实验室接单：Check-in/书面录入/审核问题 | EPIC-09 | 3 | LAB-003 |
| TASK-0047 | 公开 OpenAPI 与 Webhook（HMAC） | EPIC-11 | 1 | — |
| TASK-0048 | 全局审计日志与电子签名归属 | EPIC-12 | 1 | — |
| TASK-0049 | 加密、备份与恢复演练 | EPIC-12 | 2 | — |
| TASK-0050 | 合成测试数据与数据导出/迁移工具 | EPIC-12 | 2 | — |
| TASK-0051 | 合规部署基线与上线 Gate | EPIC-12 | 1 | — |

## 不在 MVP 任务中的高价值项

P1+ 任务整体不在 MVP：3D 编辑链（EPIC-07）、MES 深化（部分 EPIC-09）、财务（EPIC-10）、
厂商集成（EPIC-11 大部，除 TASK-0047 公开 API）与 AI 线（EPIC-08）。详见 mvp-release-plan。
