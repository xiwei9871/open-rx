# Stage B0 验收报告 — 工程地基实现

> 结论：**见文末判定**。本报告只记录实测证据；未实测项不声称完成。
> 数据纪律：全部用户/机构/数据均为合成（synthetic），无 PHI、无真实 STL、无凭据入库。

## 1. 基线与分支

| 项 | 值 |
|---|---|
| 基线 commit | `9ba5f2ce47a5bce0fea4928cf5fca7f757920c87`（Stage A.1 已核验 HEAD） |
| B0 分支 | `devin/easyrs-stage-b0`（`git switch -c … 9ba5f2ce`） |
| `main` 是否被覆盖 | 否 — Stage A.1 PR 状态经 API 实测为 `NO PR EXISTS`，未合并；按要求不动 main |
| 共同祖先 | `0618b0f`（B0 分支与 main 有共同祖先，PR diff 正常） |

## 2. B0-01 文档纠偏（已核验）

| 修正项 | 证据 |
|---|---|
| 授权矩阵 36→22 用例 | `docs/audit/stage-a1-correction-report.md` 记 "22 条用例（AZ-01~36，编号非连续）" |
| V1.1 风险分布 | `…correction-report.md` + `v1.1-verification-checklist.md` 实测：🔴5（V-01/02/03/04/14）🟡6（V-05/06/07/08/09/13）🟢3（V-10/11/12）|
| `AUTO-001` 无效 ID | 全仓 grep 零命中，已清除 |
| downloaded/printed 顺序 | `state-machines.md` §4 标注 `? UNKNOWN`，§9 明确"不实施强制迁移" |

## 3. 已实现范围（对照任务清单）

- **B0-02 工程骨架**：`apps/api` FastAPI 模块化单体（`modules/iam|auth|audit`）；`apps/web` React 18 + TS + Vite；`infra/docker-compose.yml` postgres 16 + redis 7 + S3 兼容对象存储 + api + web；`.env.example`；Alembic 迁移；pytest + httpx；CI 三 job。
- **B0-03 机构/租户**：`tenant`、`organization`（practice|lab）、`location`、`user_account`、`membership`（role 枚举）、`org_connection`（pending→accepted/rejected/revoked 状态机 + 幂等键）。跨租户默认拒绝 → PostgreSQL **RLS**（`app.tenant_id` GUC，`SET LOCAL` 事务级）+ API 层双重隔离。
- **B0-04 身份/权限**：用户创建（invite）、登录、argon2id 哈希、不透明 cookie 会话（仅存 sha256）、RBAC（`ROLE_PERMISSIONS` 仅平台级，临床能力留白待 V-03）、审计（`audit_event` 追加写、deny 也审计）、TOTP 2FA（setup→enable→verify 挑战流）。
- **B0-05 质量**：25 项 pytest，全部真实库断言，无 mock。

## 4. 测试证据（实测输出）

```text
$ cd apps/api && python -m pytest -q        # Postgres 容器 @55432，ENV=test
25 passed in 5.46s
```

| 文件 | 覆盖 |
|---|---|
| `test_migrations.py` (4) | alembic head、表存在、**RLS enabled 断言**、audit append-only 策略 |
| `test_auth.py` (7) | healthz、登录+me、错误密码+审计、401、登出吊销、改密、**TOTP 2FA 全流程** |
| `test_isolation.py` (5) | **跨租户 API 层拒绝**、**跨租户 RLS 层拒绝（direct SQL）**、同租户跨机构拒绝、连接请求幂等、接收侧 accept |
| `test_rbac_audit.py` (6) | staff 无权管机构、admin 机构生命周期、member:write 门、lab_technician 最小权限、审计内容断言、audit:read 门 |
| `test_contract.py` (3) | 已实现 op ⊆ spec∪白名单、必需 op 齐全、无错名漂移 |

## 5. 运行时实测证据（容器全栈）

```text
$ docker compose -f infra/docker-compose.yml up -d
easyrs-dev-postgres-1 Up (healthy)   easyrs-dev-redis-1 Up (healthy)
easyrs-dev-minio-1    Up             easyrs-dev-api-1    Up
easyrs-dev-web-1      Up
api 启动日志: alembic upgrade head → seed ok → Uvicorn running on :8000
```

```text
GET  http://localhost:5173/                     → 200 text/html (nginx 托管 SPA)
POST http://localhost:5173/api/v1/auth/login    → 200 {"requires_2fa":false,…}
GET  http://localhost:5173/api/v1/auth/me       → 200 {role:"practice_admin",
      permissions:["audit:read","connection:write","location:write",
                   "member:write","org:manage","roster:write"],…}
GET  http://localhost:5173/api/v1/orgs          → 200 {items:[3 orgs]}
GET  http://localhost:8000/healthz              → 200 {"status":"ok"}
```

前端→后端连通**双路径实测**：(a) 容器内 nginx `proxy_pass http://api:8000`；
(b) 开发模式 vite `/api` 代理 → uvicorn。均返回真实库数据。

## 6. CI（`.github/workflows/validate.yml`）

| job | 内容 |
|---|---|
| `validate` | 基线校验、backlog 漂移、redocly@1.25.15 lint+bundle、`validate_contract.py`、秘钥/PHI 文件扫描 |
| `api-tests` | postgres:16 service → 建 `easyrs_app` 最小权限角色 → pytest 25 项（与本地同） |
| `web-build` | `npm ci` + `tsc --noEmit` + `vite build` |

远端 CI 结果：见提交说明（推送后由 GitHub Actions 记录，本报告提交时如实更新/附 run 状态）。

## 7. 关键设计决定（审计留痕）

1. **RLS + GUC 模型**：`SET LOCAL app.tenant_id` 每事务生效；`deps.tenant_commit()` 提交后重设。教训：连接级 `SET` 在 NullPool 下随连接销毁丢失，事务级才是正确语义。
2. **登录的 RLS 悖论**：membership 受 RLS 但租户身份由 membership 发现 → 登录时经 `admin_engine` 做窄边界读取，`auth_session.tenant_id` 缓存租户供后续请求 pin GUC。
3. **审计插入 RLS**：`audit_event` INSERT 策略 `check(true)`；但 `INSERT…RETURNING` 会触发 SELECT 策略 → 模型用 Python 侧默认 `id/ts`，避免隐式 RETURNING。
4. **403 同构**：存在与否返回同构 403（防 ID 枚举），deny 落审计 `access_denied`。
5. **权限表 PROVISIONAL**：只含平台级能力；临床能力一律待 V-03 验证，未静默固化。

## 8. 未解决问题 / 偏离登记

- **MinIO→RustFS**：`minio/minio` 镜像在本环境所有可达 registry 均 403/timeout；替换为 `rustfs/rustfs:latest`（S3 API 兼容，boto3 连通，仅用于 bucket 预检）。功能等价但非任务书点名组件。
- **会话单机构**：`active_org_id` 固定为首个 active membership；多机构切换未实现（S1+）。
- **org 目录可见性**：`GET /v1/orgs` 列出租户内全部机构（机构名不属 PHI）；对象级资源仍按 membership+connection 门控。标记 PROVISIONAL。
- **无 refresh token / 无速率限制 / 无 CSRF token**（SameSite=Lax + X-Requested-With 检查兜底）；B0 明确非生产配置。
- **postgres 端口偏移**：宿主机 5432 被本机 Postgres/SSH 隧道占用 → 映射 55432；CI 内部用 5432 不受影响。
- **S3 仅 bucket 预检**：无对象上传路径（属于 S1+ 资产域）。
- 2FA challenge 存内存/DB 表二选一当前为 DB `auth_challenge`（重启不丢）——未做滑动窗口限流。

## 9. 判定

**PASS（条件性）** — B0 全部验收项实测通过：迁移、认证、RBAC、租户×机构双层隔离、审计、Docker 重建启动、前后端真实 HTTP 连通、契约一致性。唯一非等价替换为 S3 实现（RustFS 代 MinIO），已登记。未开始 S1。
