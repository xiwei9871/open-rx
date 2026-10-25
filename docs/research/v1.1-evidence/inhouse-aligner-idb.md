# Dossier — In-house lab, Aligner/IDB forms, Invisalign tracking (V-11)

Sources read in full: SRC25, SRC26. Index: SRC02, SRC15, SRC34.

## In-House Lab (CONFIRMED, plan-gated)

- Practice Premium feature (CONFIRMED SRC25 FAQ + SRC02 index + SRC15 acrylic-chart article).
- Practice configures: Aligner options (Account Settings → Aligners), acrylic color/decal chart,
  3D resin model / aligner / IDB / digital study model option sets (SRC15 index).
- In-House Lab dashboard: view cases, check in / complete cases (updates workflow), view digital
  models/files, comments, tags (SRC02 index — CONFIRMED feature surface, detail PARTIAL).
- User-account flag `In House Lab` (SRC-D5): view-only limited login restricted to in-house Rx;
  default users can already access the in-house area.
- Invisalign tracking labs are a specialized in-house-lab variant enabled by EasyRx support.

## Aligner prescription form (CONFIRMED SRC25)

- `[Aligners]` tab below the canvas on the Prescription Workspace.
- Lab-configured dropdowns: Aligner Types (Upper/Lower/Both), Post Treatment (Upper/Lower).
- Empty options → lab hasn't configured; free-text fallback via Additional Notes; EasyRx will
  help labs configure.
- Canvas reflects the form choices; then comments → Proceed to checkout.
- Invisalign caveat: real Invisalign submission must go through Invisalign's own process; an
  EasyRx aligner case to the in-house lab is for record/tracking only.

## IDB prescription form (CONFIRMED existence, PARTIAL detail)

- `[Indirect Bonding]` tab on the workspace (SRC15 index + SRC02 video).
- Lab-configurable IDB options (Nov 2016 revamp article exists) — structure PARTIAL.

## Invisalign Tracking Lab (CONFIRMED SRC26)

- Practice Premium + Invisalign Tracking lab (enabled by EasyRx support).
- Dedicated workflow bar; workflow buttons clickable; tracking-lab login can advance statuses
  including marking the case Submitted.
- `iTero Recent Scans` view in the tracker lab.
- Invisalign Case Number field editable from either login; shown on view/print.
- All Cases tab statuses: **Saved, Scanned, Submitted, Shipped, Received** — public confirmation
  of status vocabulary (Scanned = barcode-scanned Invisalign box receipt).
- Removed tabs for tracker labs: Digital Submitted, Physical Submitted, Checked-In Cases.
- Barcode scanning feature exists for Invisalign box tracking (SRC15 index).

## Implication for S1b

- Rx form is polymorphic by product class: default canvas Rx, Aligners form, IDB form — each
  contributes structured fields onto the same Rx entity. Model as `rx.form_type` + JSONB
  `form_payload` validated per lab-configured option dictionary.
- Resets tab (extractions/IPR) is explicitly NOT for aligner/IDB cases — form-type conditional.
- In-house lab = a connection to a same-tenant lab org with restricted surface; keep as a
  PROVISIONAL organization flag rather than a separate module.
