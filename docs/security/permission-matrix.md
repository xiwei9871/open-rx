# Permission matrix (MVP)

Source of truth: `apps/api/app/security.py` `ROLE_PERMISSIONS`.
This document is generated from that map — update the code first.

| Capability | practice_admin | practice_doctor | practice_staff | lab_admin | lab_technician |
|---|---|---|---|---|---|
| org:manage | ✓ | — | — | ✓ | — |
| location:write | ✓ | — | — | ✓ | — |
| member:write | ✓ | — | — | ✓ | — |
| roster:write | ✓ | — | — | — | — |
| roster:read | — | ✓ | ✓ | — | — |
| connection:write | ✓ | — | — | ✓ | — |
| audit:read | ✓ | — | — | ✓ | — |
| patient:read/write/delete | ✓ | read+write | read+write | — | — |
| asset:read | ✓ | ✓ | ✓ | ✓ | ✓ |
| asset:write | ✓ | ✓ | ✓ | ✓ | — |
| asset:share | ✓ | ✓ | — | — | — |
| rx:read | ✓ | ✓ | ✓ | ✓ | ✓ |
| rx:write | ✓ | ✓ | ✓ | ✓ | ✓ |

Enforcement layers (defense in depth):
1. `require_perm(...)` dependency on every route.
2. Application predicates: `_rx_for_practice_write` / `_rx_for_lab_write` /
   `_is_party` scope Rx mutations to issuing practice vs addressed lab.
3. PostgreSQL RLS: every tenant-scoped table has a `tenant_isolation`
   policy bound to `app.tenant_id`, set per request by `get_principal`.
4. Uniform 403 + `access_denied` audit event on authorization failure —
   object existence is never revealed to outsiders.

Object-level semantics beyond the role matrix:
- Rx: practice side = issuing org; lab side = `lab_org_id` match and
  status ≥ submitted (drafts are never lab-visible).
- Assets: owning org, or a live (unrevoked) `file_reference` whose subject
  is visible to the caller.
- Notifications: org-scoped inbox (`notification.org_id`).
- Admin export: `org:manage` only; returns the caller's own org.
