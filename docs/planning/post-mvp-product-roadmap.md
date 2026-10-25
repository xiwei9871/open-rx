# EasyRS Post-MVP Product Roadmap

Priorities roll forward the P2/P3 findings from `docs/audit/web-product-audit.md`
plus EasyRx parity gaps that were explicitly out of MVP scope. Nothing below
is committed; order is a recommendation.

## P2 — product hardening (next release candidate)

| Item | Why | Evidence |
|---|---|---|
| List pagination + server-side paging | Rx/patient lists currently render all rows; fine at seed scale, not at production volume | `web-functional-findings.csv` F-12 |
| Global search bar (patients, Rx#, tracking) | EasyRx dashboard parity; reduces nav depth | F-14 |
| Saved filters / views on Rx list | EasyRx "dashboard views" parity | parity matrix |
| Rx detail tab layout | detail page still long with many attachments/comments | F-15 |
| Rx tags / labeling system | EasyRx public docs promote tags for filtering | parity matrix |
| Accessibility pass | skip link, focus-visible rings, table `scope`, keyboard orbit for STL canvas | F-13 |
| STL large-mesh handling | LOD/decimation worker, progress bar, cancel | F-16 |
| Lab workbench kanban + batch check-in | lab production efficiency parity | F-20 |
| Streaming bundle download | current blob path buffers whole ZIP in memory | audit report limitations |
| Field-level autosave / dirty-state guard on Rx detail edit | avoids lost edits | UX gap |
| Configurable due-soon window + email/webhook notifications | notification reach | — |

## P3 — post-MVP capabilities (new scope)

| Item | Notes |
|---|---|
| EasyRx-3D-class STL editing | base builder, label engraving, boolean ops, model inspection — deliberately excluded from MVP; needs its own design track |
| Practice↔lab template sharing | E2E-13 defer item; org-scoped template marketplace |
| Reporting/analytics | production metrics, turnaround time, QC defect rates |
| Carrier integrations | real label generation + tracking webhooks (manual entry stays as fallback) |
| Code-splitting + bundle budget | vite warns 764 kB chunk; lazy-load three.js |
| Dark theme + org branding | tokens already centralized in `styles.css` |
| i18n | strings currently hard-coded English |
| Scanner/printer integrations (VisualDLP-class) | vendor partnerships; out of Alpha scope |
| Offline/draft queue for unreliable clinic networks | service worker + outbox |

## Explicitly not planned

- Real-PHI deployment, jurisdiction e-signature certification, and any
  production use of the `eicar_stub` AV path — the AV hook is a seam for a
  real engine, not protection in itself (see `docs/security/data-protection.md`).
- EasyRx proprietary asset/code reuse — clean-room stance stands.

## Suggested sequencing

1. P2 list: pagination → global search → saved views → a11y pass.
2. Then Rx detail tabs + tags + lab kanban as one workbench theme.
3. P3 tracks each need a separate design doc before code.
