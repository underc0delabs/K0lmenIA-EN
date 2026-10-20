"""Xray Server / Data Center: Xray REST (/rest/raven/1.0) + Jira REST (/rest/api/2).

Docs: https://docs.getxray.app/display/XRAY/REST+API

Mapping:
- folder   -> Test Repository folder (created level by level; root = -1)
- case     -> "Test" issue (Manual: steps with the steps API; Cucumber: Cucumber Test Type
              and Cucumber Scenario fields). The custom field ids are discovered at runtime.
- cycle    -> "Test Execution" issue
- case-story link   -> Jira issue link of type "Tests" (the one with outward = "tests")
- cycle-story link  -> "Relates" issue link
"""
import base64
import json
import os
import re
from pathlib import Path

from adapters.base import Adapter, remote_title, with_time, native_time, try_with_time, jira_duration, hhmm
from common import ManagementError, Http, env

STATUSES = {"passed": "PASS", "failed": "FAIL", "pending": "TODO",
            "in_progress": "EXECUTING", "blocked": "ABORTED"}
PRIORITIES = {"Critical": "Highest", "High": "High", "Medium": "Medium", "Low": "Low"}


class XrayDC(Adapter):
    name = "xray-dc"

    def __init__(self, project, dry_run=False):
        super().__init__(project, dry_run)
        headers = {"Accept": "application/json"}
        if dry_run:
            headers["Authorization"] = "Bearer dry-run"
        elif os.environ.get("XRAY_DC_TOKEN", "").strip():
            headers["Authorization"] = f'Bearer {env("XRAY_DC_TOKEN")}'
        else:
            cred = base64.b64encode(f'{env("XRAY_DC_USER")}:{env("XRAY_DC_PASSWORD")}'.encode()).decode()
            headers["Authorization"] = f"Basic {cred}"
        self.http = Http(env("XRAY_DC_URL") if not dry_run else "https://jira.dry-run",
                         headers, dry_run=dry_run, name="xray-dc")
        self.statuses = {**STATUSES, **json.loads(os.environ.get("XRAY_STATUSES", "{}") or "{}")}
        self.priorities = {**PRIORITIES, **json.loads(os.environ.get("MANAGEMENT_PRIORITIES", "{}") or "{}")}
        mb = float(os.environ.get("MANAGEMENT_ATTACHMENT_LIMIT_MB", "10") or 10)  # Jira default: 10 MB
        self.attachment_limit = int(mb * 1024 * 1024)
        self._fields = None
        self._case_link = None

    # --- utilities -----------------------------------------------------------------------
    def field(self, name):
        """Id of the Xray custom field by name (it varies on each instance)."""
        if self._fields is None:
            self._fields = {} if self.dry_run else {f["name"]: f["id"] for f in self.http.get("/rest/api/2/field")}
        if self.dry_run:
            return f"customfield({name})"
        if name not in self._fields:
            raise ManagementError(f"Jira does not have the field '{name}'. Is Xray installed on this instance?")
        return self._fields[name]

    def _case_link_type(self):
        if self._case_link is None:
            self._case_link = os.environ.get("XRAY_LINK_CASE", "").strip()
            if not self._case_link:
                self._case_link = "Tests"
                if not self.dry_run:
                    types = self.http.get("/rest/api/2/issueLinkType").get("issueLinkTypes", [])
                    self._case_link = next((t["name"] for t in types if t.get("outward", "").lower() == "tests"), "Tests")
        return self._case_link

    def _link(self, link_type, source_key, destination_key):
        inward, outward = source_key, destination_key
        if os.environ.get("XRAY_LINK_INVERT", "").strip() in ("1", "true", "on"):
            inward, outward = outward, inward
        self.http.post("/rest/api/2/issueLink", json_body={
            "type": {"name": link_type}, "inwardIssue": {"key": inward}, "outwardIssue": {"key": outward}})

    def _create_with_time(self, fields, case):
        """The estimated time goes to the Jira Original Estimate; if the project has no time tracking, without it."""
        with_field = fields
        if native_time() and case.get("estimate"):
            with_field = {**fields, "timetracking": {"originalEstimate": jira_duration(case["estimate"]["minutes"])}}
        return try_with_time(self._create_issue, with_field, fields)

    def _create_issue(self, fields):
        r = self.http.post("/rest/api/2/issue", json_body={"fields": {"project": {"key": self.project}, **fields}})
        return {"key": r.get("key"), "id": r.get("id")}

    # --- repository ----------------------------------------------------------------------
    def create_folder(self, path):
        base = f"/rest/raven/1.0/api/testrepository/{self.project}/folders"
        tree = [] if self.dry_run else self.http.get(base).get("folders", [])
        parent_id, children = -1, tree
        for part in [p for p in path.strip("/").split("/") if p]:
            existing = next((f for f in children if f.get("name") == part), None)
            if existing:
                parent_id, children = existing["id"], existing.get("folders") or []
            else:
                r = self.http.post(f"{base}/{parent_id}", json_body={"name": part})
                parent_id, children = r.get("id"), []
        return parent_id

    def create_case(self, case, folder_id, folder_path):
        description = case.get("description", "")
        if case.get("preconditions"):
            description += f"\n\nPreconditions: {case['preconditions']}"
        fields = {
            "issuetype": {"name": "Test"},
            "summary": remote_title(case, 250),
            "description": with_time(description.strip() or case["title"], case),
            "labels": [e.replace(" ", "_") for e in case.get("tags", [])] + ["k0lmenIA"],
        }
        priority = self.priorities.get(case.get("priority"))
        if priority and os.environ.get("MANAGEMENT_SEND_PRIORITY", "1") != "0":
            fields["priority"] = {"name": priority}
        if case["type"] == "cucumber":
            # The Cucumber Scenario field holds only the steps (without the "Scenario:" line); the Background goes to the description.
            lines = case["gherkin"].splitlines()
            outline = any(re.match(r"^\s*Scenario (Outline|Template):", l) for l in lines)
            start = next((i for i, l in enumerate(lines) if re.match(r"^\s*(Scenario|Example)", l)), -1)
            background = "\n".join(l.strip() for l in lines[:start] if l.strip()) if start > 0 else ""
            if background:
                fields["description"] += f"\n\n{background}"
            fields[self.field("Test Type")] = {"value": "Cucumber"}
            fields[self.field("Cucumber Test Type")] = {"value": "Scenario Outline" if outline else "Scenario"}
            fields[self.field("Cucumber Scenario")] = "\n".join(l.strip() for l in lines[start + 1:] if l.strip())
            created = self._create_with_time(fields, case)
        else:
            fields[self.field("Test Type")] = {"value": "Manual"}
            created = self._create_with_time(fields, case)
            for p in case["steps"]:
                self.http.put(f'/rest/raven/1.0/api/test/{created["key"]}/step',
                              json_body={"step": p["action"], "data": p["data"], "result": p["result"]})
        if folder_id not in (None, -1):
            errors = self.http.put(f"/rest/raven/1.0/api/testrepository/{self.project}/folders/{folder_id}/tests",
                                   json_body={"add": [created["key"]]})
            if isinstance(errors, list) and errors:
                raise ManagementError(f"Xray did not move {created['key']} to the folder: {errors}")
        return created

    def link_case_to_story(self, case, story):
        self._link(self._case_link_type(), case["key"], story)

    # --- cycles --------------------------------------------------------------------------
    def create_cycle(self, name, description="", folder_path=None):
        fields = {"issuetype": {"name": "Test Execution"}, "summary": name[:250], "labels": ["k0lmenIA"]}
        if description:
            fields["description"] = description
        return self._create_issue(fields)

    def link_cycle_to_story(self, cycle, story):
        self._link(os.environ.get("XRAY_LINK_CYCLE", "Relates"), cycle["key"], story)

    def add_cases_to_cycle(self, cycle, cases):
        self.http.post(f'/rest/raven/1.0/api/testexec/{cycle["key"]}/test',
                       json_body={"add": [c["key"] for c in cases]})

    # --- results -------------------------------------------------------------------------
    def _run_id(self, cycle, case):
        params = {"testExecIssueKey": cycle["key"], "testIssueKey": case["key"]}
        try:
            return self.http.get("/rest/raven/1.0/api/testrun", params=params)["id"]
        except (ManagementError, KeyError):
            self.add_cases_to_cycle(cycle, [case])  # the case was not in the execution
            return self.http.get("/rest/raven/1.0/api/testrun", params=params)["id"]

    def register_result(self, cycle, case, status, comment, evidence):
        run_id = self._run_id(cycle, case)
        self.http.put(f"/rest/raven/1.0/api/testrun/{run_id}",
                      json_body={"status": self.statuses[status], "comment": comment})
        not_uploaded = []
        for file in evidence:
            path = Path(file)
            if path.stat().st_size * 4 / 3 > self.attachment_limit:  # base64 adds ~33%
                not_uploaded.append((file, f"exceeds the attachment limit ({self.attachment_limit // 1048576} MB)"))
                continue
            mime = {"png": "image/png", "gif": "image/gif", "webm": "video/webm", "mp4": "video/mp4"}.get(
                path.suffix.lstrip(".").lower(), "application/octet-stream")
            data = "<base64>" if self.dry_run else base64.b64encode(path.read_bytes()).decode()
            try:
                self.http.post(f"/rest/raven/1.0/api/testrun/{run_id}/attachment",
                               json_body={"data": data, "filename": path.name, "contentType": mime})
            except ManagementError as e:
                not_uploaded.append((file, str(e)[:200]))
        return not_uploaded
