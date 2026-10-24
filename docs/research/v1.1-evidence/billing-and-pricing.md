# Dossier — Billing & pricing (V-09-adjacent)

Sources read in full: SRC24, SRC-D1, SRC-D2. Index: SRC16, SRC17, SRC18, SRC34.

## Practice-side billing (CONFIRMED SRC24, SRC-D1)

- Per-Script plan: billed per unique **Prescription ID** submitted — unsubmit + resubmit of the
  same Rx does NOT double-bill.
- Pay for Practice (all lab plans): lab covers a percentage of a practice's EasyRx fees;
  optional **minimum monthly submissions** threshold before the subsidy applies; Active/Inactive
  toggle; appears as a line item on the lab's monthly invoice; no split payments; 100%-covered
  practices still see an invoice showing lab payment, card not charged.
- Practice still enters a card on file even when lab pays.
- Plans referenced across sources: Practice (free/standard?) Standard, Standard + 3D, Premium
  (unlocks In-House Lab), Per-Script; Lab Standard, Premium, Enterprise, VisualDLP; EasyRx Pay.
  Exact tier names/prices not fully enumerated — PARTIAL.

## Lab-side pricing (CONFIRMED SRC16 index, SRC-D2)

- Labs price their parts/appliances/model services (Configure tab); used to compute **Standard
  Price** on the Rx (refresh + breakdown grid); discounts and misc charges via Wrench icon.
- Alternate price lists: up to 4 pricing tiers assignable per practice; new practices default to
  Standard Pricing.
- 2025 (CONFIRMED SRC34): pricing on Templates shows a **price comparison during submission**.
- Tax/shipping calculated at invoicing time, not in Standard Price (SRC-D2).
- Price changes don't retro-affect existing orders (CONFIRMED SRC18 index — snapshot semantics).

## Invoicing & payments (CONFIRMED)

- Enterprise labs generate invoices inside EasyRx; practices see them if their user account has
  the **Finances** flag (SRC-D5).
- VisualDLP: invoice from checked-out orders; statement runs (mid/EOM), regenerate, email
  templates, aging reports, payment application (manual / auto-oldest-first), credit adjustments,
  tax-exempt accounts, QuickBooks CSV export.
- EasyRx Pay (Stax): practices pay VisualDLP statements in-app.

## License-agreement money clauses (CONFIRMED SRC28)

- Termination: practice paid-in-full + written request + **$150 processing fee** → EasyRx
  provides digital copy of User Content (data-export exit clause).
- Fees change only for selections made after announcement; disputes between practice and lab are
  settled directly between them.

## Implication for EasyRS

- Rx-level `price_snapshot` at submission time (parts+options priced against the lab's price list
  effective for that practice) — CONFIRMED pattern to follow; keep totals PROVISIONAL until we
  model the lookup tables.
- Billing counters must key on `rx.id` uniqueness, never on submit events.
- EasyRS S1b scope: capture prices if present, display lab-provided comparison when available;
  full invoicing deferred to S2+.
