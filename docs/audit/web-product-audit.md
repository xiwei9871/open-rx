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

## Results

| Round | Findings | P0 | P1 | P2 | P3 | Shots |
|---|---|---|---|---|---|---|
| 1 (before) | 8 | 6 | 0 | 2 | 0 | 52 |
| 2 (after)  | 0 | 0 | 0 | 0 | 0 | 40 |

Round 2 additionally exercised, with **zero findings**: STL orbit/zoom
pixel-diff (real gesture), duplicate-comment suppression, induced API
outage surfacing `role=alert`, lab `/patients` deep-link denial, bundle
download event with non-empty payload, and 390px overflow check.

## Round-1 findings (all remediated in round 2)

| # | Sev | Finding | Fix |
|---|---|---|---|
| F-01 | P0 | No URL routing — every page lived at `/`; no deep links, no back/forward | `App.tsx` rewritten with URL routes + `popstate`/`pushState` sync |
| F-02 | P0 | Refresh on a detail page lost context → showed bare `EasyRS` login shell even when signed in | route restoration + `me()` session probe on boot |
| F-03 | P1 | Global layout capped at `max-width:720px`; no shared design system | `styles.css` design system + responsive `.appbar`/`.container` shell |
| F-04 | P1 | `window.prompt()` for template name, required catalog options, location rename — modal-blocking, Playwright-hostile | inline controlled inputs (`RxCreate`, `OrgSettings`) |
| F-05 | P1 | Rx list/detail showed raw UUIDs; no patient/lab/doctor names | `RxOut` gains `patient_label`, `lab_name`, `practice_name`, `doctor_name`, `location_name` (`rx/schemas.py`, `rx/router.py`, `openapi.yaml`) |
| F-06 | P1 | STL preview auto-rotated, no user control | `StlPreview` → OrbitControls (orbit/pan/zoom), damping, Reset view, interaction hint; verified by drag pixel-diff |
| F-07 | P1 | RxDetail was one long unstyled scroll; no grouping | grouped into cards: header/status, edit (draft), actions, attachments, fulfillment, items, issues, comments, history |
| F-08 | P1 | 401 console noise on every anonymous visit (unconditional `me()` probe) | `easyrs_session_hint` readable cookie set/cleared with the session cookie; probe skipped when absent (`auth/router.py`, `App.tsx`) |
| F-09 | P1 | `window.open()` after `await` — real browsers popup-block the bundle download | `saveAs()` blob + anchor download (`lib.ts`); e2e asserts a real `download` event |
| F-10 | P1 | Double-submit race — `disabled={busy}` lands a frame too late; `act()`/`run()`/create handlers re-enterable | `busyRef`/`useActionLock` guards in `RxDetail`, `RxCreate`, `Patients`, `OrgSettings`, `Inbox`, `PatientDetail`; verified by double `dispatchEvent("click")` posting one comment |
| F-11 | P2 | Dev login/write rate limits broke repeatable browser suites | compose env overrides `RL_LOGIN_*`, `RL_WRITE_LIMIT` (prod defaults unchanged; security tests monkeypatch their own) |

No P0/P1 remain open.

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
- Key pairs are linked in `ui-before-after.md`.
- E2E suite: `apps/web/tests/e2e/` — 21 tests covering auth/2FA, patients,
  Rx lifecycle, studio, collaboration, fulfillment, UX regression.
- Backend: 146 pytest cases incl. real-S3 `asset-integration` suite.

## Honest limitations

- The STL preview covers orbit/pan/zoom only; EasyRx 3D editing (base
  builder, boolean ops, text engraving) is roadmap, not claimed.
- Lab-side "patient" label is the Rx-scoped projection (`P000041 —
  Synthetic, Ava`) — lab never gets patient-table access; verified denied.
- Download uses in-memory blob; very large bundles will page memory before
  save — acceptable at MVP scale, streaming noted in roadmap.
