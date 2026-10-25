# UI/UX Before–After Evidence

Round 1 = pre-remediation baseline (`evidence/round1/shots/`),
round 2 = post-remediation verification (`evidence/round2/shots/`).
All screenshots are real Playwright captures at 1440×900 unless marked.

## App shell & navigation

| | Before | After |
|---|---|---|
| Evidence | `round1/01-practice_admin-patients-desktop.png` | `round2/01-practice_admin-patients-desktop.png` |
| Visible change | Bare `<h1>EasyRS</h1>` + loose buttons, page capped at 720 px | Fixed app bar: brand, signed-in identity (`PA Admin — practice_admin @ Smile Ortho`), active-route nav with unread badge, full-width content area |

## Prescriptions list

| | Before | After |
|---|---|---|
| Evidence | `round1/03-practice_admin-rx-list-desktop.png` | `round2/03-practice_admin-rx-list-desktop.png` |
| Visible change | 4 columns (`Rx #, Status, Due, Created`), free-text statuses, plain table | stat strip (Total / Submitted / Saved / Completed / Checked-In / QC pending / Delivered), Status+Fulfillment+Due-before filters, business columns (`Patient`, `Lab`), color-coded status pills |

## New prescription (Rx Studio)

| | Before | After |
|---|---|---|
| Evidence | `round1/04-practice_admin-rx-create-desktop.png` | `round2/04-practice_admin-rx-create-desktop.png` |
| Visible change | flat form; template naming and required catalog options collected via `window.prompt()` | three grouped cards (Order details / Parts & appliances / Notes); inline template select+name field; per-item required option fields; lab/doctor/location dropdowns |

## Rx detail

| | Before | After |
|---|---|---|
| Evidence | `round1/05-practice_admin-rx-detail-desktop.png` | `round2/05-practice_admin-rx-detail-desktop.png` |
| Visible change | one unbroken scroll of raw fields and buttons | grouped cards: status header with pills → draft edit → action bar (submit/unsubmit/check-in/complete/download) → attachments (with Preview) → fulfillment (carrier/tracking/QC) → items → issues → comments (with attachment anchor) → history trail |

## STL preview

| | Before | After |
|---|---|---|
| Evidence | code: `StlPreview.tsx` auto-rotate only | `round2/08-practice_admin-stl-orbited-desktop.png` (post-drag capture) |
| Verified behavior | mesh auto-rotated; no user control | OrbitControls: left-drag orbit, right-drag pan, scroll zoom, damping, Reset view; audit verified canvas pixels change on drag and on wheel — interaction is real, not just canvas presence |

## Login page

| | Before | After |
|---|---|---|
| Evidence | `round1/` role login shots | `round2/` role login shots |
| Visible change | console logged a `401` on every anonymous visit | session-hint cookie skips the `/auth/me` probe — console clean in round 2 |

## Lab workbench

| | Before | After |
|---|---|---|
| Evidence | `round1/22-lab_admin-rx-list-desktop.png` | `round2/24-lab_admin-rx-detail-desktop.png`, `round2/27-lab_admin-patients-denied-desktop.png` |
| Visible change | UUID-only rows; refresh on a detail dropped to the login shell | `Practice` column names the org, patient label is the Rx-scoped projection; refresh keeps context; `/patients` deep-link denied (screenshot shows the guarded view, no patient UI leaked) |

## Mobile 390×844

| | Before | After |
|---|---|---|
| Evidence | `round1/34…36` mobile set | `round2/36…39` mobile set |
| Visible change | 720px column forced horizontal scroll | nav wraps, forms stack, zero measured `scrollWidth` overflow (`documentElement.scrollWidth − clientWidth ≤ 1px`) |

## Failure modes (round 2 evidence)

- `round2/08-practice_admin-network-failure-desktop.png` — all API calls
  aborted via `page.route`; the list shows a `role=alert` error instead of
  a silent blank.
- Duplicate-click: two `dispatchEvent("click")` on Post produced exactly
  one comment (findings-raw clean).
- Empty Rx submit surfaces an in-app error (`role=alert`), not a silent
  browser-native block.
