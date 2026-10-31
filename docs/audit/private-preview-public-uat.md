# Private Preview — Public/UAT Results

Date: 2026-10-25 · Stack: `easyrs-preview` on 192.168.3.185 ·
Suite: `apps/web/tests/e2e/preview/preview.spec.ts` (8 tests, serial).

## Public HTTPS run — PASS

Access path: **`https://easyrx.manqiaotechnology.com`** → gateway nginx
(`192.168.3.224` = `101.207.144.86`, aaPanel `*.manqiaotechnology.com`
wildcard LE cert) → `192.168.3.185:5190`. S3 presigned endpoint:
`https://easyrx-s3.manqiaotechnology.com` → `192.168.3.185:5191`.

| Engine | Result |
|---|---|
| Chromium | **8/8 PASS** (1.2m) |
| WebKit 18.2 | **8/8 PASS** (1.6m) |

| ID | Check | Result |
|---|---|---|
| PV-SEC-01 | demo welcome, banner, 3 entry buttons, security headers, robots.txt | PASS (both engines) |
| PV-SEC-02 | unauth deep-link → sign-in; API 404 clean | PASS (both) |
| PV-PRA-01 | demo shortcut → post-login routing + persistent banner + version | PASS (both) |
| PV-PRA-02 | upper+lower STL upload via presigned PUT to **public** S3 endpoint | PASS (both) |
| PV-PRA-03 | Rx draft→sign→submit bound to case | PASS (both) |
| PV-PRA-04 | 200 MB declare rejected 422 readable | PASS (both) |
| PV-LAB-01 | inbox → Download & Check-in (real bundle) → complete → QC pass → ship | PASS (both) |
| PV-FUL-01 | practice receipt → delivery → audit trail | PASS (both) |

Presigned PUT evidence (suite log): targets were
`https://easyrx-s3.manqiaotechnology.com/easyrs-preview-assets/staging/<org>/<uuid>?X-Amz-…`
with SigV4 `X-Amz-Signature`, `X-Amz-Expires=3600` — never the API host,
never a LAN IP. Browser CORS PUT succeeded cross-origin
(`easyrx…` → `easyrx-s3…`) in both engines.

Note: the suite consumes the seeded lifecycle (ship→receive→deliver), so a
re-run requires `reset-demo.sh` first (done between the two public runs).

## TLS / headers / cookies (public path, verified by curl)

- `https://easyrx…` → HTTP 200, valid wildcard LE cert (`ssl_verify_result=0`).
- Headers: `strict-transport-security: max-age=31536000`,
  `x-content-type-options: nosniff`, `x-frame-options: DENY`,
  `x-robots-tag: noindex, nofollow`.
- `Set-Cookie: easyrs_session=…; HttpOnly; Secure; SameSite=lax` over HTTPS.
- `robots.txt` → `Disallow: /`.
- `https://easyrx-s3…` → S3 403 at root (RustFS reachable, unauthenticated
  root denied as expected).
- Login over public API returns session + demo org
  (`Harbourview Orthodontics (demo)`).

## External reachability + latency (check-host.net, request 535c8f16/535c9576)

- HTTP GET `/` → **200 from all 25 external nodes** (EU/US/Asia).
- Ping RTT to `easyrx.manqiaotechnology.com` (101.207.144.86):
  **ca1 (Canada) min 181ms / avg 217ms**; us1 213ms, jp1 121ms, de2 167ms.
  This is the Canada-direction measurement requested — real external
  vantage, not inferred from LAN timings.

## Deferred / honest gaps

- 1 MB / 20 MB / 50 MB synthetic STL matrix — only the standard fixtures
  (~KB–MB) plus 200 MB oversize-422 were exercised end-to-end; the
  intermediate sizes were not run as separate cases.
- Offline/retry UX and double-submit — covered by regression suite
  (dev stack), not re-run over the public path.
- Gateway `server_session_afc7a8e9` cookie is set by aaPanel/nginx on the
  edge (informational; not app-owned).
- Cloudflare Access equivalent: app-layer invitation only, per operator
  decision — the edge does not add an email-allowlist IdP.
