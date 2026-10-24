# Dossier — Lab-side workflows, VisualDLP MES (V-13)

Sources read in full: SRC-D2, SRC09, SRC10, SRC11. Index reads: SRC17, SRC18, SRC19, SRC20,
SRC21, SRC22.

## Written Check-In (CONFIRMED SRC-D2 — Enterprise lab feature)

- Workflow → Written Check-In: lab enters paper/faxed/emailed Rx for a non-EasyRx practice →
  internally creates an Rx + unique Prescription ID (recommended written on the paper slip).
- Then edit on the same Prescription Workspace (templates/drag-drop), refresh Standard Price
  (breakdown via grid icon; discounts/misc via Wrench icon); attach STL/supporting files.
- Print Rx produces a barcoded PDF (barcode speeds Check-Out + Batch Scan).
- Check-Out page: Prescription ID or barcode scan + shipping method/package specifics →
  Check-Out → Generate Invoices (editable under Invoices menu).
- Batch Scan: Workflow → Check-In → Scan Paper Rx tab → multi-page PDF → per-page Prescription
  ID entry (crop only affects viewing) → Send Home attaches the paper Rx image to the case and
  to the patient record.
- If the practice later joins EasyRx it gets full access to the historical Rxs/files and can
  request remakes/repairs from them.

## VisualDLP order entry (CONFIRMED SRC10)

- Order Entry: doctor name (typeahead; `*` wildcard; per-account shipping addresses) → patient
  first/last → optional completion date → Add Product (name or alpha code; narrowing list) →
  tooth number or arch → quantity auto-populates from tooth numbers (overridable) → price +
  workflow auto-populate → variable-priced products editable (red) → discount → Save.
- Remake/Adjustment: duplicate original order — links new order to original (SRC10 related
  article, confirmed by index text).
- Phonetic patient search on order list (SRC18 index); quick-view from results; per-account
  order/invoicing alerts; on-hold reason recorded in order history; **price-list changes do not
  retroactively change existing orders** (price snapshot semantics — CONFIRMED SRC18 index).
- Complete audit history added to Order Entry page (2019-08 update, SRC18 index).
- Enclosures: default list + custom items, printable on work tickets (SRC18 index).
- Proposals: order-status-8 pre-quotes printable for accounts (SRC18/SRC22 index).

## VisualDLP production model (CONFIRMED SRC09)

- Workflow = schedule of Activities a product follows through the lab; each activity has a
  day-of-production offset.
- Production Options: alternative methods for an activity carrying their own cost/time and
  **nonlinear per-unit scaling** (cost/time need not multiply by quantity).
- Giving Credit: per-activity completer tracking exists (SRC19 index).
- Auto-populate Ship/Due dates at scheduling; priority-ordered global settings (SRC19 index).
- Products grouped by Department + Product Type for reporting; tag-along products attach
  companion lines automatically (SRC20 index).

## Financials (CONFIRMED SRC11 + indexes)

- Export Transactions: date range + description filter (Invoice/Payment/Adjustment) + sort →
  CSV/PDF/Excel.
- Statements: mid-month and end-of-month batches; statement log verifies PDFs; regenerate for
  previous month; email template configurable.
- Payments: apply manually or automatically (oldest-first); credit adjustments supported.
- Accounts: tax-exempt flag; COD aging reports; report groups; sales-by-salesperson tracking;
  silent printing per user.
- EasyRx Pay: Stax-powered payments; practices connected to VisualDLP labs view + pay statements
  inside EasyRx (SRC16/SRC17 index).
- QuickBooks export for Enterprise labs (SRC16 index).

## V-13 conclusion for S1b/S2

- Lab-side case intake has three channels: connected-practice Rx (S1b), Written Check-In
  (Enterprise feature — defer to later stage, keep entity room for `origin=written_checkin`),
  scanner-driven.
- Production MES vocabulary confirmed: Order → Products (+tooth/arch, qty, price snapshot) →
  Workflow → Activities → Production Options; completer tracking; on-hold reasons; enclosures;
  remakes link to parent order.
- Do NOT conflate EasyRx `rx.status` with VisualDLP `order.status` — they are different modules
  even inside EasyRx's own product family; EasyRS keeps them separate with event projections.
