# ADR-0003 几何计算栈：独立 Python worker，库选型由 PoC 裁决

- **状态**：PROPOSED（引擎绑定推迟到 PoC 报告）
- **日期**：2026-10-24

## 背景
EDIT/AI 域需要网格校验、裁剪、偏置加底座、布尔刻字等。主报告候选：Trimesh / Open3D / VTK。**禁止在 PoC 前宣称任何库精度等价于 EasyRx**。

## 决策
Worker 独立服务（容器化，CPU 优先，GPU 可选），Python 3.12+；对外契约 = job payload（输入 asset、recipe 参数快照、输出要求）+ 结构化 QA 报告；内部引擎可插拔 `EngineAdapter` 接口，首期实现 `trimesh` 参考实现。

## 替代方案
| 方案 | 原因 |
|---|---|
| Open3D | 点云/注册强；布尔与网格手术一般 → 候选参与 PoC |
| VTK | 能力最全、最重；若 trimesh 组合在裁剪/偏置不达标再升 |
| manifold3d / CGAL 绑定 | 布尔稳健性候选，许可与打包复杂度待评估 |
| 前端 WASM 全做 | 大模型内存与权限风险，仅作预览/交互辅助 |

## 后果
+ 资源画像独立扩缩；引擎可替换不影响 API。
− 需要样本集才能最终定型（30–50 份脱敏 STL，G3D-03）。
- 每次产出记录 `engine+version` 进 provenance（SAFE-007）。

## 备注
AI worker（ABR/Blockout/PTS）同构部署，feature flag 默认关；无已验证数据前不进生产链。
