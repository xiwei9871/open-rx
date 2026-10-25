# Dossier — Patients & integrations (V-06)

Sources read in full: SRC30, SRC31, SRC14 (index). Supporting: SRC01, SRC-D4.

## Patient behaviors (CONFIRMED SRC01, SRC30)

- Patients created via Create Rx inline (name + optional ID/DOB) OR via Patients tab Add Patient.
- PMS launch flow: integration passes patient info → EasyRx finds-or-adds → Edit Patient screen
  (history, create Rx, attach STL). Unlinked records: manual `[Select Patient]` + `[Connect]`,
  or `[Create]` new.
- DOB recommended for same-name disambiguation.
- Patient record holds: Rx history, attached files (Rx attachments also land here), and —
  for lab-created histories — written check-ins visible if the practice later joins (SRC-D2).

## Integration catalog (CONFIRMED existence via SRC14 index + reads)

Practice-management (Standard/Premium plans): Dolphin (Imaging + Management + Treatment Card
comments on Rx events), Ortho2 Edge, Cloud9, TOPSortho, topsOrtho, Open Dental, EagleSoft,
Focus Ortho, Wave Ortho, Oasys, GreyFinch (in development, SRC34).
Scanners: iTero (v2 API; auto-attach; Case Order ID; disconnect clears scans; failed-export bulk
retry is an internal SuperAdmin tool), TRIOS (Recent Scans tab; create Rx from scan), Medit Link
(45-day scan history on first connect, SRC34), Dexis, 3Disc, Alliedstar, Planmeca Romexis,
3M OCP, OrthoAnalyzer auto-export.
Lab systems: Magic Touch (Rx + scans flow into MT), Xero.
Printers/software: FormLabs Preform, NextDent Sprint, MiiCraft MiiUtility, MoonRay RayWare,
EnvisionTEC Perfactory, Uniz, Nexa — "open based STL in slicer" pattern.
File access: EasyFS mount (SRC08); EasyRx Digitize impression→STL service (SRC14 index).

## V-06 conclusion for S1b

- EasyRS keeps integrations OUT of S1b scope; patient `external_id` + `source` fields already
  exist — document them as the integration seam.
- Duplicate-patient UX guidance (suggest-on-surname + DOB) is CONFIRMED behavior worth mirroring;
  our patient dedup endpoint stays.
