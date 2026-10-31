# English (Canada) UI Review — Private Preview V0.1

## Terminology normalization

| Before (internal enum) | Now rendered |
|---|---|
| `stl/upper` file kind | `Digital scan — Upper arch` |
| `format_ok` | `valid mesh` / `not a valid mesh` |
| `checked_in → completed` raw | `Checked-In → Completed` (STATUS_LABELS) |
| `[comment · open]` inbox tag | `Comment` / `Approval required` + `· unread` when applicable |
| `(upper)` item arch | `(Upper arch)` / `(Lower arch)` / `(Both arches)` |
| `sha256 abc…` | `SHA-256 abc…` |
| `∅ → draft` history start | `Created → Saved` |

Canonical labels used across pages: Patients, Treatment Cases,
Digital Scans, Prescriptions/Rx, Inbox, Settings, Upper arch/Lower arch,
Check-In, QC pass/fail, Confirm receipt, Confirm delivery.

## Locale

- Dates: `en-CA` rendering — `Oct 25, 2026` style (unambiguous, no MM/DD).
- Timestamps: shown in the org's configured timezone (`org.timezone`,
  editable in Settings → e.g. `America/Vancouver`, `America/Toronto`);
  falls back to the viewer's local zone.
- Units remain mm; no billing/CAD surface exists yet (out of scope).
- FDI tooth numbers retained; arch names now explicit.

## Demo surface

- Login page: welcome copy + three functional entries
  (Practice workflow / Lab workflow / Sample prescription) that store a
  post-login target — they route into real pages, not dead buttons.
- Persistent top banner when `VITE_DEMO=1` (preview builds):
  `Demo Environment — Synthetic Data Only · EasyRS Preview <tag>`.
- Upload card shows: `Do not upload real patient records, identifiable
  scans, or clinical data.`

## Remaining gaps (registered, not blocking preview)

- No full i18n framework — this is an en-CA pass, not a localization
  platform (per spec).
- Tooth display is a numeric grid, not a graphical FDI chart (P2, carried
  over from UAT findings).
- Some secondary admin surfaces still show compact codes where no label
  map exists yet (e.g. notification `via` in history); acceptable for an
  invited-demo audience.
- Mobile 390 px layout passes regression; no dedicated mobile redesign.
