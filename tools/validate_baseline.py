#!/usr/bin/env python3
"""Stage A baseline validator.

Mechanical checks over the research baseline and the generated Stage A
artifacts. Stdlib only so it runs anywhere (CI, dev machines, agents).

Usage:
    python3 tools/validate_baseline.py            # run all checks
    python3 tools/validate_baseline.py --update-hashes   # re-pin research hashes

Exit code 0 = PASS, 1 = FAIL. Prints a per-check report.
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESEARCH = ROOT / "research"
DOCS = ROOT / "docs"
FEATURE_CSV = RESEARCH / "easyrx_feature_inventory_v1.csv"
SOURCE_CSV = RESEARCH / "easyrx_source_index_v1.csv"
INVENTORY_JSON = RESEARCH / "easyrx_inventory_v1.json"
HASH_FILE = DOCS / "audit" / "research-sha256.txt"
TRACE_CSV = DOCS / "backlog" / "feature-traceability.csv"
TASKS_JSON = DOCS / "backlog" / "tasks.json"
DISPO_CSV = DOCS / "backlog" / "feature-disposition.csv"

VALID_EVIDENCE = {"D1", "D2", "S", "T"}
VALID_PHASES = {"MVP", "P1", "P2", "P3"}
VALID_COMPLEXITY = {"低", "中", "高", "极高"}
ID_RE = re.compile(r"^(IAM|PAT|RX|FLOW|COM|ASSET|EDIT|AI|LAB|FIN|INT|SAFE)-(\d{3})$")
EXPECTED_MODULES = {
    "机构与权限": "IAM", "患者与病例": "PAT", "处方创建与模板": "RX",
    "Rx状态与工作台": "FLOW", "沟通与协作": "COM", "3D文件与资产": "ASSET",
    "3D人工编辑": "EDIT", "3D自动化与AI": "AI", "实验室与生产MES": "LAB",
    "报价财务与报表": "FIN", "集成与互操作": "INT", "系统保障与合规": "SAFE",
}
REQUIRED_DOCS = [
    "audit/research-baseline-audit.md",
    "architecture/domain-model.md",
    "architecture/data-dictionary.md",
    "architecture/permission-matrix.md",
    "architecture/state-machines.md",
    "architecture/erd.mmd",
    "architecture/system-design.md",
    "architecture/deployment.md",
    "architecture/security-baseline.md",
    "api/openapi.yaml",
    "backlog/epics.md",
    "backlog/tasks.json",
    "backlog/feature-traceability.csv",
    "backlog/dependency-graph.mmd",
    "backlog/mvp-scope.md",
    "backlog/feature-disposition.csv",
    "architecture/authz-test-matrix.md",
    "research/v1.1-verification-checklist.md",
    "planning/mvp-release-plan.md",
    "poc/stl-processing-poc-plan.md",
    "README.md",
]

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, ok, detail))


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def load_features() -> list[dict]:
    with open(FEATURE_CSV, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def load_sources() -> dict[str, dict]:
    with open(SOURCE_CSV, encoding="utf-8-sig", newline="") as f:
        return {r["source_id"]: r for r in csv.DictReader(f)}


def main() -> int:
    if "--update-hashes" in sys.argv:
        lines = [f"{sha256(p)}  {p.name}" for p in sorted(RESEARCH.iterdir()) if p.is_file()]
        HASH_FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"updated {HASH_FILE} ({len(lines)} files)")
        return 0

    # --- 1. research files present + hash-pinned --------------------------------
    files = sorted(p for p in RESEARCH.iterdir() if p.is_file()) if RESEARCH.is_dir() else []
    check("research files present", len(files) == 5, f"{len(files)} files")
    if HASH_FILE.exists():
        pinned = {}
        for line in HASH_FILE.read_text().splitlines():
            if line.strip():
                h, name = line.split(None, 1)
                pinned[name.strip()] = h
        drift = [p.name for p in files if pinned.get(p.name) != sha256(p)]
        missing = set(pinned) - {p.name for p in files}
        check("research hashes pinned & unchanged", not drift and not missing,
              f"drift={drift} missing={sorted(missing)}")
    else:
        check("research hashes pinned & unchanged", False, "docs/audit/research-sha256.txt missing")

    rows = load_features()
    inv = json.loads(INVENTORY_JSON.read_text(encoding="utf-8"))
    sources = load_sources()

    # --- 2. CSV <-> JSON parity ---------------------------------------------------
    items = {i["id"]: i for i in inv.get("items", [])}
    check("CSV row count = 167", len(rows) == 167, str(len(rows)))
    check("JSON item count = 167", len(items) == 167, str(len(items)))
    mism = []
    for r in rows:
        it = items.get(r["id"])
        if not it:
            mism.append((r["id"], "missing in JSON"))
            continue
        for k in ("module", "feature", "evidence", "phase", "complexity", "source_ids",
                  "source_urls", "missing_or_risk", "acceptance", "implementation_status"):
            if str(it.get(k, "")).strip() != str(r.get(k, "")).strip():
                mism.append((r["id"], k))
    check("CSV<->JSON field parity", not mism, f"{len(mism)} mismatches {mism[:5]}")

    # --- 3. ID structure ----------------------------------------------------------
    ids = [r["id"] for r in rows]
    check("feature IDs unique", len(set(ids)) == len(ids), "")
    bad_fmt = [i for i in ids if not ID_RE.match(i)]
    check("feature ID format", not bad_fmt, str(bad_fmt[:5]))
    wrong_prefix = [r["id"] for r in rows
                    if ID_RE.match(r["id"]) and r["id"].split("-")[0] != EXPECTED_MODULES.get(r["module"], "?")]
    check("ID prefix matches module", not wrong_prefix, str(wrong_prefix[:5]))
    gaps = []
    by_prefix: dict[str, list[int]] = {}
    for i in ids:
        m = ID_RE.match(i)
        if m:
            by_prefix.setdefault(m.group(1), []).append(int(m.group(2)))
    for p, ns in by_prefix.items():
        if sorted(ns) != list(range(1, len(ns) + 1)):
            gaps.append(p)
    check("ID sequences gapless per module", not gaps, str(gaps))
    check("12 modules covered", set(by_prefix) == set(EXPECTED_MODULES.values()) - {"SAFE"} | {"SAFE"},
          f"{len(by_prefix)} prefixes")

    # --- 4. enum fields -------------------------------------------------------------
    bad = [(r["id"], "evidence", r["evidence"]) for r in rows if r["evidence"] not in VALID_EVIDENCE]
    bad += [(r["id"], "phase", r["phase"]) for r in rows if r["phase"] not in VALID_PHASES]
    bad += [(r["id"], "complexity", r["complexity"]) for r in rows if r["complexity"] not in VALID_COMPLEXITY]
    check("enum fields valid", not bad, str(bad[:5]))
    empt = [(r["id"], f) for r in rows for f in
            ("module", "feature", "missing_or_risk", "acceptance", "implementation_status")
            if not r[f].strip()]
    check("required fields non-empty", not empt, str(empt[:5]))
    dup = [n for n in {r["feature"] for r in rows}
           if sum(1 for r in rows if r["feature"] == n) > 1]
    check("no duplicate feature names", not dup, str(dup[:5]))

    # --- 5. source references ---------------------------------------------------------
    idx_ids = set(sources)
    prob = []
    for r in rows:
        ids_ = [s.strip() for s in r["source_ids"].split(",") if s.strip()]
        urls = [u.strip() for u in r["source_urls"].split(";") if u.strip()]
        if len(ids_) != len(urls):
            prob.append((r["id"], "id/url count"))
            continue
        for sid, url in zip(ids_, urls):
            if sid not in idx_ids:
                prob.append((r["id"], f"unknown source {sid}"))
            elif sid == "SCR":
                if "PRIVATE" not in url:
                    prob.append((r["id"], "SCR row must keep PRIVATE placeholder"))
            elif sources[sid]["url"] != url:
                prob.append((r["id"], f"url mismatch {sid}"))
    check("source ids/urls consistent with index", not prob, str(prob[:5]))

    # --- 6. evidence distribution sanity ----------------------------------------------
    from collections import Counter
    ev = Counter(r["evidence"] for r in rows)
    ph = Counter(r["phase"] for r in rows)
    check("evidence dist = D1:118 D2:23 S:4 T:22",
          ev == Counter({"D1": 118, "T": 22, "D2": 23, "S": 4}), str(dict(ev)))
    check("phase dist = MVP:72 P1:48 P2:39 P3:8",
          ph == Counter({"MVP": 72, "P1": 48, "P2": 39, "P3": 8}), str(dict(ph)))
    s_only = [r["id"] for r in rows if r["evidence"] == "S" and r["source_ids"].strip() != "SCR"]
    check("S-evidence items cite SCR only", not s_only, str(s_only))

    # --- 7. required docs exist ------------------------------------------------------------
    missing_docs = [d for d in REQUIRED_DOCS if not (DOCS / d).exists()]
    missing_docs += [] if (ROOT / "README.md").exists() else ["README.md(top)"]
    check("required docs present", not missing_docs, str(missing_docs))

    # --- 8. backlog consistency -------------------------------------------------------------
    if TASKS_JSON.exists() and TRACE_CSV.exists():
        tasks = json.loads(TASKS_JSON.read_text(encoding="utf-8"))["tasks"]
        task_ids = [t["id"] for t in tasks]
        check("task IDs unique", len(set(task_ids)) == len(task_ids), "")
        task_set = set(task_ids)
        feat_set = set(ids)
        bad_feat_refs, bad_deps, thin = [], [], []
        covered: set[str] = set()
        for t in tasks:
            for f in t.get("feature_ids", []):
                covered.add(f)
                if f not in feat_set:
                    bad_feat_refs.append((t["id"], f))
            for d in t.get("depends_on", []):
                if d not in task_set:
                    bad_deps.append((t["id"], d))
            for field in ("title", "epic", "summary", "goal", "inputs_outputs",
                          "business_rules", "permissions", "error_handling",
                          "acceptance", "tests", "priority"):
                v = t.get(field)
                if not v or (isinstance(v, list) and not all(str(x).strip() for x in v)):
                    thin.append((t["id"], field))
        check("tasks reference known features", not bad_feat_refs, str(bad_feat_refs[:5]))
        check("task deps reference known tasks", not bad_deps, str(bad_deps[:5]))
        check("tasks have all required fields", not thin, str(thin[:8]))
        check("task coverage = all 167 features", covered == feat_set,
              f"missing {sorted(feat_set - covered)[:10]}")

        with open(TRACE_CSV, encoding="utf-8-sig", newline="") as f:
            tr = list(csv.DictReader(f))
        tr_feats = {r["feature_id"] for r in tr}
        tr_tasks_ok = all(r["task_id"] in task_set for r in tr)
        check("traceability covers all 167 features", tr_feats == feat_set,
              f"missing {sorted(feat_set - tr_feats)[:10]}")
        check("traceability task refs valid", tr_tasks_ok, "")
        # every task's features appear in traceability
        tr_pairs = {(r["feature_id"], r["task_id"]) for r in tr}
        missing_pairs = [(t["id"], f) for t in tasks for f in t.get("feature_ids", [])
                         if (f, t["id"]) not in tr_pairs]
        check("traceability == tasks.json mapping", not missing_pairs, str(missing_pairs[:5]))
    else:
        check("backlog files present", False, "tasks.json or feature-traceability.csv missing")

    # --- 8b. feature disposition table (A5 — one primary per feature) ------------
    VALID_PRIMARY = {"CORE", "SIMPLIFY", "MANUAL", "DEFER", "NOT_IN_MVP"}
    if DISPO_CSV.exists():
        with open(DISPO_CSV, encoding="utf-8-sig", newline="") as f:
            dr = list(csv.DictReader(f))
        d_ids = [r["feature_id"] for r in dr]
        check("disposition covers all 167 features", set(d_ids) == set(ids) and len(d_ids) == 167,
              f"{len(d_ids)} rows")
        check("disposition values valid",
              all(r["primary_disposition"] in VALID_PRIMARY for r in dr),
              str([r["feature_id"] for r in dr if r["primary_disposition"] not in VALID_PRIMARY][:5]))
        phase_of = {r["id"]: r["phase"] for r in rows}
        bad_phase = [r["feature_id"] for r in dr
                     if (phase_of[r["feature_id"]] == "MVP") != (r["primary_disposition"] != "NOT_IN_MVP")]
        check("disposition <-> research phase consistent", not bad_phase, str(bad_phase[:5]))
        from collections import Counter as _C
        dc = _C(r["primary_disposition"] for r in dr)
        mvp_total = dc["CORE"] + dc["SIMPLIFY"] + dc["MANUAL"] + dc["DEFER"]
        check("disposition reconciles: MVP-phase = CORE+SIMPLIFY+MANUAL+DEFER = 72",
              mvp_total == 72 and dc["NOT_IN_MVP"] == 95, str(dict(dc)))
        nodetail = [r["feature_id"] for r in dr
                    if r["primary_disposition"] in {"SIMPLIFY", "MANUAL", "DEFER"} and not r["detail"].strip()]
        check("SIMPLIFY/MANUAL/DEFER rows carry detail", not nodetail, str(nodetail[:5]))
    else:
        check("feature-disposition.csv present", False, "run tools/gen_backlog.py")

    # --- 9. openapi + mermaid sanity -----------------------------------------------------------
    oapi = DOCS / "api" / "openapi.yaml"
    if oapi.exists():
        txt = oapi.read_text(encoding="utf-8")
        top = re.findall(r"^([a-zA-Z_-]+):", txt, re.M)
        need = {"openapi", "info", "paths"}
        check("openapi.yaml top-level keys", need <= set(top), str(top))
        check("openapi.yaml declares >=20 paths", txt.count("\n  /") >= 20,
              f"{txt.count(chr(10) + '  /')} paths")
    else:
        check("openapi.yaml exists", False, "")

    for mf in [DOCS / "architecture" / "erd.mmd", DOCS / "backlog" / "dependency-graph.mmd"]:
        if mf.exists():
            first = mf.read_text(encoding="utf-8").lstrip().split("\n", 1)[0]
            ok = first.split()[0] in {"erDiagram", "flowchart", "graph", "stateDiagram-v2", "sequenceDiagram"}
            check(f"mermaid header {mf.name}", ok, first[:40])
        else:
            check(f"mermaid header {mf.name}", False, "missing")

    # --- 10. private-data leak scan ---------------------------------------------------------------
    leaks = []
    for p in list(DOCS.rglob("*")) + [ROOT / "README.md", ROOT / "AGENTS.md"]:
        if p.is_file() and p.suffix in {".md", ".csv", ".json", ".mmd", ".yaml", ".txt"}:
            t = p.read_text(encoding="utf-8", errors="replace")
            if re.search(r"(?i)\b(password|api[_-]?key|secret)\s*[:=]\s*['\"]?\S{8,}", t):
                leaks.append(str(p.relative_to(ROOT)))
    check("no obvious secrets in docs", not leaks, str(leaks))

    # --- report ------------------------------------------------------------------------------
    fails = [r for r in results if not r[1]]
    for name, ok, detail in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"  -- {detail}" if detail else ""))
    print(f"\n{len(results) - len(fails)}/{len(results)} checks passed"
          + (f"; FAILURES: {len(fails)}" if fails else ""))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
