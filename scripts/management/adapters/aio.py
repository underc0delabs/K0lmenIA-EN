"""AIO Tests (Jira Cloud): public REST API v1.

Docs: https://tcms.aiojiraapps.com/aio-tcms/aiotcms-static/api-docs/  (official OpenAPI)
      https://aiosupport.atlassian.net/wiki/spaces/AioTests

Mapping:
- folder   -> case folder (PUT .../testcase/folder/hierarchy, idempotent)
- case     -> AIO case (Classic with steps or BDD with Given/When/Then steps), status "Published"
              (AIO only lets you add published cases to a cycle)
- cycle    -> test cycle (link to the story in jiraTaskIDs)
- case-story link -> jiraRequirementIDs of the case
- result   -> test run of the case in the cycle + attachments to the run
Rate limit: 60 requests per minute -> 1 request per second.
"""
import json
import os
import re
from pathlib import Path

from adapters.base import Adapter, remote_title, with_time, native_time, try_with_time, jira_duration, hhmm
from common import ManagementError, Http, env

STATUSES = {"passed": "Passed", "failed": "Failed", "blocked": "Blocked",
            "pending": "Not Run", "in_progress": "In Progress"}
PRIORITIES = {"Critical": ["critical", "highest", "blocker"], "High": ["high"],
              "Medium": ["medium", "normal"], "Low": ["low", "lowest"]}
BDD = {"given": "BDD_GIVEN", "when": "BDD_WHEN", "then": "BDD_THEN", "and": "BDD_AND",
       "but": "BDD_BUT", "*": "BDD_STAR"}


class AIO(Adapter):
    name = "aio"
    attachment_limit = 100 * 1024 * 1024  # 100 MB (AIO KB, evidence upload)

    def __init__(self, project, dry_run=False):
        super().__init__(project, dry_run)
        base = env("AIO_API_URL", required=False, default="https://tcms.aiojiraapps.com/aio-tcms/api/v1")
        token = "dry-run" if dry_run else env("AIO_API_TOKEN")
        self.http = Http(base, {"Authorization": f"AioAuth {token}"}, dry_run=dry_run,
                         name="aio", interval=1.0)
        self.p = f"/project/{project}"
        self.statuses = {**STATUSES, **json.loads(os.environ.get("AIO_STATUSES", "{}") or "{}")}
        self._config = {}

    # --- instance catalogs (ids) ----------------------------------------------------
    def _catalog(self, path):
        if path not in self._config:
            self._config[path] = [] if self.dry_run else (self.http.get(f"{self.p}/config/{path}") or [])
        return self._config[path]

    def _id_by_name(self, path, names):
        for item in self._catalog(path):
            if str(item.get("name", "")).strip().lower() in names:
                return item["ID"]
        return None

    def _tags(self, names):
        if not names or self.dry_run:
            return []
        existing = {t["name"].lower(): t["ID"] for t in (self.http.get(f"{self.p}/tag") or [])}
        new = [{"name": n} for n in names if n.lower() not in existing]
        if new:
            for t in self.http.post(f"{self.p}/tag", json_body=new) or []:
                existing[t["name"].lower()] = t["ID"]
        return [{"tag": {"ID": existing[n.lower()]}} for n in names if n.lower() in existing]

    @staticmethod
    def _bdd_steps(gherkin):
        """Scenario gherkin -> AIO BDD steps. Tables and docstrings are appended to the previous step;
        Background and Examples go to the description."""
        steps, extra, section = [], [], None
        for line in gherkin.splitlines():
            l = line.strip()
            if not l:
                continue
            if re.match(r"^(Background|Examples|Scenarios):", l):
                section = l.split(":")[0]
                extra.append(l)
                continue
            if re.match(r"^(Scenario|Scenario Outline|Scenario Template|Example):", l):
                section = None
                continue
            word = l.split(" ", 1)[0].lower()
            if section is None and word in BDD:
                steps.append({"stepType": BDD[word], "gherkinKeyword": l.split(" ", 1)[0],
                              "bddStep": l.split(" ", 1)[1] if " " in l else ""})
            elif section is None and steps:
                steps[-1]["bddStep"] += "\n" + l
            else:
                extra.append(l)
        return steps, "\n".join(extra)

    # --- repository ------------------------------------------------------------------
    def create_folder(self, path):
        parts = [p for p in path.strip("/").split("/") if p]
        r = self.http.put(f"{self.p}/testcase/folder/hierarchy",
                          json_body={"baseFolderId": None, "folderHierarchy": parts})
        return r.get("ID")

    def create_case(self, case, folder_id, folder_path):
        case_status = os.environ.get("AIO_CASE_STATUS", "Published").strip().lower()
        body = {
            "title": remote_title(case, 255),
            "description": with_time(case.get("description", ""), case),
            "precondition": case.get("preconditions", ""),
            "folder": {"ID": folder_id},
            "tags": self._tags(case.get("tags", []) + ["k0lmenIA"]),
        }
        status_id = self._id_by_name("testcase/status", {case_status})
        if status_id:
            body["status"] = {"ID": status_id}
        elif not self.dry_run:
            raise ManagementError(f"AIO does not have the case status '{case_status}' (AIO_CASE_STATUS). "
                                  "Only published cases can be added to a cycle.")
        priority_id = self._id_by_name("testcase/priority", set(PRIORITIES.get(case.get("priority"), [])))
        if priority_id:
            body["priority"] = {"ID": priority_id}
        if case["type"] == "cucumber":
            steps, extra = self._bdd_steps(case["gherkin"])
            script_id = self._id_by_name("testcase/scripttype", {"bdd"})
            if script_id:
                body["scriptType"] = {"ID": script_id}
            body["steps"] = steps
            if extra:
                body["description"] = (body["description"] + "\n\n" + extra).strip()
        else:
            script_id = self._id_by_name("testcase/scripttype", {"classic"})
            if script_id:
                body["scriptType"] = {"ID": script_id}
            body["steps"] = [{"stepType": "TEXT", "step": p["action"], "data": p["data"],
                              "expectedResult": p["result"]} for p in case["steps"]]
        with_field = body
        if native_time() and case.get("estimate"):
            with_field = {**body, "estimatedEffort": case["estimate"]["seconds"]}  # in seconds
        r = try_with_time(lambda c: self.http.post(f"{self.p}/testcase", json_body=c), with_field, body)
        return {"key": r.get("key"), "id": r.get("ID")}

    def link_case_to_story(self, case, story):
        """AIO has no link endpoint: the case is read, the story is added to
        jiraRequirementIDs and the full case is saved again."""
        path = f'{self.p}/testcase/{case["key"]}/detail'
        detail = self.http.get(path)
        if self.dry_run:
            detail = {}
        current = [str(x) for x in detail.get("jiraRequirementIDs") or []]
        if story not in current:
            detail["jiraRequirementIDs"] = current + [story]
            self.http.put(path, json_body=detail)

    # --- cycles --------------------------------------------------------------------------
    def create_cycle(self, name, description="", folder_path=None):
        body = {"title": name[:255], "objective": description}
        if folder_path:
            parts = [p for p in folder_path.strip("/").split("/") if p]
            folder = self.http.put(f"{self.p}/testcycle/folder/hierarchy",
                                   json_body={"baseFolderId": None, "folderHierarchy": parts})
            if folder.get("ID") and not self.dry_run:
                body["folder"] = {"ID": folder["ID"]}
        r = self.http.post(f"{self.p}/testcycle/detail", json_body=body)
        return {"key": r.get("key"), "id": r.get("ID")}

    def link_cycle_to_story(self, cycle, story):
        path = f'{self.p}/testcycle/{cycle["key"]}/detail'
        detail = {} if self.dry_run else self.http.get(path)
        current = [str(x) for x in detail.get("jiraTaskIDs") or []]
        if story not in current:
            detail["jiraTaskIDs"] = current + [story]
            self.http.put(path, json_body=detail)

    def add_cases_to_cycle(self, cycle, cases):
        keys = [c["key"] for c in cases]
        errors = {}
        for i in range(0, len(keys), 100):
            r = self.http.post(f'{self.p}/testcycle/{cycle["key"]}/bulk/testrun/update',
                               params={"addCaseToCycle": "true"},
                               json_body={"testRuns": [{"testCaseKey": k} for k in keys[i:i + 100]]})
            errors.update(r.get("errors") or {})
        if errors:
            raise ManagementError("AIO could not add to the cycle: " +
                                  "; ".join(f"{k}: {v.get('message', v)}" for k, v in errors.items()))

    # --- results -------------------------------------------------------------------------
    def register_result(self, cycle, case, status, comment, evidence):
        r = self.http.post(f'{self.p}/testcycle/{cycle["key"]}/testcase/{case["key"]}/testrun',
                           params={"createNewRun": "true", "addCaseToCycle": "true"},
                           json_body={"testRunStatus": self.statuses[status], "isAutomated": True,
                                      "comments": [comment]})
        run_id = r.get("ID")
        not_uploaded = []
        for file in evidence:
            path = Path(file)
            if path.stat().st_size > self.attachment_limit:
                not_uploaded.append((file, "exceeds 100 MB"))
                continue
            mime = {"png": "image/png", "gif": "image/gif", "webm": "video/webm", "mp4": "video/mp4"}.get(
                path.suffix.lstrip(".").lower(), "application/octet-stream")
            try:
                with open(path, "rb") as f:
                    self.http.post(f'{self.p}/testcycle/{cycle["key"]}/testrun/{run_id}/attachment',
                                   files={"file": (path.name, f, mime)})
            except ManagementError as e:
                not_uploaded.append((file, str(e)[:200]))
        return not_uploaded
