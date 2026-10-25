# Dossier — Parts / Appliances / Templates (V-04)

Sources read in full: SRC01, SRC02, SRC25, SRC33, SRC36 (index). Related: SRC-D2.

## Catalog structure (CONFIRMED SRC01 unless noted)

- **Universal Library of Parts and Appliances**: 500+ standardized items, maintained by EasyRx,
  distributed as a live document (parts/appliance names + pictures, downloadable PDF).
  We must NOT copy this artwork — EasyRS builds its own catalog (clean-room rule).
- Library doubles as a pseudo-lab on the Laboratory dropdown: create + print lab slip but cannot
  submit; lab can be switched to a connected lab before submitting.
- **Parts** = individual components (clasps, bows, screws, springs, bands, crowns…), searchable by
  standardized names; EasyRx acknowledges aliases (e.g. "Keeper Wire" = "Labial Support Wire",
  MEA = RPE).
- **Appliances** = composite designs (e.g. Hawley Retainer, RPE assemblies).
- **Part Options** = per-part parameter sets (bow type, wire gauge, screw type, flip). Rendered
  via red gear wheel; unset options are tolerated, not blocking.
- **Part Option Lookups** (SRC36 index): labs can create reusable option lookup lists linked to
  multiple parts; changing the lookup updates all linked parts. PARTIAL (index-level).
- Connected labs may define **custom parts**; available parts/appliances can differ per lab —
  the workspace catalog is lab-scoped (CONFIRMED SRC01: "parts and appliances may vary slightly
  depending on which lab").
- Labs can price parts/appliances/model services (CONFIRMED SRC16 index + SRC-D2: "pricing
  configured on your parts / appliances / model services").

## Templates (CONFIRMED SRC01, SRC33)

- Template = saved workspace composition (parts + positions + options + comments/annotations).
- Apply in one click; still fully editable after placement.
- Created by: practice saving its own workspace (`[Save as a template]`); lab creating for a
  specific practice via Practices→templates manager, or from inside a patient Rx canvas.
- Partial-assembly templates are supported (e.g. 4 anterior recurve springs).
- Provenance shown to practice: lab-provided templates marked with blue circle + letter.
- **Sharing permissions**: owner can assign other accounts Copy / Edit / View on a template;
  editable-shared templates can be overwritten by any grantee (documented risk); only the
  original owner/creator can edit permissions.
- November 2015 template model reworked "who can access and edit templates" (index reference —
  consistent with above, PARTIAL detail).

## Aligner / IDB / Resin / Digital Study Model option sets

- Aligners tab (SRC25): lab-configured dropdowns — Aligner Types (Upper/Lower/Both) and
  Post Treatment (Upper/Lower). Empty dropdown = lab has not configured; free-text fallback via
  Additional Notes.
- IDB form (SRC15 index + SRC02): lab-configurable option sets exist (Nov 2016 revamp).
- "Configuring 3D Resin Models, Aligner Rxs, Indirect Bonding Rxs, and Digital Study Model
  options" — one configure surface for product-class option sets (SRC15 index, PARTIAL).
- Implication: lab-scoped **product-class option dictionaries** are a confirmed concept.

## Manufacturing recipes (VisualDLP side, CONFIRMED SRC09/SRC10/SRC19/SRC20)

- Product catalog: Departments + Product Types groupings; products have price + workflow +
  variable-price flag; tag-along products auto-attach to a main product.
- Workflow = ordered Activities, each with day-of-production scheduling; Production Options carry
  method/cost/time and nonlinear per-unit scaling.
- Distinct from the drawing library: parts/appliance drawings are the Rx-side design vocabulary;
  VisualDLP products+workflows are the manufacturing/billing vocabulary. An Rx item is NOT the
  same entity as a production product (confirmed separation — they live in different modules).

## V-04 data model implication

Four layers confirmed, matching the required distinction:
1. Product/part type catalog (universal + lab-custom; arch placement rules; option dictionaries).
2. Template (versioned composition over the catalog; owner + share grants).
3. Patient Rx instance (concrete placements, options chosen, annotations — belongs to Rx).
4. Manufacturing recipe (workflow/activities/production options — lab-side, separate module).
