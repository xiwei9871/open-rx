# Dossier — Files, assets, 3D view/edit/AI (V-05)

Sources read in full: SRC04, SRC05, SRC06, SRC07, SRC08, SRC31. Supporting: SRC35, SRC14.

## Asset model (CONFIRMED)

- STL attach points: Rx Uploads tab, patient record, scanner integrations (iTero auto-attach;
  TRIOS/Medit/Dexis/3Disc/Alliedstar/Planmeca/3M OCP "Recent Scans" lookups).
- iTero flow: original scan → auto-generated "optimized file" (~5 min) → both listed on the Rx;
  optimized file opens the editor (SRC05).
- Files attached to an Rx are also saved to the patient's file — patient-level asset aggregation
  is CONFIRMED.
- File actions on the File Upload list: open view/edit, delete, scrub, scrub+remesh (recommended
  before basing), download (SRC06).
- Deleted-Rx restores lose Rx attachments but files persist on the patient record (SRC-D6).
- Plan-gating: 3D View in all plans; 3D Edit requires Practice Standard+ / Lab Standard+.

## EasyRx 3D manual edit (CONFIRMED SRC05/SRC06 — pipeline for the future 3D worker)

1. Orient: 3 orientation points; ~10s; produces orange trim-ring dots.
2. EasyModelTrim: freehand trim path (Shift+drag), resumable across rotations; ring closes → dots
   flash green; adjustable control points; points on scanner cracks turn red (failure markers).
3. Trim Model (scissors) OR Cut Model — 2-point cutting plane behind molars for vertical prints.
4. Base: Regular (solid) or Hollow; base height (preset or custom drag); hollow → wall thickness;
   optional "Use Drain Holes" (3 holes + pry notch) for horizontal prints.
5. Label: patient name default, custom text; Engraved or Embossed; up to 2 positioned labels.
6. Save Model → visible on Rx, patient profile, and View STL Print List.
- Preserve-occlusion save keeps the bite registration between upper/lower scans (SRC35 index,
  confirmed concept).

## 3D AI services (CONFIRMED SRC04, SRC07)

- 3D Command Center; activation via sales. Per-org mode: **Automatic** (process every scan) vs
  **On Demand** (per-scan request).
- Services: Automated Bracket Removal (ABR), Automated Basing (ABS), AI Blockout, PTS trim-line
  generation, ATP (auto treatment prep — name seen in per-lab exclusion list).
- Practices can EXCLUDE labs from automated processing (e.g. only process in-house scans).
- Automatic Basing defaults (verbatim option set): Trim Type {Horseshoe, Full Palate, Horseshoe
  with Removed Molar Gingiva}; Trim Margin mm; Base Height mm; Model Type {Regular, Hollow};
  Wall Thickness (hollow); Label Position {side, attached block for OCR}; Preserve Occlusion
  (recommended); Extrude Palate (only with minimal trim, not with PTS path); "make the file name
  the default label" toggle; PTS trim-line auto-generate toggle.
- AI Blockout: intensity levels for interproximal + gingival blockout + undercut retention
  distance; add-on for 3D+ plans (SRC07).
- EBR (manual bracket removal) exists as an add-on (SRC35 index).
- 2025: **AI Profiles can be saved from the Request AI Service page** (March 2025) and assigned
  per-appliance (Feb 2025: "Appliance A → Profile A"); auto-processing can be restricted to
  mapped Templates/AI Profiles (May 2025) — profile persistence CONFIRMED (SRC34).
- Processed-file naming: raw → `3D-O` output → `3D-E` edited output (SRC-D8 Dec-2023 bugfix).
- Ready-to-Print / Downloaded / Printed print-status flags: NOT verified in any read source —
  UNKNOWN (was inventoried as D1 from secondary notes).

## EasyFS (CONFIRMED SRC08)

- `https://efs.easyrxortho.com` mounted as Windows Network Location / Mac server — a WebDAV-style
  drive over the account's STL files; per-computer login; password change breaks the mount.
- Folders: Patients (practice view), Prescriptions (lab view), Recent.
- Primary use: open STL directly in 3D printer software without browser download.
- EasyRS equivalent: our presigned-URL download + optional desktop agent — the desktop_agent role
  exists in our matrix already.

## Dexis / scanner-side attach (CONFIRMED SRC31)

- Pair Dexis IS Connect with EasyRx; scans sent from IS ScanFlow appear as "Dexis IS Recent
  Scans" → Create Rx with auto-attach; also attachable from Model Source on an existing Rx and
  via patient record Look Up and Attach. Per-doctor Dexis email mapping; admin configures.

## V-05 conclusion for S1b

- Asset model: one immutable blob + derived versions (original → optimized → based) linked by
  parent pointers; Rx references asset, patient aggregates assets — consistent with EasyRS
  `asset` + `asset_reference` design. CONFIRMED at concept level.
- 3D processing profile: {mode, trim_type, trim_margin_mm, base_height_mm, hollow,
  wall_thickness_mm, label_position, label_text_source, preserve_occlusion, extrude_palate,
  pts_trimline, blockout_levels} — S1b keeps profile persistence as a PROVISIONAL task (feature
  AI-015 PARTIAL).
- Not in S1b scope: actual mesh editing (EDIT-*, AI-* processing) — S1b only needs the profile
  schema + storage, not the engines.
