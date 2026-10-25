# Private Preview V0.1 — Evidence Index

Branch `devin/easyrs-private-preview-v01` · Baseline `main@81429f94`.

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
| Stack running | `docker ps` — 5 preview containers healthy; migrate exited 0 |
| LAN entry | `http://192.168.3.185:5190/` → 200; `:5190/api/healthz` → 200 |
| S3 entry | `http://192.168.3.185:5191/` → 403 (unauth root = correct) |
| Headers | X-Content-Type-Options/X-Frame-Options/X-Robots-Tag present |
| Demo seed | migrate log: `preview demo seed ok: tenant=… practice=… lab=…` |
| Presigned PUT | test log: SigV4 URL on public endpoint, org-scoped staging key |
| Preview UAT | 8/8 PASS (journey incl. upload, submit, bundle, QC, ship, deliver) |
| Regression | 72/72 PASS on dev stack after UI changes |
| Backup | `~/easyrs-preview-backups/easyrs-preview-20261025T133000Z` (160K) |
| Restore drill | snapshot restored; rx=4, patients=11, users=2; api 200 |
| Reset drill | `reset-demo.sh demo` → new tenant id, 5 synthetic patients reseeded |
| Stock health | water:5185 200; dashboard:5174 200; public stock URL 200 |

## Blocked pending operator access

- DNS record for `easyrx.manqiaotechnology.com` (registrar/zone control).
- lanproxy admin (`www.manqiaotechnology.com:8090`) or equivalent ingress
  config to map `easyrx…` → `192.168.3.185:5190` and the S3 endpoint → 5191.
- TLS certificate for the new hostname (whatever terminates the existing
  `*.manqiaotechnology.com` / `stock.*` hosts).

Until those exist the preview is reachable only via LAN/SSH tunnel —
status `PREVIEW_PARTIAL`.
