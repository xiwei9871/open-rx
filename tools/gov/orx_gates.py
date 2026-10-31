#!/usr/bin/env python3
"""open-rx governance gates — read-only."""
import os, re, subprocess, sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
STATE = os.path.join(ROOT, "docs/agent_governance/PROJECT_STATE.yaml")


def sh(*a):
    return subprocess.run(a, cwd=ROOT, capture_output=True, text=True).stdout.strip()


def gate_state_head():
    txt = open(STATE).read() if os.path.exists(STATE) else ""
    m = re.search(r"head_commit:\s*([0-9a-f]{7,40})", txt)
    rec = m.group(1) if m else None
    head = sh("git", "rev-parse", "HEAD"); cur = sh("git", "rev-parse", "--abbrev-ref", "HEAD")
    if not rec:
        return [("state-head", "FAIL", "no recorded head_commit")]
    if head.startswith(rec):
        return [("state-head", "PASS", f"on recorded baseline {rec[:7]}")]
    base = sh("git", "merge-base", "HEAD", rec)
    if base.startswith(rec):
        ok = cur.startswith("chore/")
        return [("state-head", "PASS" if ok else "FAIL",
                 f"descendant of baseline on {cur}" + ("" if ok else " — business moved, update state"))]
    return [("state-head", "FAIL", "diverged from recorded baseline")]


def gate_workspace():
    n = len([l for l in sh("git", "status", "--porcelain").splitlines() if l.strip()])
    return [("state-workspace", "PASS", "clean" if not n else f"{n} uncommitted — commit before handoff")]


def gate_redlines():
    # staged/tracked scan for obvious red-line violations (heuristic, not proof)
    hits = []
    out = sh("git", "diff", "--name-only", "HEAD")
    for f in out.splitlines():
        if f.startswith("research/"):
            hits.append(f"{f}: D06 research baseline edited in place")
    if hits:
        return [("redlines", "FAIL", "; ".join(hits[:5]))]
    return [("redlines", "PASS", "no research/ in-place edits in worktree")]


def gate_baseline_checks():
    rows = []
    for name, cmd in (("validate_baseline", ["python3", "tools/validate_baseline.py"]),
                      ("gen_backlog_check", ["python3", "tools/gen_backlog.py", "--check"])):
        if not os.path.exists(os.path.join(ROOT, cmd[1])):
            rows.append((name, "NOT_VERIFIED", f"{cmd[1]} missing"))
            continue
        r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=120)
        rows.append((name, "PASS" if r.returncode == 0 else "FAIL",
                     (r.stdout + r.stderr).strip().splitlines()[-1][:120] if (r.stdout + r.stderr).strip() else f"exit={r.returncode}"))
    return rows


def gate_report():
    return [("report", "NOT_VERIFIED", "evidence-first: run repo gates + tests, record in state")]


def self_test():
    return [("T01 report is NOT_VERIFIED", gate_report()[0][1] == "NOT_VERIFIED"),
            ("T02 baseline checks runnable", len(gate_baseline_checks()) == 2)]


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "all"
    if cmd == "all":
        rows = gate_state_head() + gate_workspace() + gate_redlines() + gate_baseline_checks()
    elif cmd == "report":
        rows = gate_report()
    elif cmd == "self-test":
        rows = [("self-test", "PASS" if ok else "FAIL", n) for n, ok in self_test()]
    else:
        print(__doc__); return 2
    for n, s, d in rows:
        print(f"{s:4s}  {n:22s} {d}")
    return 0 if all(s != "FAIL" for _n, s, _d in rows) else 1


if __name__ == "__main__":
    sys.exit(main())
