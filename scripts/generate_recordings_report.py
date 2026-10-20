#!/usr/bin/env python3
"""
HTML report (dark mode) of the ONVIF recording verifier (recordings.json, from
`npm run recordings`) and, optionally, of the recording-verifier agent's analysis.

Usage:
    python scripts/generate_recordings_report.py <recordings.json> <output.html> [--analysis analysis.json]
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _report_styles import (page, meta, section, kpi_tiles, banner, table, doc_list,
                              level_badge, missing_info, e)

SEV_ORDER = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
TONE = {"ok": "ok", "warn": "warn", "bad": "bad"}


def generate(rec_json, output, analysis_json=None):
    data = json.loads(Path(rec_json).read_text(encoding="utf-8"))
    analysis = json.loads(Path(analysis_json).read_text(encoding="utf-8")) if analysis_json and Path(analysis_json).exists() else {}
    res = data.get("result", {})
    summary = res.get("summary", {})

    status = res.get("status", "—")
    tone = {"ok": "ok", "findings": "warn", "failed": "bad"}.get(status, "warn")
    kpis = [("Status", {"ok": "OK", "findings": "With findings", "failed": "Failed"}.get(status, status), tone),
            ("Recordings", str(summary.get("count", "—")), ""),
            ("Days covered", str(summary.get("covered_days", "—")), ""),
            ("Expected retention", f'{data.get("expected_retention")} days' if data.get("expected_retention") else "—", "")]

    body = ""
    if analysis.get("verdict"):
        body += banner(analysis["verdict"], TONE.get(analysis.get("verdict_tone"), "ok"))
    body += section("Summary", kpi_tiles(kpis) + (f'<div class="cardbody"><p>{e(analysis["summary"])}</p></div>' if analysis.get("summary") else ""))

    if not res.get("supported", True):
        body += section("ONVIF support", banner("The camera did not answer the recording service over ONVIF (Search). It may not support it; verify through the NVR's API.", "warn"))

    if summary:
        rows = [["From", e(summary.get("from") or "—")], ["Until", e(summary.get("until") or "—")],
                ["Count", e(summary.get("count"))], ["Days covered", e(summary.get("covered_days"))]]
        body += section("Recorded range", table(["Field", "Value"], rows))

    recordings = res.get("recordings", [])
    if recordings:
        rows = []
        for g in recordings:
            tracks = ", ".join(f'{t.get("type") or "?"} ({(t.get("from") or "?")[:16]}→{(t.get("until") or "?")[:16]})' for t in g.get("tracks", []))
            rows.append([e(g.get("token") or "—"), e(tracks or "—")])
        body += section("Recordings", table(["Token", "Tracks (range)"], rows))

    findings = sorted(res.get("findings", []), key=lambda x: SEV_ORDER.get(x.get("severity"), 9))
    if findings:
        body += section("Findings", table(["Severity", "Detail"], [[level_badge(x.get("severity", "Medium")), e(x.get("text", ""))] for x in findings]), sub=f"{len(findings)} in total")
    else:
        body += section("Findings", banner("No findings: recording and retention are OK.", "ok"))

    if analysis.get("recommendations"):
        rows = [[level_badge(x.get("priority", "Medium")), e(x.get("action", "")), e(x.get("reason", ""))] for x in analysis["recommendations"]]
        body += section("Recommendations", table(["Priority", "Action", "Why"], rows))
    if analysis.get("next_steps"):
        body += section("Next steps", doc_list(analysis["next_steps"]))
    body += missing_info(analysis.get("missing_info"))

    meta_html = meta([("Generated", data.get("generated")), ("Story", data.get("story")),
                      ("Host", f'{res.get("host")}:{res.get("port")}')])
    html = page("Recordings", "NVR · ONVIF Recording", meta_html, body)
    Path(output).write_text(html, encoding="utf-8")
    return output


def main():
    ap = argparse.ArgumentParser(description="Recordings HTML report.")
    ap.add_argument("rec_json")
    ap.add_argument("output")
    ap.add_argument("--analysis", default=None)
    args = ap.parse_args()
    print(generate(args.rec_json, args.output, args.analysis))


if __name__ == "__main__":
    main()
