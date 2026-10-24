# Dossier — Rx lifecycle (V-01 create/save/submit, V-02 check-in/unsubmit/ship)

Sources read in full: SRC01, SRC02, SRC03, SRC24, SRC25, SRC26, SRC-D6.

## V-01 Create Rx — confirmed mechanics (SRC01, SRC02)

Entry points: Dashboard `[Create Rx]` button, or `[Create Rx]` inside a patient record (CONFIRMED, SRC01).

### Create form (first screen)

| Field | Rule | Status / source |
|---|---|---|
| Patient first/last name | Auto-fill suggestion when same last name exists; creating the Rx also creates the patient record if new | CONFIRMED SRC01 |
| Laboratory dropdown | Connected lab, or "EasyRx Universal Library" (create/print but cannot submit; lab can be changed later) | CONFIRMED SRC01 |
| Patient ID | External PMS ID, optional, usable for patient lookup | CONFIRMED SRC01 |
| Date of Birth | Optional but recommended to disambiguate same-name patients | CONFIRMED SRC01 |
| Staff who made impression | Required only when account setting enables it | CONFIRMED SRC01 |
| Staff who submitted case | Same conditional requirement | CONFIRMED SRC01 |
| Doctor / office / date needed | Doctor and office locations are configured entities (SRC01 setup); "changing date needed" and "changing lab" are canvas toolbar actions (SRC02 video index). Exact requiredness on the form itself | PARTIAL |

`[Create Prescription]` opens the Prescription Workspace (canvas).

### Prescription Workspace (CONFIRMED SRC01 unless noted)

- Left panel: `[Parts, Appliances, Templates]` tree + search box; connected lab may expose custom
  parts; available items can differ per lab.
- Canvas: upper/lower arch drawing areas; drag-drop parts/appliances; left-click auto-place then
  drag. Blue circles mark draggable anchor points on the selected item only; not printed on
  submitted drawing.
- Arch constraints exist: e.g. an "Upper Invisible Retainer" cannot be dragged to the lower arch;
  most parts can go to either arch. (Rule per part — CONFIRMED existence, per-part matrix UNKNOWN.)
- Red "gear wheel" on a placed item = Part Options (e.g. Labial Bow: bow type + wire size .028/.032;
  RPE: screw type; recurve spring: flip). Menu icons turn red/animate when options need attention.
- Part Options may be left unset — guidance is to add a comment; lab expected to ask if unclear.
- **Update (SRC-D8): part options CAN be made required** — "Band options can now be required"
  ("Prompt for Bands" forces band details before submit). Treat `required` as a per-part-option
  flag that blocks submission when unset.
- **Update (SRC-D8): Ship To Patient** selection exists at create; org defaults for Doctor /
  Office / Ship To can autofill new Rxs (Sept-2023); Saved Rxs bulk-deletable; switching labs
  re-resolves that lab's field settings (bugfix evidence).
- Toolbar actions (SRC02 Part 2 index): save rx, save as template, add comment, set acrylic color,
  **change date needed**, **change lab**, text annotation, freehand sketch, polyline sketch.
- Comments (chat icon) = messages to the lab, visible below the drawing; lab can comment back;
  post-submission comments allowed.
- Text annotations (`[A]` icon) = text rendered on the drawing itself; Enter commits.
- Star Comment exists (SRC02 index — PARTIAL, semantics not detailed).
- Tabs below canvas (SRC02 Part 3 index): **Parts Used**, **Resets** (extractions / IPR / resets —
  explicitly for non-aligner and non-IDB cases), **Uploads** (attach STL + any file).
- Model Source box: iTero scans, "I am sending a plaster model / impression", other sources.
- Upload box accepts ANY file type (STL, PDF, images, Word). Files attached to an Rx are also
  saved to the patient's file. Storage is plan-limited (GB).
- Templates: one-click apply then fully editable; `[Save as a template]`; own templates under
  canvas Templates tab; lab-provided templates marked with a blue circle + letter.

### Checkout and submit

- A **Checkout Page** exists with "all options" including iTero Case Order ID entry (SRC02 index).
- `[Sign & Submit]` → `[Submit Prescription]` confirmation → overview page with workflow bar.
- On plaster-model submissions the system issues an **EasyRx Prescription ID** meant to be written
  on the physical package; it matches the case in the lab account and avoids putting the patient
  name on the box (CONFIRMED SRC01).
- Practice license agreement §6(g): the practice must provide signatures (incl. e-signatures) or
  initials to the lab when placing orders (SRC28) — consistent with "Sign & Submit" naming.
- Exact checkout field set (signature capture widget, shipping options, billing preview)
  UNKNOWN — no source enumerates the checkout controls.

### Save / edit / delete / resubmit

- `[Save]` keeps the Rx as a draft ("Saved"); re-editable including appointment date and assigned
  doctor (CONFIRMED SRC01).
- Saved Rxs surface on the LAB dashboard too, but only as "tags" — a saved Rx is NOT a formal
  submission (CONFIRMED SRC03).
- After unsubmit, the Rx returns to Saved and can be edited, have files changed, or be deleted
  (CONFIRMED SRC24).
- Deleted Rx: restorable via EasyRx support within **60 days**; attached files are removed from
  the restored Rx but remain on the patient record (CONFIRMED SRC-D6). Separately, deleting a
  checked-out prescription is permanent (index-level, SRC-D6 related article — PARTIAL).
- **Update (SRC34 Jan-2025): a self-serve "Rx recovery tool" now exists** that "should fully
  retrieve the files", and user accounts can be granted/restricted a **delete-Rx permission**
  (Account Settings > User Accounts). Bulk-delete of multiple Saved Rxs also exists
  (SRC-D8 Sept-2023).
- Per-Script billing counts a unique Prescription ID once — unsubmit + resubmit does not bill twice
  (CONFIRMED SRC24).

## V-02 State transitions — confirmed

| # | Transition | Actor | Trigger | Status |
|---|---|---|---|---|
| T1 | none → Saved | practice (any user with Edit Prescriptions) | Create + Save | CONFIRMED SRC01, D5 |
| T2 | Saved → Submitted | practice | Sign & Submit → Submit on checkout | CONFIRMED SRC01 |
| T3 | Submitted → Saved (Unsubmit) | practice | Unsubmit; only before lab check-in; lab may be notified; same Rx ID kept | CONFIRMED SRC24 |
| T4 | Submitted → Checked-In | lab | `[Check-In]` on dashboard or Rx view; opens case; practice notified | CONFIRMED SRC03 |
| T5 | Submitted → Checked-In | lab | **Downloading the Rx ZIP also sets Checked-In** — answers the file-download question: YES | CONFIRMED SRC03 |
| T6 | Checked-In → Shipped | lab | `[Ship Rx]` from Rx view; tracking # optional; USPS/UPS track in-browser | CONFIRMED SRC03 |
| T7 | Checked-In → Completed | lab (Premium/Enterprise plans only) | Check-Out records date; free-plan workflow bar skips Completed | CONFIRMED SRC03 |
| T8 | Shipped → Received | practice | "Marking cases as Received at your office(s)" | PARTIAL SRC02 index, SRC26 status list |
| T9 | Received → Delivered | practice | "Delivered to your Patients" | PARTIAL SRC02 index |
| T10 | Submitted/Checked-In → edit by lab | lab | Edit buttons exist ONLY on Submitted and Checked-In Rx (drawings, files, annotations, notifications) | CONFIRMED SRC23 |

Blocked transitions:
- Unsubmit after check-in is impossible — practice "will no longer have the ability to unsubmit"
  (CONFIRMED SRC03 + SRC24).
- iTero auto-attach cannot be added after submission (manual uploads can) (CONFIRMED SRC24).

Irreversibility: check-in is not undoable by either side; Checked-Out deletes are permanent.
"Completed Rx" vs "production complete": Completed is a plan-gated lab workflow step (Premium/
Enterprise check-out); production completion inside VisualDLP is a separate order-lifecycle
concept. The two are NOT the same entity (CONFIRMED SRC03 + SRC09).

Notifications on transitions (CONFIRMED SRC03/SRC24): check-in notifies the practice; unsubmit may
notify the lab; ship gives practice tracking access. Alert-notification preferences cover email/
popup (SRC02 index).

### Existing EasyRS state machine — conflict check

`docs/architecture/state-machines.md` models `draft→submitted→checked_in→in_progress→completed`
plus provisional hold/cancel. Mapping to evidence:
- `draft` ≈ EasyRx `Saved` (CONFIRMED).
- `submitted` matches. Unsubmit transition `submitted→draft` matches evidence.
- `checked_in` matches; **add the rule that a lab download/check-in action triggers it**.
- `in_progress` has NO direct EasyRx equivalent as a public Rx status — EasyRx goes
  Checked-In → (Completed) → Shipped. Keep `in_progress` as an optional lab-internal stage
  PROVISIONAL, or drop it from `rx.status` (recommend keeping it out of the public status;
  production progress belongs to `production_order.status`).
- `completed` matches plan-gated Completed/Check-Out — CONFIRMED to exist; keep as reachable
  state with evidence note.
- shipped/received/delivered correctly excluded from `rx.status` already (fulfillment projection);
  EasyRx itself shows them on the workflow bar — no conflict, different axis.

Open questions left UNKNOWN: cancellation fees, whether a checked-out Rx can reopen, QC retry
limits, whether lab edits create a new version requiring re-approval (notifications support
approval requests — the state linkage itself is not documented).
