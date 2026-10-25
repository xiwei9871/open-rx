#!/usr/bin/env python3
"""Generate Stage A backlog artifacts from tools/backlog_tasks.py.

Outputs (all generated — do not hand-edit):
  docs/backlog/tasks.json
  docs/backlog/tasks/EPIC-XX-<slug>.md     (one file per epic)
  docs/backlog/feature-traceability.csv
  docs/backlog/dependency-graph.mmd
  docs/backlog/epics.md
  docs/backlog/mvp-scope.md
  docs/backlog/feature-disposition.csv

--check: regenerate into memory and diff against disk (CI gate).
"""
from __future__ import annotations

import csv
import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
from backlog_tasks import EPICS, TASKS  # noqa: E402
from feature_disposition import disposition_table  # noqa: E402

FEATURE_CSV = ROOT / "research" / "easyrx_feature_inventory_v1.csv"
OUT = ROOT / "docs" / "backlog"
PHASE_ORDER = {"MVP": 0, "P1": 1, "P2": 2, "P3": 3}
SLUG = {
    "EPIC-01": "iam", "EPIC-02": "patient", "EPIC-03": "rx", "EPIC-04": "workflow",
    "EPIC-05": "collaboration", "EPIC-06": "assets", "EPIC-07": "editing",
    "EPIC-08": "automation-ai", "EPIC-09": "lab-mes", "EPIC-10": "finance",
    "EPIC-11": "integrations", "EPIC-12": "security",
}


def load_features() -> dict[str, dict]:
    with open(FEATURE_CSV, encoding="utf-8-sig", newline="") as f:
        return {r["id"]: r for r in csv.DictReader(f)}


def validate_tasks(feats: dict[str, dict]) -> list[str]:
    errs = []
    ids = [t["id"] for t in TASKS]
    if len(ids) != len(set(ids)):
        errs.append("duplicate task ids")
    epic_ids = {e["id"] for e in EPICS}
    task_ids = set(ids)
    covered = set()
    for t in TASKS:
        if t["epic"] not in epic_ids:
            errs.append(f"{t['id']}: unknown epic {t['epic']}")
        for f in t["feature_ids"]:
            if f not in feats:
                errs.append(f"{t['id']}: unknown feature {f}")
            covered.add(f)
        for d in t["depends_on"]:
            if d not in task_ids:
                errs.append(f"{t['id']}: unknown dep {d}")
    missing = set(feats) - covered
    if missing:
        errs.append(f"uncovered features: {sorted(missing)}")
    return errs


def phase_of(t: dict, feats: dict[str, dict]) -> str:
    return min((feats[f]["phase"] for f in t["feature_ids"]), key=lambda p: PHASE_ORDER[p])


def evidence_of(t: dict, feats: dict[str, dict]) -> str:
    evs = sorted({feats[f]["evidence"] for f in t["feature_ids"]}, key="D1D2ST".index)
    return "/".join(evs)


def sources_of(t: dict, feats: dict[str, dict]) -> list[str]:
    seen, out = set(), []
    for f in t["feature_ids"]:
        for s in feats[f]["source_ids"].split(","):
            s = s.strip()
            if s and s not in seen:
                seen.add(s)
                out.append(s)
    return out


def bullets(items) -> str:
    return "\n".join(f"- {i}" for i in items)


def task_md(t: dict, feats: dict[str, dict]) -> str:
    frows = []
    for fid in t["feature_ids"]:
        r = feats[fid]
        frows.append(f"| {fid} | {r['feature']} | {r['evidence']} | {r['phase']} | {r['complexity']} | {r['acceptance']} |")
    deps = ", ".join(t["depends_on"]) or "无"
    oq = bullets(t["open_questions"]) if t["open_questions"] else "- 无"
    return f"""## {t['id']} {t['title']}

| 字段 | 值 |
|---|---|
| Epic | {t['epic']} |
| 优先级 | {t['priority']} |
| 前置依赖 | {deps} |
| 证据等级（覆盖项） | {evidence_of(t, feats)} |
| 关联来源 | {", ".join(sources_of(t, feats))} |

### 功能说明
{t['summary']}

### 业务目标
{t['goal']}

### 覆盖 Feature
| Feature ID | 名称 | 证据 | 阶段 | 复杂度 | 研究验收口径 |
|---|---|---|---|---|---|
{chr(10).join(frows)}

### 输入输出
{t['inputs_outputs']}

### 业务规则
{bullets(t['business_rules'])}

### 权限要求
{t['permissions']}

### 异常处理
{bullets(t['error_handling'])}

### 验收标准
{bullets(t['acceptance'])}

### 测试场景
{bullets(t['tests'])}

### 尚未解决的问题
{oq}
"""


def gen(feats: dict[str, dict]) -> tuple[dict[str, str], list[str]]:
    files: dict[str, str] = {}
    dispo_rows, dispo_errs = disposition_table(feats)

    # tasks.json
    files["tasks.json"] = json.dumps(
        {"version": "stage-a-v1", "epics": EPICS,
         "tasks": [{**{k: v for k, v in t.items()}, "phase_derived": phase_of(t, feats),
                    "sources": sources_of(t, feats)} for t in TASKS]},
        ensure_ascii=False, indent=1) + "\n"

    # per-epic task files
    by_epic: dict[str, list[dict]] = {}
    for t in TASKS:
        by_epic.setdefault(t["epic"], []).append(t)
    epic_name = {e["id"]: e for e in EPICS}
    for e in EPICS:
        ts = by_epic.get(e["id"], [])
        head = f"""# {e['id']} {e['name']}

> 域：{e['domain']} · 任务数：{len(ts)} · 覆盖 Feature：{sum(len(t['feature_ids']) for t in ts)}
> {e['desc']}
> 本文件由 `tools/gen_backlog.py` 生成，勿手改。

"""
        files[f"tasks/{e['id']}-{SLUG[e['id']]}.md"] = head + "\n---\n\n".join(task_md(t, feats) for t in ts)

    # traceability csv
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["feature_id", "task_id", "epic_id", "feature_phase", "evidence", "task_priority", "source_ids", "note"])
    f2t = {}
    for t in TASKS:
        for f in t["feature_ids"]:
            f2t.setdefault(f, []).append(t["id"])
    for fid in sorted(f2t, key=lambda x: (x.split("-")[0], int(x.split("-")[1]))):
        r = feats[fid]
        for tid in f2t[fid]:
            t = next(x for x in TASKS if x["id"] == tid)
            note = "DEFERRED_IN_TASK" if PHASE_ORDER[r["phase"]] > PHASE_ORDER[t["priority"]] else ""
            w.writerow([fid, tid, t["epic"], r["phase"], r["evidence"], t["priority"], r["source_ids"], note])
    files["feature-traceability.csv"] = buf.getvalue()

    # feature disposition csv — exactly one primary disposition per feature
    if not dispo_errs:
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["feature_id", "phase", "primary_disposition", "labels", "detail"])
        for r in sorted(dispo_rows, key=lambda x: (x["feature_id"].split("-")[0],
                                                 int(x["feature_id"].split("-")[1]))):
            w.writerow([r["feature_id"], r["phase"], r["primary_disposition"],
                        r["labels"], r["detail"]])
        files["feature-disposition.csv"] = buf.getvalue()

    # dependency graph
    lines = ["flowchart LR"]
    epic_of = {t["id"]: t["epic"] for t in TASKS}
    for t in TASKS:
        for d in t["depends_on"]:
            lines.append(f"  {d}[{d}] --> {t['id']}[{t['id']}]")
    lines.append("")
    for e in EPICS:
        members = [t["id"] for t in TASKS if t["epic"] == e["id"]]
        if members:
            lines.append(f"  subgraph {e['id']}[{e['id']} {e['name']}]")
            for m in members:
                lines.append(f"    {m}")
            lines.append("  end")
    files["dependency-graph.mmd"] = "\n".join(lines) + "\n"

    # epics.md
    rows = ["# Epics — Stage A 开发任务分组", "",
            "> 生成自 `tools/backlog_tasks.py`。Task 可跨 Epic 引用 Feature；Epic 归属按任务主体。",
            "", "| Epic | 名称 | 域 | 任务数 | Feature 覆盖 | 任务文件 |",
            "|---|---|---|---:|---:|---|"]
    for e in EPICS:
        ts = by_epic.get(e["id"], [])
        nfeat = sum(len(t["feature_ids"]) for t in ts)
        rows.append(f"| {e['id']} | {e['name']} | {e['domain']} | {len(ts)} | {nfeat} | [tasks/{e['id']}-{SLUG[e['id']]}.md](tasks/{e['id']}-{SLUG[e['id']]}.md) |")
    rows += ["", "## 依赖概览", "", "```mermaid", files["dependency-graph.mmd"].rstrip(), "```", ""]
    files["epics.md"] = "\n".join(rows)

    # mvp-scope.md
    mvp_tasks = [t for t in TASKS if t["priority"] == "MVP"]
    from collections import Counter
    dispo_counts = Counter(r["primary_disposition"] for r in dispo_rows)
    lines = ["# MVP 任务范围（任务级视图）", "",
             "> 与 `docs/planning/mvp-release-plan.md` 配套：后者解释**为什么**是这些，本文列出任务级事实。",
             "> `DEFERRED_IN_TASK` = 任务内被推迟的 Feature（研究阶段 > MVP）。",
             "> Feature 级唯一处置结论见 `feature-disposition.csv`（本目录，机器可校验）。",
             "", f"MVP 任务数：**{len(mvp_tasks)}/{len(TASKS)}**；覆盖 Feature（含被推迟部分）："
             f"**{sum(len(t['feature_ids']) for t in mvp_tasks)}**。",
             "", "## Feature 级处置统计（167 项，口径统一）", "",
             "| 处置 | 数量 | 含义 |", "|---|---:|---|",
             f"| CORE | {dispo_counts['CORE']} | MVP 内按验收口径实现 |",
             f"| SIMPLIFY | {dispo_counts['SIMPLIFY']} | MVP 内简化交付（削减点见 CSV detail） |",
             f"| MANUAL | {dispo_counts['MANUAL']} | MVP 内以人工操作替代 |",
             f"| DEFER | {dispo_counts['DEFER']} | 研究-MVP 项移出首个闭环（落点见 CSV） |",
             f"| NOT_IN_MVP | {dispo_counts['NOT_IN_MVP']} | 研究阶段 P1/P2/P3，本就不属 MVP 候选 |",
             "",
             "对账：研究-MVP 72 = CORE+SIMPLIFY+MANUAL+DEFER；NOT_IN_MVP = 95（48+39+8）。",
             "旧口径 55 核心/5 延期/3 手工 把 KEEP-SEC 混入 CORE、把两个部分交付项算作延期、",
             "并把两个 P1 期手工项计入——本表已统一为 Feature 级唯一主处置。",
             "", "| Task | 标题 | Epic | Feature | 其中 >MVP 的 Feature |", "|---|---|---|---|---|"]
    for t in mvp_tasks:
        deferred = [f for f in t["feature_ids"] if PHASE_ORDER[feats[f]["phase"]] > 0]
        lines.append(f"| {t['id']} | {t['title']} | {t['epic']} | {len(t['feature_ids'])} | {', '.join(deferred) or '—'} |")
    lines += ["", "## 不在 MVP 任务中的高价值项", "",
              "P1+ 任务整体不在 MVP：3D 编辑链（EPIC-07）、MES 深化（部分 EPIC-09）、财务（EPIC-10）、",
              "厂商集成（EPIC-11 大部，除 TASK-0047 公开 API）与 AI 线（EPIC-08）。详见 mvp-release-plan。", ""]
    files["mvp-scope.md"] = "\n".join(lines)
    return files, dispo_errs


def main() -> int:
    feats = load_features()
    errs = validate_tasks(feats)
    files, dispo_errs = gen(feats)
    errs += dispo_errs
    if errs:
        for e in errs:
            print("ERR", e)
        return 1
    check = "--check" in sys.argv
    drift = []
    for rel, content in files.items():
        p = OUT / rel
        if check:
            if not p.exists() or p.read_bytes() != content.encode("utf-8"):
                drift.append(rel)
        else:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
    if check:
        if drift:
            print("DRIFT:", drift)
            return 1
        print(f"OK: {len(files)} generated files in sync")
    else:
        print(f"wrote {len(files)} files")
        for k in sorted(files):
            print(" ", k)
    return 0


if __name__ == "__main__":
    sys.exit(main())
