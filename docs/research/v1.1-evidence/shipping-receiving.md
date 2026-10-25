# Dossier — Shipping, receiving, turnaround (V-07)

Sources read in full: SRC03, SRC27. Supporting: SRC02, SRC15, SRC18, SRC34.

## Ship (CONFIRMED SRC03)

- Lab action: `[Ship Rx]` icon inside the Rx view → prompts for tracking number.
- Tracking # optional but recommended; USPS/UPS numbers get in-browser tracking; other couriers
  tracked manually on their sites.
- Save → workflow bar shows `Shipped` + date; practice sees status + tracking from their account.
- On the free lab plan the workflow bar skips `Completed` — Completed/Check-Out with recorded
  dates is a Premium/Enterprise plan capability.

## Receive / Deliver (PARTIAL)

- SRC02 video index: "Marking cases as Received at your office(s) and Delivered to your Patients"
  — confirms practice-side Received and Delivered marks exist and that Received is per-office.
- SRC26 confirms `Received` appears in the lab-side All Cases status list.
- Delivered exists as a distinct mark (patient-facing final step). Whether Delivered is mandatory
  or only for tracking labs (e.g. Invisalign tracker) UNKNOWN.

## Turnaround / minimum date needed (CONFIRMED SRC27)

- Lab Configure → Ship Date Automation: `Days in Lab` (business days) + `Transit Time` per
  practice/office → `Total Days` = earliest Date Needed a practice may request.
- Holidays configured by the lab are skipped in the count.
- Transit time can be padded per doctor/location (example: +2 days for a distant office).
- Extension (index-level, PARTIAL→CONFIRMED by SRC34 note): scheduling can vary by **Part
  Category** and **Product Class** (in addition to practice overrides); a 2025 fix ensured
  Appliance types are also considered, not only Part rules.
- Effect: minimum selectable date is enforced at Rx creation time — practice "will not be able
  to request cases before" the computed date.

## Related logistics evidence

- Plaster model flow: model source flag on Rx + Prescription ID written on the physical box;
  lab matches the ID to the case (CONFIRMED SRC01).
- Mark Cases as Shipped tab supports filtering by Date, Practice Office, Production Location,
  Doctor, Tags (index-level 2019 update — PARTIAL).
- "Bin Number in Use" Enterprise error → Enterprise shipping supports bin/box batching by
  departure (index-level PARTIAL).
- VisualDLP auto-populates Ship Date/Due Dates when an order is scheduled; priority-ordered
  global settings control how ship time is set (SRC19 index, PARTIAL).

## V-07 conclusion for S1b

- Shipment is a lab-created object on the Rx (carrier, tracking #, shipped_at) — matches the
  EasyRS `shipment` entity owning `shipment.status` (no conflict).
- Received/Delivered are practice-side marks that update the workflow bar — model as
  `fulfillment_status` projection events: `received_at`, `delivered_at` on the Rx/summary.
- Date-needed validation: `date_needed >= today + lab.days_in_lab + lab.transit_time(practice)`
  business days, holiday-aware — CONFIRMED formula shape; keep the per-part-category/product-class
  modifiers PROVISIONAL (index-level).
