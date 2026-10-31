# Project context — open-rx / easyrs

Open-Rx: clean-room reimplementation planning of an EasyRx-style
orthodontic lab workflow (research + MVP backlog). Heavy spec/audit docs;
business app code early-stage.

## Key paths
- `research/` hash-pinned baseline (never edit in place — D06)
- `tools/backlog_tasks.py` → generates `docs/backlog/` (never edit output)
- `tools/validate_baseline.py`, `tools/gen_backlog.py` — pre-commit gates
- `docs/audit/audit-flags.csv` — evidence verification ledger
- `docs/agent_governance/` — this continuity layer

## Verify
`python3 tools/gov/orx_gates.py all` then repo gates:
`python3 tools/validate_baseline.py && python3 tools/gen_backlog.py --check`
