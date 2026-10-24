# Stage B0.1 验收报告 — 安全边界与真实前后端闭环

> 基线：`devin/easyrs-stage-b0` @ `51f2b7c`（已审核）。分支：`devin/easyrs-stage-b01`。
> 全部测试实测，非文档声称；合成数据 only。

## 1. 已修复问题与证据

### P0-1 跨机构连接自批准漏洞 — 已修复

`transition_connection()` 原先允许连接任一方（含发起方）执行 accept。
现已实现方向感知授权（**EasyRS 自有安全设计决策，非 EasyRx 已证实规则 —— V-14 仍挂起**）：

| 动作 | 允许者 | 来源状态 |
|---|---|---|
| request / re-request | 连接任一方（记 `initiated_by_org_id`） | — / revoked·rejected·withdrawn→pending |
| accept / reject | **仅对方**（发起方 → 403 + 审计） | pending |
| withdraw | 仅发起方 | pending |
| revoke | 任一方（ADR-0006：禁新不杀旧） | accepted |

附加：`decided_by_user_id` + `decided_at` 落库（迁移 0002 新增列）；`expected_version` 竞态 → 409；accept 可收窄 `granted_scopes`、扩大 → 422 `scope_expansion`；accepted 记录不可被复用绕过审批（accept 仅从 pending 合法）；重复 accept → 422 `illegal_transition`（可解释幂等）。

负向测试（`tests/test_connection_security.py`，7 项全过）：
发起方自批准 403 · 第三方四种动作全 403 · 接收方 accept 成功且 decided_* 正确 · 重复 accept 422 · 陈旧版本 409 · 发起方 withdraw 合法/对方 withdraw 403 · revoke 后旧授权不可复活、重新请求必须对方再裁决 · scope 扩大被拒/收窄通过。

### P0-2 前后端响应类型不一致 — 已修复

`/v1/orgs` 返回 `{items, next_cursor}` 而前端按 `Org[]` 消费 —— 已在 `apps/web/src/api.ts` 修复为分页类型，并对全部响应做 **zod 运行时 schema 校验**（LoginResult/Me/OrgPage），前后端字段漂移会在浏览器里显式报错而不是静默渲染。

真实浏览器 E2E（`apps/web/tests/e2e/auth.spec.ts`，Playwright，系统 Chrome/CI chromium）：
- 错误凭据 → 显示 `Invalid credentials`，不建立会话 ✅
- 登录 → `/me`+`/orgs` 真实响应 → 渲染 `PA Admin`/`Smile Ortho (synthetic)`/`practice_admin` → 登出 → 会话服务端吊销（`/me` 直查 401）✅

`npm run build`（tsc+vite）通过；build PASS 未被当作 E2E PASS。

## 2. B0.1-03 安全缺口关闭

### A. 运行时不再持有 RLS 豁免凭据

- compose 新增 `migrate` 一次性服务：`alembic upgrade head` + 条件性 `seed`，独占 `DATABASE_ADMIN_URL`，执行完退出。
- `api` 服务 `DATABASE_ADMIN_URL` 置空 → `db.py` 中 admin engine **不创建**（可选化）。
- 登录边界查询改走迁移 0002 的 `resolve_login(email)` —— `SECURITY DEFINER` SQL 函数，仅投影 user/org/tenant/role 五列，`REVOKE PUBLIC` + 仅授权 `easyrs_app` EXECUTE。
- `apps/api/Dockerfile` CMD 不再内联 migrate/seed。

实测：`docker exec easyrs-dev-api-1 env` 中 `DATABASE_ADMIN_URL` 为空；登录/me/orgs 经 nginx 正常返回。

### B. 开发/生产隔离

- `seed.py`：`ENV` 非 dev/test → `SystemExit` 拒绝执行（`test_seed_refuses_prod` 实测非零退出）。
- `config.py` `model_validator`：`ENV=prod` 且仍用任何 dev 默认值（session_secret/db 口令/S3 凭据）或缺 `TOTP_ENCRYPTION_KEY` → 拒绝启动（ValidationError，`test_prod_fails_closed_on_defaults`）。
- 前端登录表单不再预填账号密码。
- compose 所有发布端口绑定 `127.0.0.1`（pg 55432 / redis 6379 / s3 9000-9001 / api 8000 / web 5173）。

### C. 认证安全

- **CSRF/Origin 中间件**：`/v1/*` 非安全方法必须带 `X-Requested-With: XMLHttpRequest`（跨站伪造无法携带自定义头），且 Origin 若存在必须在白名单。实测：无头 403 `CSRF header missing`，`Origin: evil.example` 403 `Origin not allowed`。
- **限流**（Redis 固定窗口，prod 故障时 fail-closed）：login 按 email 8/300s + IP 40/300s；2FA verify 按 IP 20/300s；password 5/900s；IAM 敏感写（orgs/locations/members/roster/connection 请求与裁决）按用户 60/300s。超限 → 429 `rate_limited` + `login_rate_limited` 审计；`test_sensitive_write_rate_limit` 实测第二笔写被拒。
- **2FA**：`auth_challenge.attempts` 上限 5，用尽即 consumed；过期/已消费/重放全 401。
- **改密即吊销其它会话**（`UPDATE auth_session SET revoked_at`，保留当前会话）。
- **TOTP 加密存储**：`totp_secret_enc` BYTEA，Fernet 加密；密钥源 `TOTP_ENCRYPTION_KEY`（prod 必填）否则 HKDF(session_secret)。测试断言库内 bytes 不含明文种子且可回环解密。
- Cookie 属性：`HttpOnly + SameSite=Lax`，`Secure` 仅在 ENV=prod。

## 3. B0.1-04 RustFS 兼容性（非"能 list_buckets 就行"）

`tests/test_s3_compat.py`（`S3_COMPAT=1` 门控，真实 boto3 → :9000）：

| 用例 | 结果 |
|---|---|
| put/get/head/delete + SHA-256 逐字节一致 | ✅ |
| 预签名 PUT 上传 + 预签名 GET 下载（httpx 实测） | ✅ |
| 错误凭据 → ClientError 拒绝 | ✅ |
| multipart create/upload-part/complete；abort 路径无残留 | ✅ |
| 20MB 大对象 | ✅ |
| `docker compose restart minio` 后对象可恢复 | ✅（本地实测，S3_RESTART=1） |

镜像固定为 digest：`rustfs/rustfs@sha256:9ca9559533b537d10482fe923288b676ad08f92a7069d9a17327fbae3cab688b`（compose 与 CI service 一致）。

## 4. B0.1-05 CI 门

| job | 内容 |
|---|---|
| `validate` | 既有基线/契约/秘钥扫描（保留） |
| `api-tests` | pg+redis services → **46 项 pytest**（25 原 + 21 新） |
| `s3-compat` | pinned rustfs service → 5 项 S3 接口实测（restart 项仅本地） |
| `e2e` | `docker compose up -d --build` 全栈 → Playwright chromium 2 项，报告 artifact 上传 |
| `web-build` | tsc + vite build |

junit 输出解析并在 job log 打印实际 `tests/failures/skipped` 计数（不写"全绿"）。原有 25 项测试全部保留且通过。

远端实测：run [40093135296](https://github.com/xiwei9871/open-rx/actions/runs/40093135296)（commit `0cfb24f`）五 job 全 success — `validate` / `api-tests` / `s3-compat` / `e2e` / `web-build`。前一轮 run 4009263* 曾暴露两处 CI 独有缺陷并已修复：postgres init 容器内未收到 `POSTGRES_APP_PASSWORD`（CI 覆盖值与 init 口令分裂）与测试字符串字面量命中秘钥扫描正则。

## 5. 测试数量变化

- 后端 pytest：**25 → 46**（+7 连接方向与安全、+11 CSRF/限流/会话/2FA/RLS 函数、+3 配置隔离）
- S3 兼容套件：**+6**（5 CI 常驻 + 1 本地 restart）
- 浏览器 E2E：**+2**（新增）
- 总计：**25 → 54**（本地 `46 passed, 6 skipped` + `5 passed, 1 skipped` + restart `1 passed` + e2e `2 passed`）

## 6. 仍保留的非阻断风险

- RustFS 仍非任务书点名的 MinIO（兼容范围已实测并固定 digest；未覆盖 S3 全表面，如 versioning/object-lock —— B0 资产域未需要，S1 前按需扩展）。
- 会话固定为首个 active membership，无机构切换端点（S1+）。
- `GET /v1/orgs` 列出租户内全部机构名（目录可见性，PROVISIONAL；对象级访问仍门控）。
- 限流为固定窗口（非滑动）；dev/test 下 Redis 不可用时 fail-open（prod fail-closed）。
- seed 的 PA↔LA 连接在 dev 环境直接以 accepted 预置（合成数据便利，非业务规则）。
- 无 refresh token / 邮箱验证 / 邀请接受流程。

## 7. 判定

| 评审问题 | 状态 |
|---|---|
| P0 连接自批准 | ✅ 消除（代码+7 负测） |
| P0 前后端类型不一致 | ✅ 消除（zod 校验 + 2 项真实浏览器 E2E） |
| 运行时管理员凭据 | ✅ 消除（admin engine 可选化 + resolve_login） |
| seed/默认密钥/前端预填/公网绑定 | ✅ 关闭 |
| CSRF/限流/2FA 上限/会话吊销/TOTP 加密 | ✅ 关闭 + 实测 |
| RustFS latest | ✅ 固定 digest + 接口面验证 |

**S0 地基：READY（条件性）** — 允许开始 S1 患者与处方开发；上表为遗留非阻断项。V1.1 官方核验（V-01~V-14）可并行，不阻塞。
