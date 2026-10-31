# Private Preview V0.1 — Evidence Index

Branch `devin/easyrs-private-preview-v01` · Baseline `main@81429f94`.
**Public URL: `https://easyrx.manqiaotechnology.com`** — live.

## Artifacts in repo

- `infra/docker-compose.preview.yml` — isolated stack
- `infra/preview/{deploy,backup,restore,reset-demo}.sh`, `env.preview.example`
- `apps/api/app/preview_seed.py` — controlled demo seed (prod + flag + token)
- `apps/web/tests/e2e/preview/preview.spec.ts` — 8-case deployed acceptance
- `docs/ops/private-preview-{deploy,rollback}.md`
- `docs/audit/private-preview-{security-report,public-uat,stock-nonregression}.md`
- `docs/audit/english-canada-ui-review.md`

## Live verification evidence (2026-10-25)

| Check | Evidence |
|---|---|
| Public HTTPS | `https://easyrx.manqiaotechnology.com/` → 200, wildcard LE cert valid to 2026-12-05 |
| Public API | `…/api/v1/auth/login` → session; `…/api/healthz` → 200 |
| Public S3 | `https://easyrx-s3.manqiaotechnology.com/` → 403 (unauth root = correct) |
| Presigned PUT | suite log: `https://easyrx-s3…/easyrs-preview-assets/staging/<org>/<uuid>?X-Amz-…` SigV4, expires 3600 — cross-origin PUT succeeded Chromium + WebKit |
| Security headers | HSTS 1yr, `x-frame-options: DENY`, `x-content-type-options: nosniff`, `x-robots-tag: noindex` |
| Session cookie | `easyrs_session`: HttpOnly + Secure + SameSite=lax over HTTPS |
| robots.txt | `Disallow: /` |
| Public UAT | **8/8 PASS Chromium + 8/8 PASS WebKit** over public HTTPS |
| External reach | check-host.net: 25/25 nodes HTTP 200; CA RTT 181–217ms, US 213–280ms |
| Stack running | `docker ps` — 5 preview containers healthy; migrate exited 0 |
| Headers (LAN) | X-Content-Type-Options/X-Frame-Options/X-Robots-Tag present |
| Demo seed | migrate log: `preview demo seed ok: tenant=… practice=… lab=…` |
| Regression | 72/72 PASS on dev stack after UI changes |
| Backup | `~/easyrs-preview-backups/easyrs-preview-20261025T133000Z` (160K) |
| Restore drill | snapshot restored; rx=4, patients=11, users=2; api 200 |
| Reset drill | `reset-demo.sh demo` → new tenant id, 5 synthetic patients reseeded |
| Stock health | water:5185 200; dashboard:5174 200; stock.manqiaotechnology.com 200; mems 200 — unchanged after gateway vhost add |

## Public ingress config (on gateway 192.168.3.224 / 101.207.144.86)

- `/www/server/panel/vhost/nginx/easyrx.manqiaotechnology.com.conf` → `192.168.3.185:5190`
- `/www/server/panel/vhost/nginx/easyrx-s3.manqiaotechnology.com.conf` → `192.168.3.185:5191` (`client_max_body_size 210m`, `proxy_request_buffering off`, Host passthrough for SigV4)
- Cert: `/www/server/panel/vhost/cert/easyrx.manqiaotechnology.com/` (copy of the existing `*.manqiaotechnology.com` LE wildcard)
- Rollback of ingress = remove the two confs + `nginx -s reload`.

## Remaining caveats

- Demo credentials live only in `~/easyrs-preview/demo-accounts.txt` on
  `.185` (chmod 600) — distribute to invitees out-of-band.
- Invitation control is app-layer (no edge IdP allowlist), per operator
  decision 2026-10-25.
- Status: **`PREVIEW_READY`** for invited demo use with synthetic data.
