#!/usr/bin/env python3
"""Test management in Xray (Cloud or Server/DC), QMetry for Jira (QTM4J) and AIO Tests.

Same commands for every tool; which one is used comes from MANAGEMENT_TOOL
(root .env) or from --tool. Every command prints a JSON with the result.

    python scripts/management/management.py [--tool X] [--dry-run] <command> [options]

Commands:
  folder               --path "/US-001 Signup"
  upload-cases         --source <cases.xlsx | scenarios.feature> --folder "/US-001 Signup"
                       [--story PROJ-12] [--ids TC-001,TC-002] [--trace US-001]
  link                 --story PROJ-12 (--cases PROJ-45,PROJ-46 | --cycle PROJ-60)
  create-cycle         --name "US-001 Sprint 5" [--description ...] [--story PROJ-12]
                       [--cases PROJ-45,PROJ-46 | --trace US-001 [--ids TC-001,...]]
  add-to-cycle         --cycle PROJ-60 (--cases PROJ-45,... | --trace US-001 [--ids ...])
  extract-results      --report tools/k0lmena/reports/web/cucumber-report.json
                       [--output output/management/results-<date>.json]
  publish-results      --cycle PROJ-60 --results <results.json> [--trace US-001]
                       [--no-video]

Tools: xray-cloud | xray-dc | qtm4j | aio
--trace <name>: traceability file output/management/<name>-<tool>.json
(which TC-XXX is which key). Defaults to the value of --story.
--dry-run: shows the requests without sending them (to review before touching the real tool).
"""
import argparse
import datetime as dt
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from common import (MANAGEMENT_DIR, ROOT, ManagementError, Traceability, load_env, env,  # noqa: E402
                    output)
import readers  # noqa: E402

TOOLS = ("xray-cloud", "xray-dc", "qtm4j", "aio")


def create_adapter(name, dry_run):
    project = env("MANAGEMENT_PROJECT")
    if name == "xray-cloud":
        from adapters.xray_cloud import XrayCloud as Cls
    elif name == "xray-dc":
        from adapters.xray_dc import XrayDC as Cls
    elif name == "qtm4j":
        from adapters.qtm4j import QTM4J as Cls
    elif name == "aio":
        from adapters.aio import AIO as Cls
    else:
        raise ManagementError(f"Unknown tool '{name}'. Options: {', '.join(TOOLS)}.")
    return Cls(project, dry_run=dry_run)


def folder_path(value):
    """Normalizes the folder path to "/A/B". Git Bash converts arguments that start with "/"
    into Windows paths (C:/Program Files/Git/...): this is detected and you are asked to write it without the leading slash."""
    if re.match(r"^[A-Za-z]:[\\/]", value or ""):
        raise ManagementError(f"The folder arrived as a Windows path ('{value}'): Git Bash converts paths that "
                              "start with '/'. Write it without the leading slash, e.g. --folder \"US-001 Signup/Manual\".")
    parts = [p.strip() for p in re.split(r"[\\/]", value or "") if p.strip()]
    if not parts:
        raise ManagementError("The folder path is empty.")
    return "/" + "/".join(parts)


def split_list(value):
    return [v.strip() for v in (value or "").split(",") if v.strip()]


def cases_from_args(args, trace, adapter):
    """Cases (dicts with key/id) from --cases or from the traceability (+ --ids)."""
    if args.cases:
        return [{"key": k, "id": None} for k in split_list(args.cases)]
    if not trace:
        raise ManagementError("Specify --cases or --trace.")
    ids = split_list(args.ids) or list(trace.data["cases"])
    missing = [i for i in ids if i not in trace.data["cases"]]
    if missing:
        raise ManagementError(f"These cases have not been uploaded yet (they are not in {trace.path.name}): {', '.join(missing)}.")
    return [{"cid": i, **trace.data["cases"][i]} for i in ids]


def validate_keys(args):
    """The story, cycle and case keys go into JQL and API paths: only the format of a key is allowed."""
    pattern = re.compile(r"^[A-Za-z][A-Za-z0-9_]*-\d+$")
    for field in ("story", "cycle"):
        value = getattr(args, field, None)
        if value and not pattern.match(value):
            raise ManagementError(f"--{field} must be a key like PROJ-12 (got {value!r}).")
    for value in split_list(getattr(args, "cases", None)):
        if not pattern.match(value):
            raise ManagementError(f"--cases: {value!r} is not a valid key (e.g. PROJ-45).")


def cmd_folder(args, ad):
    path = folder_path(args.path)
    return {"path": path, "id": ad.create_folder(path)}


def cmd_upload_cases(args, ad):
    args.folder = folder_path(args.folder)
    cases = readers.read_cases(args.source, split_list(args.ids))
    trace = Traceability(args.trace or args.story or Path(args.source).stem, ad.name)
    trace.data.update({"project": ad.project, "source": str(args.source)})
    if args.trace and re.match(r"^US-\d+$", args.trace, re.I):
        trace.data["us"] = args.trace.upper()
    if args.story:
        trace.data["story"] = args.story
    folder_id = ad.create_folder(args.folder)
    trace.data["folder"] = {"path": args.folder, "id": folder_id}

    created, existing, no_link = [], [], []

    def link(cid, remote):
        """Links the case to the story and records it in the traceability; if it fails, it is
        flagged to retry on the next run (without creating the case again)."""
        if not args.story:
            return
        try:
            ad.link_case_to_story(remote, args.story)
            trace.data["cases"][cid]["linked"] = args.story
        except ManagementError as e:
            trace.data["cases"][cid]["linked"] = False
            no_link.append({"case": cid, "key": remote.get("key"), "error": str(e)[:300]})
        if not ad.dry_run:
            trace.save()

    for case in cases:
        cid = case["id"]
        if trace.key_of(cid):
            existing.append({"case": cid, "key": trace.key_of(cid)})
            if args.story and trace.data["cases"][cid].get("linked") is False:
                link(cid, trace.data["cases"][cid])  # retry of the link that failed before
            continue
        remote = ad.create_case(case, folder_id, args.folder)
        # It is recorded as soon as it is created: if something fails later, the retry does not duplicate it.
        trace.data["cases"][cid] = {**remote, "title": case["title"]}
        if not ad.dry_run:
            trace.save()
        link(cid, remote)
        created.append({"case": cid, "key": remote.get("key"), "id": remote.get("id")})
    if not ad.dry_run:
        trace.save()
    cmd_output = {"folder": args.folder, "story": args.story, "created": created,
                  "already_existed": existing, "traceability": str(trace.path)}
    if no_link:
        cmd_output["unlinked"] = no_link
        cmd_output["warning"] = ("These cases were created but could not be linked to the story. "
                                 "Run the same command again: they are not duplicated and the link is retried.")
    return cmd_output


def cmd_link(args, ad):
    if args.cycle:
        ad.link_cycle_to_story({"key": args.cycle, "id": None}, args.story)
        return {"cycle": args.cycle, "story": args.story}
    cases = [{"key": k, "id": None} for k in split_list(args.cases)]
    for case in cases:
        ad.link_case_to_story(case, args.story)
    return {"cases": [c["key"] for c in cases], "story": args.story}


def _optional_trace(args, ad):
    name = args.trace or getattr(args, "story", None)
    return Traceability(name, ad.name) if name else None


def cmd_create_cycle(args, ad):
    trace = _optional_trace(args, ad)
    cycle = ad.create_cycle(args.name, args.description or "",
                            (trace.data.get("folder") or {}).get("path") if trace else None)
    if args.story:
        ad.link_cycle_to_story(cycle, args.story)
    added = []
    if args.cases or (trace and trace.data["cases"]):
        cases = cases_from_args(args, trace, ad)
        ad.add_cases_to_cycle(cycle, cases)
        added = [c["key"] for c in cases]
    if trace and not ad.dry_run:
        trace.data["cycles"].append({**cycle, "name": args.name,
                                     "date": dt.datetime.now().isoformat(timespec="minutes")})
        trace.save()
    return {"cycle": cycle, "story": args.story, "cases": added}


def cmd_add_to_cycle(args, ad):
    trace = _optional_trace(args, ad)
    cases = cases_from_args(args, trace, ad)
    ad.add_cases_to_cycle({"key": args.cycle, "id": None}, cases)
    return {"cycle": args.cycle, "cases": [c["key"] for c in cases]}


def cmd_extract_results(args, _ad):
    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M")
    target = Path(args.output or MANAGEMENT_DIR / f"results-{stamp}.json")
    results = readers.read_results(args.report, target.with_suffix("") )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = {}
    for r in results:
        summary[r["status"]] = summary.get(r["status"], 0) + 1
    return {"results": str(target), "scenarios": len(results), "by_status": summary,
            "detail": [{"scenario": r["scenario"], "tags": r["tags"], "status": r["status"],
                        "evidence": len(r["evidence"])} for r in results]}


def _story_from_trace(trace):
    """The story (US-XXX) the traceability belongs to, if it can be determined."""
    if not trace:
        return None
    if trace.data.get("us"):
        return str(trace.data["us"]).upper()
    m = re.match(r"^(US-\d+)-", trace.path.stem, re.I)  # US-001-xray-cloud.json
    return m.group(1).upper() if m else None


def _key_from_result(result, trace, key_pattern):
    """The case of a scenario is identified by tag: a direct key (@PROJ-45) or a local
    ID (@TC-001) translated with the traceability. TC-XXX IDs repeat in every
    story, so they are only translated if the scenario carries the @US tag of that traceability.
    Returns (key, reason_if_no_key)."""
    for tag in result["tags"]:
        if re.match(key_pattern, tag):
            return tag, None
    tcs = [t for t in result["tags"] if re.match(r"^TC(-API)?-\d+$", t)]
    if not tcs:
        return None, "no @TC-XXX tag or case key"
    if not trace:
        return None, "has @TC-XXX but --trace is missing to translate it"
    story = _story_from_trace(trace)
    uss = [t.upper() for t in result["tags"] if re.match(r"^US-\d+$", t, re.I)]
    if story and story not in uss:
        return None, (f"belongs to another story ({', '.join(uss)})" if uss else
                      f"has no @{story} tag: cannot be sure it belongs to that story")
    for tag in tcs:
        if trace.key_of(tag):
            return trace.key_of(tag), None
    return None, f"{', '.join(tcs)} is not in {trace.path.name} (was the case uploaded?)"


def cmd_publish_results(args, ad):
    trace = _optional_trace(args, ad)
    results = json.loads(Path(args.results).read_text(encoding="utf-8"))
    key_pattern = rf"^{re.escape(ad.project)}-(TC-)?\d+$"
    cycle = {"key": args.cycle, "id": None}
    published, no_case, warnings = [], [], []
    for r in results:
        key, reason = (r["case"], None) if r.get("case") else _key_from_result(r, trace, key_pattern)
        if not key:
            no_case.append({"scenario": r["scenario"], "reason": reason})
            continue
        evid = [e["file"] for e in r["evidence"]
                if e["type"] in ("screenshot", "gif") or (e["type"] == "video" and r["status"] == "failed" and not args.no_video)]
        comment = f"Run with k0lmena ({r['feature']} / {r['scenario']})."
        missing = [t for t in r.get("tags", []) if re.match(r"^MI-\d+$", t, re.I)]
        if "missing-info" in [t.lower() for t in r.get("tags", [])] or missing:
            comment += (f"\n\nMISSING INFORMATION ({', '.join(missing) or 'see the context sheet'}): "
                        "the case depends on data that is not defined; the result may change once it is resolved.")
        if r["error"]:
            comment += f"\n\nError:\n{r['error'][:3000]}"
        not_uploaded = ad.register_result(cycle, {"key": key, "id": None}, r["status"], comment, evid) or []
        warnings += [f"{key}: {Path(a).name} was not uploaded ({why})" for a, why in not_uploaded]
        published.append({"case": key, "scenario": r["scenario"], "status": r["status"],
                          "evidence": len(evid) - len(not_uploaded)})
    return {"cycle": args.cycle, "published": published,
            "no_linked_case": no_case, "warnings": warnings}


def main():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--tool")
    p.add_argument("--dry-run", action="store_true")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("folder"); s.add_argument("--path", required=True)
    s = sub.add_parser("upload-cases")
    s.add_argument("--source", required=True); s.add_argument("--folder", required=True)
    s.add_argument("--story"); s.add_argument("--ids"); s.add_argument("--trace")
    s = sub.add_parser("link")
    s.add_argument("--story", required=True); s.add_argument("--cases"); s.add_argument("--cycle")
    s = sub.add_parser("create-cycle")
    s.add_argument("--name", required=True); s.add_argument("--description")
    s.add_argument("--story"); s.add_argument("--cases"); s.add_argument("--trace"); s.add_argument("--ids")
    s = sub.add_parser("add-to-cycle")
    s.add_argument("--cycle", required=True); s.add_argument("--cases"); s.add_argument("--trace"); s.add_argument("--ids")
    s = sub.add_parser("extract-results")
    s.add_argument("--report", required=True); s.add_argument("--output")
    s = sub.add_parser("publish-results")
    s.add_argument("--cycle", required=True); s.add_argument("--results", required=True)
    s.add_argument("--trace"); s.add_argument("--no-video", action="store_true")

    args = p.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # the Windows console is not UTF-8 by default
    load_env()
    try:
        if args.command == "extract-results":  # does not need credentials
            output(cmd_extract_results(args, None))
            return
        validate_keys(args)
        tool = args.tool or env("MANAGEMENT_TOOL")
        adapter = create_adapter(tool, args.dry_run)
        command = globals()["cmd_" + args.command.replace("-", "_")]
        output(command(args, adapter))
    except ManagementError as e:
        output({"error": str(e)})
        sys.exit(1)
    except Exception as e:  # network down, invalid JSON in the .env, etc.: the agent reads a JSON, not a traceback
        output({"error": f"{type(e).__name__}: {e}"})
        sys.exit(1)


if __name__ == "__main__":
    main()
