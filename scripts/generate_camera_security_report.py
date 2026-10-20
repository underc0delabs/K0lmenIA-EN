#!/usr/bin/env python3
"""
HTML report (dark mode) of the passive camera security analysis (camera-security.json, from
`npm run camera-security`) and, optionally, of the camera-security-analyst agent's analysis.

Usage:
    python scripts/generate_camera_security_report.py <camera-security.json> <output.html> [--analysis analysis.json]
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


def _card(rec):
    status = rec.get("status")
    tone = {"ok": "ok", "findings": "warn", "failed": "bad"}.get(status, "warn")
    label = {"ok": "No findings", "findings": "With findings", "failed": "Failed"}.get(status, status)
    body = banner(label, tone)
    op = rec.get("open_ports", [])
    if op:
        body += table(["Port", "Service"], [[e(p.get("port")), e(p.get("service"))] for p in op])
    else:
        body += '<div class="cardbody"><p class="muted">No well-known open ports were detected.</p></div>'
    if rec.get("device"):
        d = rec["device"]
        desc = f"{d.get('brand') or ''} {d.get('model') or ''} · firmware {d.get('firmware') or '?'}"
        body += f'<div class="cardbody"><p class="muted">{e(desc)}</p></div>'
    if rec.get("findings"):
        findings = sorted(rec["findings"], key=lambda x: SEV_ORDER.get(x.get("severity"), 9))
        body += table(["Severity", "Detail"], [[level_badge(x.get("severity", "Medium")), e(x.get("text", ""))] for x in findings])
    return section(rec.get("host", "Camera"), body)


def generate(sec_json, output, analysis_json=None):
    data = json.loads(Path(sec_json).read_text(encoding="utf-8"))
    analysis = json.loads(Path(analysis_json).read_text(encoding="utf-8")) if analysis_json and Path(analysis_json).exists() else {}
    hosts = data.get("hosts", [])
    r = data.get("summary", {})
    total_findings = sum(len(h.get("findings", [])) for h in hosts)

    kpis = [("Cameras", str(r.get("total", len(hosts))), ""),
            ("No findings", str(r.get("ok", 0)), "ok" if r.get("ok") else ""),
            ("With findings", str(r.get("with_findings", 0)), "warn" if r.get("with_findings") else ""),
            ("Total findings", str(total_findings), "bad" if total_findings else "")]

    body = ""
    if analysis.get("verdict"):
        body += banner(analysis["verdict"], TONE.get(analysis.get("verdict_tone"), "ok"))
    body += section("Summary", kpi_tiles(kpis) + (f'<div class="cardbody"><p>{e(analysis["summary"])}</p></div>' if analysis.get("summary") else ""))
    body += section("Scope", banner("Passive analysis: ports and services, with no attacks or credential testing. Only cameras in AUTHORIZED_CAMERAS.", "ok"))
    for hst in hosts:
        body += _card(hst)
    if analysis.get("recommendations"):
        rows = [[level_badge(x.get("priority", "Medium")), e(x.get("action", "")), e(x.get("reason", ""))] for x in analysis["recommendations"]]
        body += section("Recommendations", table(["Priority", "Action", "Why"], rows))
    if analysis.get("next_steps"):
        body += section("Next steps", doc_list(analysis["next_steps"]))
    body += missing_info(analysis.get("missing_info"))

    meta_html = meta([("Generated", data.get("generated")), ("Story", data.get("story"))])
    html = page("Camera security", "IP cameras · passive scan", meta_html, body)
    Path(output).write_text(html, encoding="utf-8")
    return output


def main():
    ap = argparse.ArgumentParser(description="Camera security HTML report.")
    ap.add_argument("sec_json")
    ap.add_argument("output")
    ap.add_argument("--analysis", default=None)
    args = ap.parse_args()
    print(generate(args.sec_json, args.output, args.analysis))


if __name__ == "__main__":
    main()
