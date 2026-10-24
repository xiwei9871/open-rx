# MVP 发布计划 V1.0 — 72 项 MVP 候选的再审结论

> **MVP 闭环定义**：患者建档 → 创建 Rx → 上传 STL → 实验室接单 → 生产跟踪 → 质检 → 交付。
> 配套：`docs/backlog/mvp-scope.md`（任务级事实，自动生成）。
> **再审结论**：72 项研究-MVP 中，**55 项保留 CORE/KEEP**，**11 项降级（DEFER/SIMPLIFY）**，其余以**手工替代或简化形态**交付。MVP 不含任何依赖厂商授权或未验证 AI 的功能。

## 1. 再审口径

| 处置 | 含义 |
|---|---|
| CORE | 闭环必需，按现有验收口径实现 |
| KEEP-SEC | 安全/审计类——**必须第一版内建**，不可后补 |
| SIMPLIFY | 功能保留但首期用简化形态（明确简化点） |
| DEFER | 移出首个可发布闭环，给出落点 |
| MANUAL | 用人工操作替代自动化，标注替代方式 |

## 2. 逐项处置（72）

### IAM（12）

| Feature | 处置 | 理由 |
|---|---|---|
| IAM-001 机构信息配置 | CORE | 一切的地基 |
| IAM-002 多地点 | CORE | 收货地址依赖，实现成本低 |
| IAM-003 医生列表/默认 | CORE | Rx 必填归属 |
| IAM-004 员工名册 | CORE | 采样/提交人归属 |
| IAM-005 员工必填开关 | **DEFER→P1** | 便利性；MVP 固定"医生必填"即可 |
| IAM-006 员工登录 | CORE | 协作前提 |
| IAM-007 诊所↔实验室连接 | CORE | E2E-04 关键路径 |
| IAM-008 实验室模板分享授权 | **DEFER→P1** | 与 RX-012 同包落地；MVP 仅诊所自建模板 |
| IAM-009 密码管理 | CORE | 安全底线 |
| IAM-010 时区 | **SIMPLIFY** | MVP 存机构级时区用于显示/排程；不做用户级切换 |
| IAM-011 最小权限矩阵 | KEEP-SEC | T 级自建，不可后补 |
| IAM-012 2FA+访问审计 | KEEP-SEC | 高危操作门槛 |

### PAT（8）

| Feature | 处置 | 理由 |
|---|---|---|
| PAT-001/002 建档+联想 | CORE | 闭环起点 |
| PAT-003 外部编号 | CORE | 迁移与集成的基础键 |
| PAT-004 生日识别同名 | CORE | 仅展示辅助，成本低 |
| PAT-005 处方历史 | CORE | 临床查询刚需 |
| PAT-006 患者直接附件 | **SIMPLIFY** | 复用资产管线；MVP 入口可从 Rx 侧为主，患者侧留接口 |
| PAT-008 病例实体 | CORE | Rx 分组语义（T） |
| PAT-009 软删除/保留 | KEEP-SEC | 事后补会造成数据债务 |

### RX（14）

| Feature | 处置 | 理由 |
|---|---|---|
| RX-001 创建入口 | CORE | |
| RX-002 医生/地点/实验室/日期 | CORE | E2E-01 |
| RX-003 唯一编号 | CORE | 计费/追溯键 |
| RX-004 草稿 | CORE | E2E-02 |
| RX-006 部件检索 | CORE + **目录 SIMPLIFY** | 自建首批审查目录（数十项），非 500+（GAP-04） |
| RX-007 器械库 | CORE + SIMPLIFY | 同上 |
| RX-008 牙弓画布拖放 | **SIMPLIFY** | MVP 用牙位勾选/标记图替代完整拖放画布；画布交互放 P1 |
| RX-009 部件选项 | CORE | |
| RX-010 模板保存/调用 | CORE | |
| RX-011 模板来源区分 | **DEFER→P1** | 依赖 IAM-008 分享 |
| RX-013 自由文字 | CORE | |
| RX-019 附件上传 | CORE | |
| RX-020 Checkout/Submit | CORE | E2E-07 幂等 |
| RX-021 PDF 导出 | CORE | E2E-11 |

### FLOW（13）

| Feature | 处置 | 理由 |
|---|---|---|
| FLOW-001 仪表盘+计数 | CORE | |
| FLOW-002 日期/状态筛选 | CORE | |
| FLOW-003 多维筛选 | **SIMPLIFY** | S 级证据；MVP 子集（状态/日期/lab） |
| FLOW-005 Saved/Submitted | CORE | |
| FLOW-006 Check-in | CORE | |
| FLOW-008 禁 Unsubmit | CORE | SRC24 |
| FLOW-009 Unsubmit→Saved | CORE | E2E-05 |
| FLOW-010 提交后追加文件 | CORE | SRC24 |
| FLOW-011 Complete | CORE | |
| FLOW-012 出货+追踪号 | CORE + **MANUAL** | 手工录入承运商/单号，不接承运商 API |
| FLOW-013 收货/交付 | CORE | E2E-10 |
| FLOW-014 Needed Soon | **SIMPLIFY** | due_date 排序+临近高亮；阈值固定默认值，可配放 P1 |
| FLOW-016 版本/审批事件 | KEEP-SEC | T 级，审计必需 |

### COM（4）

| Feature | 处置 | 理由 |
|---|---|---|
| COM-001 评论 | CORE | |
| COM-002 临床通知 | CORE | |
| COM-004 需审批通知 | CORE | E2E-09 闭环 |
| COM-007 消息中心 | CORE | |

### ASSET（7）

| Feature | 处置 | 理由 |
|---|---|---|
| ASSET-001 STL 上传+颌位 | CORE | |
| ASSET-002 原始/优化区分 | CORE | 版本链基础 |
| ASSET-003 浏览器预览 | CORE + **SIMPLIFY** | 基础 Three.js 预览；大网格 LOD 优化放 P1 |
| ASSET-005 跨上下文访问 | CORE | |
| ASSET-008 哈希去重 | KEEP-SEC | 事后补代价高 |
| ASSET-009 版本链不可变 | KEEP-SEC | 核心不变量 |
| ASSET-010 隔离+配额 | KEEP-SEC + SIMPLIFY | 类型/大小/网格 sanity 必做；AV 引擎为可插拔配置 |

### LAB（3）

| Feature | 处置 | 理由 |
|---|---|---|
| LAB-001 接单 Check-in | CORE | |
| LAB-002 审核问题/建议 | CORE | 经通知审批闭环 |
| LAB-019 物流签收 | CORE + MANUAL | 手工登记（无承运商 API） |

### INT（2）

| Feature | 处置 | 理由 |
|---|---|---|
| INT-005 通用扫描仪导入 | CORE | 复用资产管线；这是 MVP 唯一的"集成"——全部手动 |
| INT-011 OpenAPI/Webhook | **SIMPLIFY/DEFER** | 内部 v1 API 契约存在；对外 webhook 订阅移 P1（无第三方消费者） |

### SAFE（9）

| Feature | 处置 | 理由 |
|---|---|---|
| SAFE-001 审计+签署归属 | KEEP-SEC | |
| SAFE-002 租户隔离 | KEEP-SEC | |
| SAFE-003 加密 | KEEP-SEC | 部署配置 |
| SAFE-004 限时下载链接 | KEEP-SEC | 外发唯一路径 |
| SAFE-005 上传限制/扫描 | KEEP-SEC | |
| SAFE-006 备份+演练 | KEEP-SEC | E2E-16 |
| SAFE-008 合成数据 | KEEP-SEC | 零 PHI 红线 |
| SAFE-009 导出/迁移 | **DEFER→MVP 后首个迭代** | 重要性高但依赖 GAP-09（对方导出能力）；MVP 提供管理员 JSON+文件包导出雏形，完整迁移工具随后 |
| SAFE-010 合规部署基线 | KEEP-SEC | 上线 gate |

## 3. 处置汇总

| 类别 | 数量 | 明细 |
|---|---:|---|
| CORE（含简化标记） | 55 | 上表 CORE/SIMPLIFY/KEEP-SEC 合计 |
| DEFER（移出首个闭环） | 5 | IAM-005、IAM-008、RX-011、SAFE-009（部分）、INT-011（webhook 部分） |
| 手工替代 | 3 | FLOW-012/LAB-019 承运商、FLOW-015/LAB-016 交付日（本就 P1）、打印列表手工 |
| 依赖外部厂商 | **0** | MVP 不接任何厂商 API |
| 依赖未验证 AI | **0** | EPIC-08 全部不在 MVP |

## 4. 交付切片（Alpha 顺序）

| 切片 | 内容 | 出口标准 |
|---|---|---|
| S0 地基 | TASK-0001/0002/0048/0049：租户+认证+审计+加密备份骨架 | RLS 越权测试绿；审计追加可验 |
| S1 诊所侧 | TASK-0003/0004/0005/0006/0008/0009/0012(+0013 管线)：患者→Rx→附件→提交 | E2E-01/02/04/05/07/08/15 |
| S2 实验室侧 | TASK-0015/0033：check-in、状态机、问题通知（TASK-0019/0020 核心） | E2E-06/09 |
| S3 履约收尾 | TASK-0016/0017：出货/收货/交付+基础仪表盘；PDF（TASK-0012 尾） | E2E-03/10/11/14 |
| S4 硬化门 | TASK-0050/0051：合成数据、备份演练、上线检查 | E2E-12/13/16 + 安全 gate |

（TASK-0007/0010/0014 在对应切片内完成 MVP 部分；其 DEFERRED 特性随 P1 批次。）

## 5. MVP 出口标准

- E2E-01 ~ E2E-16 全部通过（合成数据）。
- `validate_baseline.py` 全绿；API 契约漂移 = CI 拒绝。
- 审计、隔离、备份演练有证据记录。
- 所有 `? UNKNOWN/PROVISIONAL` 规则在代码/文档中仍带标记——**不允许借 MVP 上线把未验证规则静默固化**。

## 6. 明确不做（MVP 边界）

- 任何厂商实时 API（iTero/TRIOS/PMS/打印/支付）——手动导入兜底。
- 3D 人工编辑器与自动/AI 加工（EPIC-07/08 全推迟到 PoC 之后）。
- Aligner/IDB 专用表单深度、手绘标注、财务模块、生产排程细化。
- 完整迁移导入器（等 SAFE-009 后续迭代 + GAP-09 证据）。
