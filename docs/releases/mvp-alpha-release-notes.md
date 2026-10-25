# EasyRS MVP Alpha — Release Notes

Channel: **Alpha (synthetic data only)** · Base: PR #1 (S1b-Core, audited)
+ M1–M4 milestone commits on `devin/easyrs-full-mvp`

## What's in

**Practice side**
- Org profile/defaults/timezone, locations, member roster w/ default doctor,
  org connections (request/accept/withdraw/revoke), admin password set w/
  audit, org-scoped export (`GET /v1/admin/export`)
- Patients + cases + direct attachments w/ full Rx history per patient
- Rx Studio: connected-lab picker, doctor/location defaults, due date,
  catalog parts search, option dictionaries w/ required-field validation,
  tooth/arch marking, template save/apply, STL 3D preview (Three.js),
  debounced patient search, full loading/error/permission states
- Inbox: notifications, unread/pending counts, signed approvals bound to
  Rx version (drift → 409)

**Lab side**
- Queue (submitted+ only), Rx detail, download & check-in (real ZIP bundle:
  prescription.pdf + manifest + attachment bytes, sha-verified), issue
  notifications, approval requests, comments incl. attachment-anchored,
  Complete, QC record, ship w/ manual carrier/tracking

**Lifecycle**
- Rx: draft → submitted → checked_in → in_progress/on_hold → completed /
  reopened / cancelled — append-only transitions + audit
- Fulfillment (separate from clinical state): qc → shipped → received →
  delivered; dashboard counts + due-soon + filters
- Security: sessions, 2FA, CSRF, CORS allowlist, RBAC, RLS, If-Match
  optimistic locking, idempotency snapshots, upload limits + STL validation
  + scan hook, presigned TTL links, backup/restore scripts w/ drill record

## Database migrations

0001–0011 forward-only; `0009_m1_studio`, `0010_m2_collaboration`,
`0011_m3_fulfillment` added this program. Rollback path documented in
`docs/ops/deploy-upgrade-rollback.md` (expand/contract preferred).

## Known limits (Alpha)

- MANUAL items FLOW-012/LAB-019 intentionally manual (no carrier API, no
  auto-DLP nesting).
- Deferred to P1: IAM-005 (user admin detail), IAM-008 + RX-011 (template
  sharing across orgs).
- No real patient data. Ever.
- Deployments limited to test environments pending release authorization.

## Ops quickstart

```bash
cp .env.example .env
docker compose -f infra/docker-compose.yml up -d --build
python3 scripts/preflight.py          # env sanity
python3 tools/mvp_acceptance.py       # feature matrix gate
```

Docs: `docs/ops/deploy-upgrade-rollback.md`,
`docs/security/permission-matrix.md`, `docs/security/data-protection.md`,
`docs/audit/full-mvp-acceptance-report.md`.
