# EasyRS Web Product Audit — Report

**Baseline:** `30065f03a22ab9f6faa937fb9ffc4a1171fbbce7` (post A–E closure)
**Scope:** full-site functional + UI/UX audit against the real running stack
(PostgreSQL + Redis + MinIO/RustFS + nginx SPA), benchmarked only against
publicly available EasyRx material. No EasyRx login, proprietary assets, or
real patient data were used. All test data is the synthetic seed set.

## Method

`apps/web/tests/audit/run-audit.mjs` drives Playwright (Chromium) through:

- **Five roles:** `admin@pa.dev`, `doctor@pa.dev`, `staff@pa.dev`
  (practice), `admin@la.dev`, `tech@la.dev` (lab). The doctor's 2FA factor is
  reset via SQL before plain-credential sign-in because `auth.spec` enables
  it mid-suite.
- **Three viewports:** 1440×900 desktop, 1280×800 laptop, 390×844 mobile.
- **Per role walk:** every reachable page screenshotted; console errors,
  page errors, failed requests, HTTP 5xx/404 recorded per interaction.
- **Real-world checks:** deep-link URLs, browser back/forward, refresh on a
  detail page, empty-form submit, duplicate-click comment, lab role
  deep-linking into `/patients`, induced network failure (`route.abort`),
  STL upload → preview → drag-orbit pixel-diff, scroll-zoom pixel-diff,
  bundle download producing a real file-download event, mobile horizontal
  overflow measurement.
- **Two rounds:** `evidence/round1` = pre-fix baseline, `evidence/round2`
  = post-fix verification.

## Results — separate tallies (not a single "zero")

The counts below are deliberately kept apart; they measure different
things and must not be collapsed into one "zero issues" claim.

| Category | Count | Detail |
|---|---|---|
| Round-1 automated findings | **8, all P0** | 3 routing (deep-link/back/forward), 3 page-crash (refresh on detail dropped to login shell), 2 refresh-state-loss. See `findings-raw.json` — every record is severity P0 |
| Code-review findings | 11 (F-03..F-11 in `web-functional-findings.csv` carry `source` labels) | 8 P1 fixed (prompts, UUID display, STL controls, download blocker, 401 noise, double-submit) + 1 P2 dev-rate-limit fix (F-11); 2 overlapped round-1 auto findings |
| Round-2 automated findings | **0** | re-run after remediation; `findings-raw.json` = `[]` |
| Open P2/P3 (deferred, not defects) | 9 | F-12..F-20 → `post-mvp-product-roadmap.md` |

| Round | Finding records | P0 | P1 | P2 | P3 | Shots |
|---|---|---|---|---|---|---|
| 1 (before) | 8 | 8 | 0 | 0 | 0 | 52 |
| 2 (after)  | 0 | 0 | 0 | 0 | 0 | 40 |

Round 2 additionally exercised, with **zero findings**: STL orbit/zoom
pixel-diff (real gesture), duplicate-comment suppression, induced API
outage surfacing `role=alert`, lab `/patients` deep-link denial, bundle
download event with non-empty payload, and 390px overflow check.

## Findings ledger (numbered `F-xx` in `web-functional-findings.csv`)

`source` distinguishes **audit-auto** (recorded live by
`run-audit.mjs`/screenshot evidence) from **code-review** (found by
inspection, verified in the app, not necessarily re-detectable
automatically).

| # | Sev | Source | Finding | Fix / disposition |
|---|---|---|---|---|
| F-01 | P0 | audit-auto | No URL routing — deep links, back/forward, shareable URLs all broken | `App.tsx` rewritten with URL routes + `popstate`/`pushState` |
| F-02 | P0 | audit-auto | Refresh on a detail page lost context → login shell even when signed in | route restoration + `me()` session probe on boot |
| F-03 | P1 | audit-auto | Bare layout, 720 px cap, no design system | `styles.css` tokens + responsive `.appbar`/`.container` shell |
| F-04 | P1 | code-review | `window.prompt()` for template name + required catalog options | inline controlled inputs in `RxCreate` |
| F-05 | P1 | code-review | `window.prompt()` for location rename | inline field in `OrgSettings` |
| F-06 | P1 | code-review | Rx list showed only Rx#/status/due — no patient or lab identity | stat strip + Patient/Lab columns + filters |
| F-07 | P1 | code-review | List/detail rendered raw UUIDs | `RxOut` display fields (`patient_label`, `lab_name`, `doctor_name`, `location_name`) |
| F-08 | P1 | code-review | RxDetail one ungrouped scroll | grouped card sections + action bar |
| F-09 | P1 | code-review | STL preview auto-rotate only | OrbitControls orbit/pan/zoom + Reset; pixel-diff verified |
| F-10 | P1 | code-review | 401 console noise on anonymous visit | `easyrs_session_hint` readable cookie gates the `me()` probe |
| F-11 | P1 | code-review | `window.open()` after `await` popup-blocked (bundles + patient assets) | `saveAs()` blob + anchor download; real download event verified |
| F-12 | P1 | code-review | Logout never sent delete `Set-Cookie` headers (dead cookie stayed in jar); double-submit race in `act()`/`run()` | logout returns the `Response` carrying both deletions; `useActionLock`/`busyRef` re-entry guards |
| F-13 | P2 | code-review | Dev login/write rate limits broke repeatable suites | compose env overrides only; prod defaults + security tests unchanged |

All P0/P1 above are FIXED and re-verified in round 2 (0 findings).
F-19 (P2, silent empty-comment no-op) and F-12..F-20 roadmap items were
already recorded in the CSV; open items below.

## Coverage matrix (actual, not claimed-full)

Recorded by `run-audit.mjs` in `coverage.json`. "—" = not applicable.

| Area | Roles | Viewports | Verified |
|---|---|---|---|
| Login + logout | 5/5 | desktop | cookie set/cleared incl. hint cookie |
| Patients list/detail/create | practice_admin, doctor, staff | desktop + 390px | — |
| Lab `/patients` deep-link denial | lab_admin | desktop | guarded redirect, no leak |
| Rx list / detail / create | 5/5 roles | desktop; doctor+tech also 1280 & 390 | filters, stat strip, template apply |
| STL upload → preview → orbit/zoom | practice_admin | desktop | pixel-diff on drag + wheel |
| Bundle download | practice_admin, lab_admin | desktop | real `download` event, non-empty |
| Comments, double-click dedupe | practice_admin | desktop | 2 clicks → 1 comment |
| Induced network outage | practice_admin | desktop | `role=alert` surfaces, not silent |
| Mobile 390px overflow | doctor, lab_tech | mobile | 0 px overflow measured |
| Refresh/back/deep-link | all roles | desktop | route restore |
| 2FA challenge | (covered by `auth.spec.ts` e2e, not the audit walk) | — | — |

This is a **sampling matrix**: the audit walks a representative path per
role/viewport, it does not claim exhaustive coverage of every page on
every role/viewport combination.

## P2/P3 deferred to roadmap

See `docs/planning/post-mvp-product-roadmap.md`. Highlights: list
pagination/virtualization, global search, saved views, tags (EasyRx
parity), a11y pass (skip link, focus rings, table semantics), loading
skeletons, 3D edit tools (EasyRx 3D parity — explicitly non-MVP), bundle
code-splitting (764 kB chunk warning), i18n, dark theme.

## Evidence index

- `docs/audit/evidence/round1/` — 52 screenshots + `findings-raw.json`
- `docs/audit/evidence/round2/` — 40 screenshots + `findings-raw.json`
  (`[]` — zero findings)
- Key pairs are linked in `ui-before-after.md` (every referenced path
  verified to exist on disk).
- E2E suite: `apps/web/tests/e2e/` — 23 tests covering auth/2FA, patients,
  Rx lifecycle, studio, collaboration, fulfillment, UX regression, and
  the logout-cookie regression pair.
- Backend: 148 pytest cases incl. real-S3 `asset-integration` suite and
  the logout delete-`Set-Cookie` assertions.
- **CI gate** (`validate.yml` → `e2e` job, after the Playwright suite):
  1. `run-audit.mjs --out audit-evidence` — full walk; any P0/P1 fails
     the job (nonzero exit).
  2. `run-audit.mjs --self-test` — synthetic severity matrix + live
     injected console error must both trip the gate.
  3. `AUDIT_INJECT=1 --quick` — real failure-injection run must exit 1;
     a green result fails the job (`|| exit 1` inversion).
  Artifacts (`web-audit-evidence`, `if: always()`): `findings-raw.json`,
  `coverage.json`, `summary.json`, all screenshots, per-role
  `trace-*.zip` when a role produced findings, plus the injected-run
  findings as tamper evidence.

## Honest limitations

- The STL preview covers orbit/pan/zoom only; EasyRx 3D editing (base
  builder, boolean ops, text engraving) is roadmap, not claimed.
- Lab-side "patient" label is the Rx-scoped projection (`P000041 —
  Synthetic, Ava`) — lab never gets patient-table access; verified denied.
- Download uses in-memory blob; very large bundles will page memory before
  save — acceptable at MVP scale, streaming noted in roadmap.
