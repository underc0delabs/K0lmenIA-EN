#!/usr/bin/env python3
"""
Generates the image quality HTML report (dashboard, dark mode) from the OpenCV evaluation
(quality.json, from `npm run image-quality`) and, optionally, from the vision analysis of the
image-quality-analyst agent (dirty lens, moved camera, backlight, IR).

Usage:
    python scripts/generate_quality_report.py <quality.json> <output.html> [--analysis analysis.json]
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
    label = {"ok": "OK", "findings": "With findings", "failed": "Failed"}.get(status, status)
    m = rec.get("metrics", {})
    body = banner(label, tone)
    if rec.get("screenshot"):
        body += (f'<div class="cardbody"><img src="{e(rec["screenshot"])}" alt="Screenshot" '
                 f'style="max-width:100%;border-radius:12px"></div>')
    if m:
        rows = [["Resolution", e(f'{m.get("width")}x{m.get("height")}') if m.get("width") else "—"],
                ["Average brightness", e(m.get("brightness"))],
                ["Sharpness (Laplacian)", e(m.get("sharpness"))]]
        if m.get("freeze_diff") is not None:
            rows.append(["Difference (freeze)", e(m.get("freeze_diff"))])
        if m.get("reference_diff") is not None:
            rows.append(["Difference vs. reference", e(m.get("reference_diff"))])
        body += table(["Metric", "Value"], rows)
    if rec.get("findings"):
        found = sorted(rec["findings"], key=lambda x: SEV_ORDER.get(x.get("severity"), 9))
        body += table(["Severity", "Detail"], [[level_badge(x.get("severity", "Medium")), e(x.get("text", ""))] for x in found])
    if rec.get("review_with_vision"):
        body += ('<div class="cardbody"><p class="muted">Review with judgment (vision): '
                 + e(", ".join(rec["review_with_vision"])) + "</p></div>")
    return section(rec.get("source", "Camera"), body)


def generate(quality_json, output, analysis_json=None):
    data = json.loads(Path(quality_json).read_text(encoding="utf-8"))
    analysis = json.loads(Path(analysis_json).read_text(encoding="utf-8")) if analysis_json and Path(analysis_json).exists() else {}
    sources = data.get("sources", [])
    r = data.get("summary", {})

    kpis = [("Cameras", str(r.get("total", len(sources))), ""),
            ("OK", str(r.get("ok", 0)), "ok" if r.get("ok") else ""),
            ("With findings", str(r.get("with_findings", 0)), "warn" if r.get("with_findings") else ""),
            ("Failed", str(r.get("failed", 0)), "bad" if r.get("failed") else "")]

    body = ""
    if analysis.get("verdict"):
        body += banner(analysis["verdict"], TONE.get(analysis.get("verdict_tone"), "ok"))
    body += section("Summary", kpi_tiles(kpis) + (f'<div class="cardbody"><p>{e(analysis["summary"])}</p></div>' if analysis.get("summary") else ""))
    for f in sources:
        body += _card(f)
    if analysis.get("recommendations"):
        rows = [[level_badge(x.get("priority", "Medium")), e(x.get("action", "")), e(x.get("reason", ""))] for x in analysis["recommendations"]]
        body += section("Recommendations", table(["Priority", "Action", "Why"], rows))
    if analysis.get("next_steps"):
        body += section("Next steps", doc_list(analysis["next_steps"]))
    body += missing_info(analysis.get("missing_info"))

    meta_html = meta([("Generated", data.get("generated")), ("Story", data.get("story"))])
    html = page("Image quality", "Cameras · vision + OpenCV", meta_html, body)
    Path(output).write_text(html, encoding="utf-8")
    return output


def main():
    ap = argparse.ArgumentParser(description="Image quality HTML report.")
    ap.add_argument("quality_json")
    ap.add_argument("output")
    ap.add_argument("--analysis", default=None)
    args = ap.parse_args()
    print(generate(args.quality_json, args.output, args.analysis))


if __name__ == "__main__":
    main()
