# ADR-0002 前端与 3D 查看器：React + TypeScript + Three.js

- **状态**：PROPOSED
- **日期**：2026-10-24

## 背景
需要单一代码库服务 Practice/Lab 两种工作台 + 浏览器 STL 预览（ASSET-003）与人工编辑交互（EDIT-*）。

## 决策
React 18 + TypeScript + Vite；Three.js（经 react-three-fiber 可选）承载 3D；react-query 式数据层；同一构建按 `realm=practice|lab` 路由与权限裁剪。

## 替代方案
| 方案 | 原因 |
|---|---|
| Vue/Svelte | 生态可，但 Three.js/企业表单招聘与资料面 React 占优 |
| Babylon.js | 功能强但 Three.js 社区/资料/招聘面更大；PoC 可复评 |
| 前后端同框架（Next.js） | 自托管部署与 API-first 契约下非必需；暂留选项 |

## 后果
+ 组件与 3D 生态成熟；realm 共享组件库。
− 大 STL 的 LOD/分块/Web Worker 解析需自研（PoC 基准见 docs/poc）。
- 编辑器交互（三点定位、trim 曲线）是项目最高前端风险 → PoC 先行。

## 备注
表单草稿必须本地持久化可恢复（E2E-02）；画布标注（RX-014）技术选型在实现任务内决定。
