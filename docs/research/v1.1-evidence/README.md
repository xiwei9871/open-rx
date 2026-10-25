# V1.1 Evidence Dossiers

Verification date: 2026-02 (research session on `devin/easyrs-v11-evidence`).
Method: every public URL in `research/easyrx_source_index_v1.csv` was fetched and read in full
body text. Index/category pages were read to inventory their article lists — they register
feature existence, not behavioral detail. Supplementary articles (SRC-D1..D7) were discovered
via those indexes and read in full; they are registered in `v1.1-source-audit.csv` alongside
the original 36.

Status legend used across all V1.1 artifacts:

| Status | Meaning |
|---|---|
| `CONFIRMED` | Supported by directly read official text (this session). |
| `PARTIAL` | Some aspect verified; remaining detail undocumented or only directory-snippet level. |
| `PROVISIONAL` | EasyRS-owned design proposal. MUST NOT be presented as EasyRx fact. |
| `UNKNOWN` | Not established by any read source. |
| `CONFLICT` | Sources disagree, or existing EasyRS design contradicts evidence. |

Directory listings and article titles alone never justify `CONFIRMED` for behavior detail.
Private user screenshots (`SCR`) were not accessed and are excluded from this repository.

## Dossier index

| File | Verification items | Primary sources |
|---|---|---|
| `rx-lifecycle.md` | V-01 create form, workspace, save/submit; V-02 check-in/unsubmit/ship | SRC01, SRC02, SRC03, SRC24, SRC25, SRC26, D6 |
| `accounts-and-permissions.md` | V-03 roles, user accounts, clinical staff | SRC01, SRC-D4, SRC-D5, SRC-D1, SRC29 |
| `parts-templates-library.md` | V-04 parts/appliances/templates/catalog | SRC01, SRC02, SRC25, SRC33, SRC36 |
| `notifications-approvals.md` | V-08 notify levels, approval signatures | SRC23, SRC-D7, SRC02 |
| `shipping-receiving.md` | V-07 ship/received/delivered, ship-date automation | SRC03, SRC27, SRC02, SRC18 |
| `connections-and-sharing.md` | V-14 connection lifecycle, sharing grants | SRC-D1, SRC-D3, SRC-D4, SRC03 |
| `files-and-3d.md` | V-05 assets, 3D view/edit, AI services, EasyFS | SRC04, SRC05, SRC06, SRC07, SRC08, SRC31, SRC35 |
| `lab-side-workflows.md` | V-13 written check-in, VisualDLP MES | SRC-D2, SRC09, SRC10, SRC11, SRC17..SRC22 |
| `billing-and-pricing.md` | per-script billing, price lists, pay-for-practice | SRC16, SRC17, SRC24, SRC-D1, SRC-D2 |
| `inhouse-aligner-idb.md` | V-11 in-house lab, aligner/IDB forms, Invisalign tracking | SRC02, SRC25, SRC26, SRC15 |
| `patients-integrations.md` | V-06 patient linkage, scanner/PMS integrations | SRC30, SRC31, SRC14, SRC01 |
| `index-and-terms.md` | index pages, license agreement, ToS, release notes | SRC12..SRC22, SRC28, SRC29, SRC34, SRC35, SRC36 |

Everything under this directory is public-source research notes. No EasyRx proprietary
assets, product artwork, or private-account data are reproduced here.
