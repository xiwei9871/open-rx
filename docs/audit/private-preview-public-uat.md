# Private Preview — Public/UAT Results

Date: 2026-10-25 · Stack: `easyrs-preview` on 192.168.3.185 ·
Suite: `apps/web/tests/e2e/preview/preview.spec.ts` (8 tests, serial).

Access path used for this run: SSH tunnel
`localhost:8190 → 192.168.3.185:5190`, `localhost:8191 → :5191`
(same code path as the HTTPS ingress will serve; the secure-cookie flow
behaves identically on localhost).

| ID | Check | Result |
|---|---|---|
| PV-SEC-01 | demo welcome, banner, 3 entry buttons, security headers, robots.txt | PASS |
| PV-SEC-02 | unauth deep-link → sign-in; API 404 clean | PASS |
| PV-PRA-01 | demo shortcut → post-login routing + persistent banner + version | PASS |
| PV-PRA-02 | create patient, upper+lower STL upload via presigned PUT to public S3 endpoint, "valid mesh", warning copy shown | PASS |
| PV-PRA-03 | Rx draft→sign→submit bound to case | PASS |
| PV-PRA-04 | 200 MB declare rejected 422 readable | PASS |
| PV-LAB-01 | inbox → Download & Check-in (real bundle) → complete → QC pass → ship | PASS |
| PV-FUL-01 | practice receipt → delivery → audit trail | PASS |

Presigned PUT evidence (logged by the suite): targets were
`http://localhost:8191/easyrs-preview-assets/staging/<org>/<uuid>?X-Amz-…`
with SigV4 `X-Amz-Signature` — never the API host, never a bare LAN IP
inline. Expiry: `X-Amz-Expires=3600`.

## Not yet covered (blocked or deferred)

- **Real public HTTPS run** — pending lanproxy/DNS route for
  `easyrx.manqiaotechnology.com`. The same spec runs unchanged by setting
  `E2E_BASE_URL`/`PREVIEW_BASE_URL` to the public origin.
- WebKit/Safari leg — spec is browser-agnostic; run with
  `npx playwright test --project=webkit` once public.
- Canadian latency — cannot be inferred from localhost; needs a real CA
  access point once the URL exists.
- Cloudflare-Access rejection check — depends on the chosen edge control.
- Offline/retry UX and 1 MB/20 MB/50 MB matrix — deferred to the public run
  where they are meaningful (current: oversize-422 proven via declare API).

## Regression state

72/72 existing browser tests still pass on the dev stack after the UI
changes (en-CA labels, banner, inbox/history humanization). Assertions were
updated only where the rendered copy intentionally changed
(`checked_in → checked_in` → `Checked-In → Completed`, `format_ok` →
`valid mesh`, `sha256` → `SHA-256`, `(upper)` → `(Upper arch)`).
