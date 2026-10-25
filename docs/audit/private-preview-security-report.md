# Private Preview Security Report — 2026-10-25

## Posture

| Control | State |
|---|---|
| ENV | `prod` — prod guards verified enforced (boot refuses dev secrets) |
| Secrets | generated per-service on host, `.env.preview` mode 600, gitignored; nothing secret in git |
| Session cookies | `Secure`, `HttpOnly`, `SameSite=lax` under prod |
| CSRF | `X-Requested-With` header required on unsafe `/v1/*` methods + Origin allowlist |
| CORS | `CORS_ORIGINS` explicit list; S3 bucket CORS restricted to those origins (PUT/GET/HEAD) |
| Security headers | `X-Content-Type-Options`, `X-Frame-Options DENY`, `Referrer-Policy`, `Permissions-Policy`, `X-Robots-Tag noindex` on every response |
| robots | `robots.txt` served, `Disallow: /` |
| Public registration | none exists — accounts only via controlled seed |
| Rate limits | finite: login/email 30/300s, login/IP 120/300s, writes 60/300s |
| Upload cap | `UPLOAD_MAX_BYTES=104857600` (100 MB) — aligned to what the ingress is expected to pass; oversized declares return 422 with a readable message |
| 2FA | TOTP supported; `TOTP_ENCRYPTION_KEY` set (Fernet) |
| TLS | terminates at the external ingress (lanproxy → `:5190`) — pending public route |
| Access layer | lanproxy provides no app-level SSO; EasyRS login is the auth boundary. Cloudflare-Access-style email allowlist is NOT possible without lanproxy admin or Cloudflare access — see open items |

## Exposure surface

- Host-bound ports added: `192.168.3.185:5190` (web+api proxy), `192.168.3.185:5191` (rustfs presigned endpoint). Both LAN-only; direct public IP access to the host is not routed (verified: `101.204.19.48:80/443/5185` unreachable from outside).
- DB / Redis / rustfs-console: no host port, isolated `easyrs-preview_*` network.
- Redis: `requirepass` + appendonly, maxmemory 192mb LRU.

## Data-safety controls

- Synthetic-only tenant `preview-demo:<slug>`; UI shows persistent
  `Demo Environment — Synthetic Data Only` banner and an upload warning
  against real patient data.
- Demo reset is tenant-scoped SQL — cannot reach other tenants/systems.
- No AV engine exists (`asset_av_engine` = structural validation only):
  risk is mitigated by invitation-only accounts + 100 MB cap + .stl
  extension enforcement + per-org isolation. Arbitrary public uploads are
  NOT enabled; upload requires `asset:write` permission on a demo org.

## Verified by test

- PV-SEC-01/02: headers, noindex, robots, deep-link bounce, clean API 404.
- PV-PRA-02: presigned PUTs minted against the public S3 endpoint
  (SigV4, host-signed, 1 h expiry), upload restricted to authenticated
  `asset:write` members.
- PV-PRA-04: 200 MB declare → 422.

## Open items

1. **Public hostname/HTTPS route** — requires lanproxy admin (or DNS+edge
   access). Until then the demo is LAN/SSH-tunnel only: `PREVIEW_PARTIAL`.
2. **Invitation allowlist at the edge** — needs the same access; app-level
   login already gates everything.
3. Per-customer tenant provisioning works (`--slug`); invitation/revocation
   is operator-run, no self-serve.
4. No malware scanning beyond structural STL validation (documented limit).
