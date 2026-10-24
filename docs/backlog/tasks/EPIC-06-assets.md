# EPIC-06 数字资产管线

> 域：Digital Asset Management · 任务数：2 · 覆盖 Feature：12
> 上传、哈希去重、不可变版本、隔离扫描、限时授权、3D 预览。
> 本文件由 `tools/gen_backlog.py` 生成，勿手改。

## TASK-0013 文件管线：上传/哈希去重/不可变版本/隔离扫描/通用扫描仪导入

| 字段 | 值 |
|---|---|
| Epic | EPIC-06 |
| 优先级 | MVP |
| 前置依赖 | TASK-0001 |
| 证据等级（覆盖项） | D1/T |
| 关联来源 | SRC02, SRC05, SRC04, SRC28, SRC08 |

### 功能说明
声明式上传+分块续传、sha256 去重、parent 版本链、AV/恶意网格隔离、限时下载授权、通用 STL 导入通道。

### 业务目标
原件永不覆盖、重复文件秒传、断网可续、未过扫描不可引用。

### 覆盖 Feature
| Feature ID | 名称 | 证据 | 阶段 | 复杂度 | 研究验收口径 |
|---|---|---|---|---|---|
| ASSET-001 | STL手动上传及上下颌分类 | D1 | MVP | 中 | 上下颌文件分别关联Rx |
| ASSET-002 | 原始与优化版本区分 | D1 | MVP | 中 | 原件只读另生成派生版本 |
| ASSET-008 | 文件哈希与内容去重 | T | MVP | 中 | 重复上传识别并保留业务引用 |
| ASSET-009 | 文件版本链和不可变原件 | T | MVP | 中 | 每个派生版本能定位源和任务 |
| ASSET-010 | 防病毒/恶意网格隔离及配额 | T | MVP | 中 | 恶意或超限文件被隔离不影响系统 |
| SAFE-004 | 最小权限临时下载链接 | T | MVP | 中 | 过期链接和撤权后访问失败 |
| SAFE-005 | 恶意文件扫描与上传限制 | T | MVP | 中 | 恶意网格不能造成服务崩溃 |
| INT-005 | 其它扫描仪STL导入 | D1 | MVP | 低 | 标准STL无依赖可上传处理 |

### 输入输出
输入：文件声明（size/sha256/kind/jaw）。输出：file_asset+file_reference+access_grant。

### 业务规则
- key=sha256 内容寻址；同 hash 直接复用资产（ASSET-008）。
- parent_asset_id 版本链；原件 parent=null 不可变（ASSET-002/009）。
- scan_status=clean 才允许建立 reference（ASSET-010/SAFE-005）。
- 下载仅 access_grant+预签名（SAFE-004），30 天后撤权场景见 E2E-14。
- 通用扫描仪 STL 走同一管线（INT-005，不建旁路）。

### 权限要求
上传者需患者/Rx 权限；下载需有效 reference/grant。

### 异常处理
- hash 与 size 不符 → 拒收
- 感染/失败 → 隔离+审计
- 中断续传不产半文件（E2E-12）

### 验收标准
- E2E-08/12/14 通过
- 原件不可变可由哈希证明
- 隔离文件不可下载

### 测试场景
- 去重秒传
- 断点续传
- 版本链完整性
- 扫描门控
- E2E-14

### 尚未解决的问题
- STL 之外允许的文件类型全集
- 配额默认值

---

## TASK-0014 3D 资产访问：浏览器预览、Optimize、打印列表、跨上下文引用

| 字段 | 值 |
|---|---|
| Epic | EPIC-06 |
| 优先级 | MVP |
| 前置依赖 | TASK-0013 |
| 证据等级（覆盖项） | D1 |
| 关联来源 | SRC06, SRC02, SRC05, SRC04 |

### 功能说明
Three.js 浏览器预览、STL Optimize/Scrubber、打印列表、患者与 Rx 双入口访问同一模型。

### 业务目标
大 STL 可流畅预览；同一资产多上下文可见而权限不扩散。

### 覆盖 Feature
| Feature ID | 名称 | 证据 | 阶段 | 复杂度 | 研究验收口径 |
|---|---|---|---|---|---|
| ASSET-003 | 3D Viewer浏览器预览 | D1 | MVP | 中 | 可旋转缩放双视图不改变源文件 |
| ASSET-004 | STL Optimize/Scrubber | D1 | P1 | 高 | 处理前后拓扑报告及文件可回退 |
| ASSET-005 | 从Rx和患者记录访问同一模型 | D1 | MVP | 中 | 同一对象多路径访问且记录版本 |
| ASSET-006 | STL Print List | D1 | P1 | 中 | 按状态筛选可打印模型 |

### 输入输出
输入：asset 访问请求。输出：渲染流/视图、optimized 派生资产、print list 条目。

### 业务规则
- 预览用 LOD/分块；超大文件降级提示（性能基准 PoC 回写）。
- Optimize 产新 asset（parent 链），不覆盖原件（ASSET-004）。
- 同一 asset 经多条 file_reference 暴露（ASSET-005）；撤权按 reference。
- print list 组织待打 STL（ASSET-006）。

### 权限要求
有任一有效 reference 即可预览元数据；下载仍需 grant。

### 异常处理
- 损坏 STL 预览 → 明确错误而非空白
- LOD 失败降级原样

### 验收标准
- 50MB 级 STL 可交互（阈值 PoC 定）
- 双入口访问一致
- optimized 版本链正确

### 测试场景
- 预览加载基准
- 双入口权限
- 优化派生链

### 尚未解决的问题
- Optimize 官方行为（抽稀/修复?）
- Print list 与生产衔接
