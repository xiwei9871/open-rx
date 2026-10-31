# Decision register

Distilled from `AGENTS.md` (binding contract) — see it for full text.
ACTIVE entries block conflicting requests.

| ID | Decision | Status |
| --- | --- | --- |
| D01 | Feature ID (`IAM/PAT/RX/FLOW/COM/ASSET/EDIT/AI/LAB/FIN/INT/SAFE-NNN`) is the sole tracking key; every PR/task cites IDs | **ACTIVE** |
| D02 | Evidence discipline: D1 official / D2 TOC / S private screenshot / T proposal. T never described as existing EasyRx feature; unverified stays UNKNOWN/OPEN | **ACTIVE** |
| D03 | No "done without tests": tasks/*.md acceptance + E2E-01~16 are part of DoD | **ACTIVE** |
| D04 | Zero PHI: no real patient data, identifying screenshots, clinical STL, secrets — ever committed | **ACTIVE** |
| D05 | Clean-room: no EasyRx code/assets/500+ part library/weights copied; deps ≥7d old, license-audited (ADR-0007) | **ACTIVE** |
| D06 | `research/` is a hash-pinned baseline — new versions, never in-place edits; `docs/backlog` artifacts are generated (edit `tools/backlog_tasks.py`) | **ACTIVE** |
| D07 | Pre-commit gates: `validate_baseline.py` && `gen_backlog.py --check` must be green | **ACTIVE** |
| D08 | Agent delivery must cite branch, commit, file list, verification evidence | **ACTIVE** |
