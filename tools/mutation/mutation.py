#!/usr/bin/env python3
"""
Read-only reader of a mutation testing report (standard Stryker / mutation-testing-report-schema format):
computes the mutation score, the surviving mutants and the score per file.

Usage (from the repo root, after running the project's mutation tool):
    python tools/mutation/mutation.py --report reports/mutation/mutation.json [--threshold 70] [--output ...]

What it does:
- Parses the Stryker JSON (StrykerJS, Stryker.NET and those that export to that schema) and aggregates by status
  (Killed, Survived, Timeout, NoCoverage…), computes the global and per-file **mutation score**, and lists the
  **mutants that survived** (the ones your tests did not detect) and the code **without coverage**.
- With --threshold it flags the files below the minimum score.

It does not run the mutation (the mutation-analyst agent does that with the project's tool: Stryker for
JS/TS/C#, mutmut/cosmic-ray for Python, PITest for JVM, Infection for PHP). It only reads the report.
"""
import argparse
import json
import sys
from pathlib import Path

DETECTED = ("Killed", "Timeout")
VALID = ("Killed", "Timeout", "Survived", "NoCoverage")


def _score(det, val):
    return round(det / val * 100, 1) if val else None


def parse_stryker(data):
    """Summary of the Stryker report. Pure and testable."""
    files = (data or {}).get("files") or {}
    by_status, survived, by_file = {}, [], {}
    for file, info in files.items():
        mutants = info.get("mutants") or []
        for m in mutants:
            st = m.get("status")
            by_status[st] = by_status.get(st, 0) + 1
            if st in ("Survived", "NoCoverage"):
                survived.append({"file": file, "mutator": m.get("mutatorName"),
                                 "line": ((m.get("location") or {}).get("start") or {}).get("line"), "status": st})
        det = sum(1 for m in mutants if m.get("status") in DETECTED)
        val = sum(1 for m in mutants if m.get("status") in VALID)
        by_file[file] = {"score": _score(det, val),
                                "survived": sum(1 for m in mutants if m.get("status") in ("Survived", "NoCoverage")),
                                "total": len(mutants)}
    det = sum(v for k, v in by_status.items() if k in DETECTED)
    val = sum(v for k, v in by_status.items() if k in VALID)
    return {"score": _score(det, val), "by_status": by_status, "survived": survived,
            "by_file": by_file, "total": sum(by_status.values())}


def below_threshold(by_file, threshold):
    """Files with a score below the threshold. Pure and testable."""
    return sorted([a for a, v in (by_file or {}).items() if v.get("score") is not None and v["score"] < threshold],
                  key=lambda a: by_file[a]["score"])


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass
    ap = argparse.ArgumentParser(description="Reads a mutation testing report (Stryker JSON), read-only.")
    ap.add_argument("--report", default="reports/mutation/mutation.json", help="path of the Stryker JSON")
    ap.add_argument("--threshold", type=float, default=70.0, help="minimum score per file")
    ap.add_argument("--output", default="")
    args = ap.parse_args(argv)
    rep = Path(args.report)
    if not rep.exists():
        print(f"[mutation] Report not found: {rep}. First run the project's mutation tool "
              f"(Stryker/mutmut/PITest) and point --report to its JSON.", file=sys.stderr)
        return 2
    try:
        data = json.loads(rep.read_text(encoding="utf-8"))
    except ValueError as ex:
        print(f"[mutation] The report is not valid JSON: {ex}", file=sys.stderr)
        return 2
    inv = parse_stryker(data)
    inv["below_threshold"] = below_threshold(inv["by_file"], args.threshold)
    inv["threshold"] = args.threshold
    text = json.dumps(inv, ensure_ascii=False, indent=2)
    if args.output:
        p = Path(args.output)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        print(f"[mutation] Data in {p}", file=sys.stderr)
    print(text)
    print(f"[mutation] score={inv['score']}% · {len(inv['survived'])} surviving mutant(s) · "
          f"{len(inv['below_threshold'])} file(s) below {args.threshold}%.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
