# ADR-0004 存储与不可变性：PostgreSQL + S3 hash 寻址

- **状态**：ACCEPTED
- **日期**：2026-10-24

## 背景
业务数据（关系强、需事务）与大文件（STL/PDF/图）读写画像完全不同；原件不可覆盖是硬要求（ASSET-009、主报告 §4.2）。

## 决策
- PostgreSQL 16 存全部业务/审计/事件数据。
- S3 兼容对象存储（生产 S3 或自托管 MinIO）存文件；key = `sha256` 内容寻址；DB `file_asset` 只存元数据+引用计数。
- 版本化 = 新 asset + `parent_asset_id`；删除 = 软删 reference + 生命周期策略清理无引用对象（保留期由 retention_policy 控）。
- 秘钥/凭据仅存 secret store 引用，DB 不落明文。

## 替代方案
| 方案 | 原因 |
|---|---|
| 文件存 DB large object | 备份膨胀、流式下载弱 → 否 |
| NAS/文件系统 | 自托管简，但缺版本/生命周期/签名 URL → 仅开发环境 |
| IPFS/内容寻址网络 | 运维与隐私不必要复杂度 → 否 |

## 后果
+ 去重天然（同 hash 秒传）、审计友好、对象级生命周期。
− 需要垃圾回收任务处理孤儿对象；MinIO 需纳入备份。
- 匿名命名（不编码患者信息）；MIME/扩展名校验在入库前完成。

## 备注
下载一律 `access_grant` + 预签名 URL（SAFE-004），禁止公开 bucket。
