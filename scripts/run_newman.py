#!/usr/bin/env python3
"""
Runs a Postman collection with Newman and leaves the HTML report of the run (api-runner agent).

Usage (from the repo root; on Mac/Linux, python3):
    python scripts/run_newman.py <collection> [--story US-001] [--title "Auth API"]
                                    [--folder "Login"] [--environment env] [--base-url URL] [--data data.csv]

<collection> can be a Postman collection (.json), a **Bruno** folder (with bruno.json) or an
**Insomnia** export (v4 .json or v5 .yaml): Bruno and Insomnia ones are converted to Postman first with
scripts/convert_collection.py (in a temp folder that is deleted at the end) and the
warnings about what could not be converted are shown. With Bruno and Insomnia, --environment is the NAME of the
environment (Bruno: the environments/ file without .bru; Insomnia: the sub-environment); with Postman,
the environment .json file. GraphQL requests run the same as REST ones.

What it does:
1. Takes API_TOKEN from the root .env (the {{token}} variable of the collection). The URL ({{base_url}})
   comes, in this order, from --base-url, the environment or the collection, and if none of them defines it,
   from API_BASEURL in the .env. It works the same in PowerShell, bash and zsh: no need to load the .env.
2. Runs Newman (installed globally or with npx) and exports its JSON.
3. Converts it to the results format (scripts/newman_to_results.py), with the story.
4. Generates the HTML report (scripts/generate_report.py) and deletes Newman's raw JSON.

Output in output/runs/: report-<US or API>-<date-time>.html and _results-<US or API>-<date-time>.json.
The token is never written to files or to the report.
"""
import argparse
import datetime
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from _env import read_env  # noqa: E402
import convert_collection  # noqa: E402

OUTPUT = ROOT / "output" / "runs"


def newman():
    if shutil.which("newman"):
        return ["newman"]
    if shutil.which("npx"):
        return ["npx", "-y", "newman@6"]
    sys.exit("Neither Newman nor npx was found. Install Node.js and then: npm install -g newman")


def own_base_url(collection, environment):
    """The base_url that the environment or the collection already define (if they do, the .env does not override it)."""
    for file, key in ((environment, "values"), (collection, "variable")):
        if not file:
            continue
        try:
            data = json.loads(Path(file).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        for v in data.get(key) or []:
            if v.get("key") == "base_url" and v.get("value") and v.get("enabled", True) is not False:
                return v["value"]
    return None


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Runs a Postman collection and generates the HTML report")
    ap.add_argument("collection", help="Postman collection (.json), Bruno folder or Insomnia export")
    ap.add_argument("--story", help="US-XXX: goes in the file names and in the report")
    ap.add_argument("--title", help="report title (by default, the collection name)")
    ap.add_argument("--folder", help="only this folder of the collection (Newman's --folder)")
    ap.add_argument("--environment", help="Postman: environment .json file; Bruno/Insomnia: environment name")
    ap.add_argument("--base-url", help="overrides API_BASEURL from the .env")
    ap.add_argument("--data", help="data CSV or JSON (Newman's -d): one iteration per row, each one is a case in the report")
    a = ap.parse_args()

    collection = Path(a.collection)
    if not collection.exists():
        sys.exit(f"The collection {collection} does not exist.")
    if a.data and not Path(a.data).is_file():
        sys.exit(f"The data file {a.data} does not exist.")
    fmt = convert_collection.detect_format(collection)
    if fmt is None:
        sys.exit(f"Unrecognized {collection}: it must be a Postman collection (.json), a "
                 "Bruno folder (with bruno.json) or an Insomnia export (v4 .json or v5 .yaml).")
    if a.story and not re.match(r"^US-\d+$", a.story, re.I):
        sys.exit("--story must be an ID like US-001.")
    env = read_env()
    prefix = a.story.upper() if a.story else "API"
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M")
    OUTPUT.mkdir(parents=True, exist_ok=True)
    raw = OUTPUT / f"_newman-{prefix}-{stamp}.json"
    results = OUTPUT / f"_results-{prefix}-{stamp}.json"
    report = OUTPUT / f"report-{prefix}-{stamp}.html"
    temp = None
    if fmt != "postman":
        conv = convert_collection.convert(collection, a.environment)
        temp = OUTPUT / f"_conversion-{prefix}-{stamp}"
        collection, converted_env = convert_collection.save(conv, temp, "collection")
        a.environment = str(converted_env) if converted_env else None
        n = convert_collection.count_requests(conv.collection["item"])
        print(f"Converted from {fmt}: {n} request(s)" + (f" · environment {conv.environment['name']}" if conv.environment else ""))
        for warning in conv.warnings:
            print(f"  ! {warning}")
    try:
        _run(a, collection, env, raw, results, report)
    finally:
        if temp:
            shutil.rmtree(temp, ignore_errors=True)


def _run(a, collection, env, raw, results, report):
    cmd = newman() + ["run", str(collection), "-r", "cli,json", "--reporter-json-export", str(raw)]
    if a.environment:
        cmd += ["-e", a.environment]
    if a.folder:
        cmd += ["--folder", a.folder]
    if a.data:
        cmd += ["-d", a.data]
    own = own_base_url(collection, a.environment)
    base = a.base_url or (None if own else env.get("API_BASEURL"))
    if base:
        cmd += ["--env-var", f"base_url={base}"]  # --env-var wins over the environment and the collection
    base = base or own
    if env.get("API_TOKEN"):
        cmd += ["--env-var", f"token={env['API_TOKEN']}"]  # only on the process command line, never in files

    print(f"Newman · {Path(a.collection).name}" + (f" · folder {a.folder}" if a.folder else "") + (f" · {base}" if base else ""))
    r = subprocess.run(cmd, shell=(sys.platform == "win32"))
    if not raw.exists():
        sys.exit(f"Newman did not generate results (code {r.returncode}). Check the output above.")

    title = a.title or json.loads(collection.read_text(encoding="utf-8")).get("info", {}).get("name", collection.stem)
    subprocess.run([sys.executable, str(ROOT / "scripts" / "newman_to_results.py"), str(raw), str(results), title], check=True)
    data = json.loads(results.read_text(encoding="utf-8"))
    if a.story:
        data["story"] = a.story.upper()
    if base:
        data["url"] = base
    results.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    subprocess.run([sys.executable, str(ROOT / "scripts" / "generate_report.py"), str(results), str(report)], check=True)
    raw.unlink(missing_ok=True)

    cases = data.get("cases", [])
    count = {s: sum(1 for c in cases if c.get("status") == s) for s in ("Passed", "Failed", "Blocked")}
    print(f"\nResult: {len(cases)} requests · {count['Passed']} passed · {count['Failed']} failed · {count['Blocked']} blocked")
    print(f"Report:  {report.relative_to(ROOT).as_posix()}")
    print(f"Results: {results.relative_to(ROOT).as_posix()}")


if __name__ == "__main__":
    main()
