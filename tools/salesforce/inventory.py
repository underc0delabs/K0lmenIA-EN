#!/usr/bin/env python3
"""
QA inventory of an AUTHORIZED Salesforce org (sandbox or scratch), with the official `sf` CLI.

Usage (from the repo root):
    python tools/salesforce/inventory.py --org <alias> [--objects Account,Opportunity,Order__c]
        [--story US-001] [--apex] [--allow-production] [--confirm]

What it does (read-only, except --apex):
- Verifies that the alias is in SALESFORCE_AUTHORIZED_ORGS in the .env and that the org is connected (sf org display).
- Reads the org (Organization: whether it is a sandbox, type, language, time zone). If it is PRODUCTION, it stops unless
  --allow-production is passed (and even then, read-only and without --apex).
- Surveys what needs testing: profiles and active users per profile (counts only), permission sets,
  record types, validation rules (Tooling API), flows (with any Process Builders still active),
  Apex triggers, Apex coverage (ApexCodeCoverageAggregate), sharing model (OWD) of the objects,
  duplicate rules, approval processes and org limits (sf org list limits).
- With --apex it runs the local Apex tests (RunLocalTests) with coverage: it leaves no data (Apex rolls back what
  its tests create), but it consumes asynchronous limits; that is why it is confirmed and never runs in production.
- Computes findings (coverage < 75 %, failed tests, nearly exhausted limits, active Process Builders,
  several triggers per object, public read/write OWD, inactive rules) and test suggestions
  (one negative per validation rule, one test per record-triggered flow, a bulk of 200 per trigger,
  one per profile with users).
- Writes to output/salesforce/<story or alias>/: salesforce.json and salesforce-report.html; the previous
  run moves to history/ (last 5).

Queries are passed to `sf` through a file (--file), so nothing is interpreted on the command line.
It does not create, edit or delete records, metadata, users or permissions.
"""
import argparse
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MIN_COVERAGE = 75  # the coverage Salesforce requires to deploy to production
STANDARD_OBJECTS = ["Account", "Contact", "Lead", "Opportunity", "Case"]
KEY_LIMITS = {"DailyApiRequests", "DataStorageMB", "FileStorageMB", "DailyAsyncApexExecutions",
                 "DailyBulkV2QueryJobs", "DailyWorkflowEmails", "SingleEmail", "MassEmail", "HourlyPublishedPlatformEvents"}
OWD_OPEN = {"ReadWrite", "ReadWriteTransfer", "FullAccess"}

QUERIES = {
    "organization": ("SELECT Id, Name, OrganizationType, IsSandbox, InstanceName, LanguageLocaleKey, TimeZoneSidKey "
                     "FROM Organization", False),
    "profiles": ("SELECT Id, Name, UserType FROM Profile ORDER BY Name", False),
    "users_by_profile": ("SELECT Profile.Name, COUNT(Id) total FROM User WHERE IsActive = true GROUP BY Profile.Name", False),
    "permission_sets": ("SELECT Name, Label, NamespacePrefix FROM PermissionSet WHERE IsOwnedByProfile = false ORDER BY Label", False),
    "record_types": ("SELECT SobjectType, DeveloperName, Name, IsActive FROM RecordType ORDER BY SobjectType", False),
    "validations": ("SELECT Id, ValidationName, Active, ErrorDisplayField, ErrorMessage, EntityDefinition.QualifiedApiName "
                     "FROM ValidationRule", True),
    "flows": ("SELECT ApiName, Label, ProcessType, TriggerType, IsActive, LastModifiedDate FROM FlowDefinitionView ORDER BY Label", False),
    "triggers": ("SELECT Name, TableEnumOrId, Status FROM ApexTrigger WHERE NamespacePrefix = null ORDER BY TableEnumOrId", False),
    "coverage": ("SELECT ApexClassOrTrigger.Name, NumLinesCovered, NumLinesUncovered FROM ApexCodeCoverageAggregate", True),
    "custom_objects": ("SELECT DeveloperName, NamespacePrefix FROM CustomObject", True),
    "duplicates": ("SELECT DeveloperName, SobjectType, IsActive FROM DuplicateRule", False),
    "approvals": ("SELECT Name, TableEnumOrId, State FROM ProcessDefinition WHERE Type = 'Approval'", False),
}


def exit_with(msg, code=2):
    print(msg, file=sys.stderr)
    sys.exit(code)


def read_env():
    sys.path.insert(0, str(ROOT / "scripts"))
    from _env import read_env as _read
    values = _read()
    values.update({k: v for k, v in os.environ.items() if k.startswith("SALESFORCE_")})
    return values


def authorized(alias, env):
    allowed = [u.strip() for u in re.split(r"[,\s]+", env.get("SALESFORCE_AUTHORIZED_ORGS", "")) if u.strip()]
    if not allowed:
        exit_with("There are no authorized Salesforce orgs. Add to the root .env:\n"
              "  SALESFORCE_AUTHORIZED_ORGS=my-qa-sandbox\n"
              "(the alias you authorized it with: sf org login web --alias my-qa-sandbox --instance-url https://test.salesforce.com).")
    if alias not in allowed:
        exit_with(f"{alias} is not in SALESFORCE_AUTHORIZED_ORGS in the .env. Only authorized orgs are surveyed.")


def sf_cli():
    sf = shutil.which("sf")
    if not sf:
        exit_with("The Salesforce CLI (sf) was not found. Install it with: npm install --global @salesforce/cli\n"
              "and authorize the org: sf org login web --alias <alias> --instance-url https://test.salesforce.com")
    return sf


def run_sf(sf, args, timeout=180):
    """Runs `sf <args> --json` and returns (result, error). sf answers JSON with status 0 when it succeeded."""
    try:
        p = subprocess.run([sf, *args, "--json"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired:
        return None, f"sf {args[0]} {args[1] if len(args) > 1 else ''}: took longer than {timeout} s"
    try:
        data = json.loads(p.stdout or "{}")
    except ValueError:
        return None, (p.stderr or p.stdout or "non-JSON response").strip()[:300]
    if data.get("status", 1) != 0:
        return None, (data.get("message") or data.get("name") or "sf error").strip()[:300]
    return data.get("result"), None


def query(sf, alias, soql, tooling=False):
    """Read-only SOQL through a file (--file): returns (records, error)."""
    with tempfile.NamedTemporaryFile("w", suffix=".soql", delete=False, encoding="utf-8") as f:
        f.write(soql)
        path = f.name
    try:
        args = ["data", "query", "--file", path, "--target-org", alias]
        if tooling:
            args.append("--use-tooling-api")
        res, err = run_sf(sf, args)
    finally:
        os.unlink(path)
    if err:
        return [], err
    return [{k: v for k, v in r.items() if k != "attributes"} for r in (res or {}).get("records", [])], None


def _rel_name(r, rel, field="Name"):
    v = r.get(rel)
    return v.get(field) if isinstance(v, dict) else r.get(field)


def objects_to_review(requested, custom):
    if requested:
        return [o.strip() for o in requested.split(",") if re.fullmatch(r"[A-Za-z][\w]*", o.strip())][:50]
    names = [f'{c["NamespacePrefix"] + "__" if c.get("NamespacePrefix") else ""}{c["DeveloperName"]}__c'
               for c in custom if c.get("DeveloperName")]
    return (STANDARD_OBJECTS + sorted(names))[:50]


def findings_and_suggestions(inv):
    h, s = [], []
    org = inv.get("organization") or {}
    if org and not org.get("IsSandbox"):
        h.append({"severity": "Critical", "area": "Org", "text": "The org is PRODUCTION: it was surveyed read-only and Apex was not run."})

    cov = inv.get("coverage") or []
    covered = sum(c.get("NumLinesCovered") or 0 for c in cov)
    uncovered = sum(c.get("NumLinesUncovered") or 0 for c in cov)
    if covered + uncovered:
        pct = 100 * covered / (covered + uncovered)
        inv["org_coverage"] = round(pct, 1)
        if pct < MIN_COVERAGE:
            h.append({"severity": "High", "area": "Apex",
                      "text": f"Org Apex coverage {pct:.1f} %: below the {MIN_COVERAGE} % Salesforce requires to deploy to production."})
        zeros = sorted(_rel_name(c, "ApexClassOrTrigger") or "?" for c in cov
                       if not c.get("NumLinesCovered") and (c.get("NumLinesUncovered") or 0) > 0)
        if zeros:
            h.append({"severity": "Medium", "area": "Apex",
                      "text": f"{len(zeros)} class(es) or trigger(s) without a single covered line: {', '.join(zeros[:10])}{'…' if len(zeros) > 10 else ''}."})
    elif not inv.get("errors", {}).get("coverage"):
        h.append({"severity": "Low", "area": "Apex", "text": "There is no coverage data (the Apex tests were never run or there is no custom Apex)."})

    apex = inv.get("apex") or {}
    for t in apex.get("failed") or []:
        h.append({"severity": "High", "area": "Apex", "text": f'Failed Apex test: {t.get("name")} — {(t.get("message") or "")[:200]}'})

    for lim in inv.get("limits") or []:
        maximum, remaining = lim.get("max") or 0, lim.get("remaining")
        if lim.get("name") in KEY_LIMITS and maximum and remaining is not None:
            used = 100 * (maximum - remaining) / maximum
            if used >= 80:
                h.append({"severity": "High" if used >= 90 else "Medium", "area": "Limits",
                          "text": f'{lim["name"]}: {used:.0f} % used ({maximum - remaining} of {maximum}). Tests may fail because of the limit and not because of a bug.'})

    for f in inv.get("flows") or []:
        if f.get("IsActive") and f.get("ProcessType") == "Workflow":
            h.append({"severity": "Medium", "area": "Automation",
                      "text": f'Active Process Builder "{f.get("Label")}": Salesforce retired it (end of support 2025-12-31); it should be migrated to Flow and the replacement tested.'})
        if f.get("IsActive") and f.get("TriggerType") in ("RecordBeforeSave", "RecordAfterSave", "RecordBeforeDelete"):
            s.append({"area": "Flow", "element": f.get("Label") or f.get("ApiName"),
                      "test": f'Create/edit the record that triggers "{f.get("Label")}" ({f.get("TriggerType")}) and verify its effects, also in bulk (200 records).'})
        elif f.get("IsActive") and f.get("ProcessType") == "Flow":
            s.append({"area": "Flow", "element": f.get("Label") or f.get("ApiName"),
                      "test": f'Walk through the screen flow "{f.get("Label")}" along each decision path, with valid and invalid data.'})

    by_object = {}
    for t in inv.get("triggers") or []:
        if t.get("Status") == "Active":
            by_object.setdefault(t.get("TableEnumOrId"), []).append(t.get("Name"))
            s.append({"area": "Apex", "element": t.get("Name"),
                      "test": f'Insert/update 200 {t.get("TableEnumOrId")} records at once (bulk) and verify that the trigger {t.get("Name")} does not exceed governor limits.'})
        elif t.get("Status") == "Inactive":
            h.append({"severity": "Low", "area": "Apex", "text": f'Inactive trigger {t.get("Name")} on {t.get("TableEnumOrId")}: confirm whether it should be active.'})
    for obj, names in by_object.items():
        if len(names) > 1:
            h.append({"severity": "Medium", "area": "Apex",
                      "text": f'{obj} has {len(names)} active triggers ({", ".join(names)}): Salesforce does not guarantee their execution order.'})

    for v in inv.get("validations") or []:
        obj = _rel_name(v, "EntityDefinition", "QualifiedApiName")
        if v.get("Active"):
            s.append({"area": "Validation", "element": f'{obj}.{v.get("ValidationName")}',
                      "test": f'Save a {obj} that breaks the rule and verify the message "{(v.get("ErrorMessage") or "")[:120]}"'
                                f'{" on the field " + v["ErrorDisplayField"] if v.get("ErrorDisplayField") else " at the top of the form"}; and one that complies with it.'})
        else:
            h.append({"severity": "Low", "area": "Validation", "text": f'Inactive validation rule {obj}.{v.get("ValidationName")}: confirm whether it is intentional.'})

    for o in inv.get("sharing") or []:
        if o.get("InternalSharingModel") in OWD_OPEN:
            h.append({"severity": "Medium", "area": "Sharing",
                      "text": f'{o.get("QualifiedApiName")}: internal default access "{o.get("InternalSharingModel")}" (everyone sees and edits). Confirm that this is expected.'})
        if o.get("InternalSharingModel") in ("Private", "Read"):
            s.append({"area": "Sharing", "element": o.get("QualifiedApiName"),
                      "test": f'With a user who is not the owner and is not above in the role hierarchy, verify that they cannot {"see" if o.get("InternalSharingModel") == "Private" else "edit"} someone else\'s {o.get("QualifiedApiName")}.'})

    for d in inv.get("duplicates") or []:
        if not d.get("IsActive"):
            h.append({"severity": "Low", "area": "Data", "text": f'Inactive duplicate rule {d.get("SobjectType")}.{d.get("DeveloperName")}.'})
        else:
            s.append({"area": "Data", "element": f'{d.get("SobjectType")}.{d.get("DeveloperName")}',
                      "test": f'Create a duplicate {d.get("SobjectType")} and verify that it is blocked or warned about according to the rule.'})

    for a in inv.get("approvals") or []:
        if a.get("State") == "Active":
            s.append({"area": "Approval", "element": a.get("Name"),
                      "test": f'Submit a {a.get("TableEnumOrId")} for approval and go through approve, reject and recall, verifying record locking and notifications.'})

    for p in inv.get("users_by_profile") or []:
        name = _rel_name(p, "Profile")
        if name and (p.get("total") or 0) > 0:
            s.append({"area": "Permissions", "element": name,
                      "test": f'With a test user of the "{name}" profile, verify which objects, fields, tabs and buttons they see and can use (permissions-tester).'})

    rts = {}
    for r in inv.get("record_types") or []:
        if r.get("IsActive"):
            rts.setdefault(r.get("SobjectType"), []).append(r.get("Name"))
    for obj, names in rts.items():
        if len(names) > 1:
            s.append({"area": "Record types", "element": obj,
                      "test": f'Create a {obj} with each record type ({", ".join(names)}) and verify the layout, picklists and validations of each one.'})

    order = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
    h.sort(key=lambda x: order.get(x["severity"], 9))
    return h, s


def run_apex(sf, alias):
    res, err = run_sf(sf, ["apex", "run", "test", "--test-level", "RunLocalTests", "--code-coverage",
                              "--result-format", "json", "--wait", "30", "--target-org", alias], timeout=1900)
    if err:
        return {"error": err}
    res = res or {}
    summary = res.get("summary") or {}
    failed = [{"name": t.get("FullName") or f'{(t.get("ApexClass") or {}).get("Name", "?")}.{t.get("MethodName", "?")}',
                 "message": t.get("Message") or ""} for t in res.get("tests") or [] if t.get("Outcome") not in ("Pass", "Skip")]
    return {"result": summary.get("outcome"), "ran": summary.get("testsRan"), "passed": summary.get("passing"),
            "failed_n": summary.get("failing"), "org_coverage": summary.get("orgWideCoverage"), "failed": failed}


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="QA inventory of a Salesforce org (read-only).")
    ap.add_argument("--org", help="alias of the org authorized in sf (or SALESFORCE_ORG in the .env)")
    ap.add_argument("--objects", default="", help="comma-separated objects for the sharing model (or SALESFORCE_OBJECTS)")
    ap.add_argument("--story", default="")
    ap.add_argument("--apex", action="store_true", help="run the local Apex tests with coverage (never in production)")
    ap.add_argument("--allow-production", action="store_true", help="survey a production org read-only")
    ap.add_argument("--confirm", action="store_true")
    args = ap.parse_args(argv)

    env = read_env()
    alias = args.org or env.get("SALESFORCE_ORG") or ""
    if not alias:
        exit_with("The org is missing: pass it with --org <alias> or set SALESFORCE_ORG in the .env.")
    if not re.fullmatch(r"[\w.@+-]+", alias):
        exit_with(f"Invalid alias: {alias!r}")
    authorized(alias, env)
    sf = sf_cli()

    if not args.confirm:
        print(f"You are about to survey the Salesforce org {alias} (read-only{'; the Apex tests will also be run' if args.apex else ''}).")
        if input("Confirm? [y/N] ").strip().lower() not in ("y", "yes"):
            exit_with("Cancelled.", 1)

    print(f"[salesforce] Connecting to {alias} …", file=sys.stderr)
    info, err = run_sf(sf, ["org", "display", "--target-org", alias])
    if err:
        exit_with(f"Could not connect to the org {alias}: {err}\nAuthorize it with: sf org login web --alias {alias} --instance-url https://test.salesforce.com")
    orgs, err = query(sf, alias, QUERIES["organization"][0])
    if err or not orgs:
        exit_with(f"Could not read the organization: {err or 'no data'}")
    org = orgs[0]
    if not org.get("IsSandbox"):
        if not args.allow_production:
            exit_with(f"The org {alias} is PRODUCTION ({org.get('OrganizationType')}). It is not surveyed without --allow-production "
                  "(and the explicit authorization of its owner). Use a sandbox.")
        if args.apex:
            exit_with("Apex tests are not run in production. Remove --apex.")

    inv = {"organization": org, "errors": {}}
    for key, (soql, tooling) in QUERIES.items():
        if key in ("organization", "custom_objects"):
            continue
        print(f"[salesforce] {key} …", file=sys.stderr)
        records, err = query(sf, alias, soql, tooling)
        inv[key] = records
        if err:
            inv["errors"][key] = err
    custom, err = query(sf, alias, QUERIES["custom_objects"][0], True)
    if err:
        inv["errors"]["custom_objects"] = err
    inv["custom_objects"] = custom
    objects = objects_to_review(args.objects or env.get("SALESFORCE_OBJECTS", ""), custom)
    object_list = ", ".join(f"'{o}'" for o in objects)
    inv["sharing"], err = query(sf, alias, "SELECT QualifiedApiName, Label, InternalSharingModel, ExternalSharingModel "
                                               f"FROM EntityDefinition WHERE QualifiedApiName IN ({object_list})")
    if err:
        inv["errors"]["sharing"] = err
    limits, err = run_sf(sf, ["org", "list", "limits", "--target-org", alias])
    inv["limits"] = limits or []
    if err:
        inv["errors"]["limits"] = err
    if args.apex:
        print("[salesforce] Running the Apex tests (it may take several minutes) …", file=sys.stderr)
        inv["apex"] = run_apex(sf, alias)
        if inv["apex"].get("error"):
            inv["errors"]["apex"] = inv["apex"]["error"]

    findings, suggestions = findings_and_suggestions(inv)
    data = {"generated": datetime.datetime.now().isoformat(timespec="seconds"), "story": args.story or None,
             "org": {"alias": alias, "name": org.get("Name"), "type": org.get("OrganizationType"), "sandbox": bool(org.get("IsSandbox")),
                     "instance": org.get("InstanceName"), "language": org.get("LanguageLocaleKey"), "timezone": org.get("TimeZoneSidKey"),
                     "api": (info or {}).get("apiVersion"), "url": (info or {}).get("instanceUrl")},
             "inventory": inv, "findings": findings, "suggestions": suggestions}

    folder = ROOT / "output" / "salesforce" / re.sub(r"[^\w.-]+", "-", args.story or alias)
    folder.mkdir(parents=True, exist_ok=True)
    try:
        sys.path.insert(0, str(ROOT / "scripts"))
        import _history
        _history.archive(folder, ["salesforce.json", "analysis.json", "salesforce-report.html"], "salesforce.json")
    except Exception as ex:
        print(f"[warning] could not archive the previous run: {ex}", file=sys.stderr)
    (folder / "salesforce.json").write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        import generate_salesforce_report
        generate_salesforce_report.generate(folder / "salesforce.json", folder / "salesforce-report.html")
        print(f"[salesforce] Report: {folder / 'salesforce-report.html'}", file=sys.stderr)
    except Exception as ex:
        print(f"[warning] could not generate the HTML report: {ex}", file=sys.stderr)
    print(f"[salesforce] {len(findings)} finding(s), {len(suggestions)} test suggestion(s)"
          f"{', ' + str(len(inv['errors'])) + ' query(ies) with errors' if inv['errors'] else ''}.")
    print(f"[salesforce] Data: {folder / 'salesforce.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
