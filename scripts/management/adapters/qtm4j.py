"""QMetry Test Management for Jira Cloud (QTM4J): Open API (/rest/api/latest).

Docs: https://app.swaggerhub.com/apis-docs/qmetry-ada/qtm4j_cloud/restapi
      https://support.smartbear.com/qmetry-test-management-for-jira-cloud/docs/

Mapping:
- folder   -> test case folder (created level by level)
- case     -> test case (manual steps; BDD: it is created and then bddScenario is loaded in the version)
- cycle    -> test cycle
- case/cycle-story link -> requirements/link with JQL by key (the Jira id is not needed)
- result   -> test case execution of the cycle (executionResultId + comment) and attachments via a signed S3 URL
Rate limit: 10,000 calls per hour for the whole instance.
"""
import json
import os
from pathlib import Path

from adapters.base import Adapter, remote_title, with_time, native_time, try_with_time, jira_duration, hhmm
from common import ManagementError, Http, env, need

# normalized status -> QTM4J defaultName (the "name" may be customized)
STATUSES = {"passed": "Pass", "failed": "Fail", "blocked": "Blocked",
            "pending": "Not Executed", "in_progress": "WIP"}
PRIORITIES = {"Critical": ["blocker", "critical", "highest"], "High": ["high", "major"],
              "Medium": ["medium", "normal"], "Low": ["low", "minor", "lowest"]}


class QTM4J(Adapter):
    name = "qtm4j"

    def __init__(self, project, dry_run=False):
        super().__init__(project, dry_run)
        base = env("QTM4J_BASE_URL", required=False, default="https://qtmcloud.qmetry.com")
        key = "dry-run" if dry_run else env("QTM4J_API_KEY")
        self.http = Http(f"{base.rstrip('/')}/rest/api/latest",
                         {"apiKey": key, "Content-Type": "application/json"}, dry_run=dry_run, name="qtm4j")
        self.statuses = {**STATUSES, **json.loads(os.environ.get("QTM4J_STATUSES", "{}") or "{}")}
        self._project_id = None
        self._cache = {}

    # --- utilities -----------------------------------------------------------------------
    @property
    def project_id(self):
        if self._project_id is None:
            if self.dry_run:
                self._project_id = 0
            else:
                r = self.http.post("/projects", params={"maxResults": 100},
                                   json_body={"search": self.project, "qmetryEnabled": True})
                for p in r.get("data", []):
                    if p.get("key") == self.project:
                        self._project_id = p["id"]
                if self._project_id is None:
                    raise ManagementError(f"QTM4J cannot find the project {self.project} (is QMetry enabled?).")
        return self._project_id

    def _list(self, path):
        if path not in self._cache:
            r = [] if self.dry_run else self.http.get(f"/projects/{self.project_id}/{path}")
            self._cache[path] = r.get("data", r) if isinstance(r, dict) else r
        return self._cache[path]

    def _id_by_name(self, path, names, field="name"):
        for item in self._list(path) or []:
            if str(item.get(field, "")).strip().lower() in names:
                return item["id"]
        return None

    def _labels(self, names):
        ids = []
        for n in names:
            i = self._id_by_name("labels", {n.lower()})
            if i is None and not self.dry_run:
                i = self.http.post(f"/projects/{self.project_id}/labels", json_body={"name": n}).get("id")
                self._cache.pop("labels", None)
            if i is not None:
                ids.append(i)
        return ids

    def _case(self, case):
        """key -> {id, versionNo} (the operations use the internal id and the version)."""
        if case.get("id") and case.get("versionNo"):
            return case
        if self.dry_run:
            return {**case, "id": f'id({case["key"]})', "versionNo": 1}
        r = self.http.post("/testcases/search", params={"maxResults": 1},
                           json_body={"filter": {"projectId": self.project_id, "key": case["key"]}})
        data = (r.get("data") or [])
        if not data:
            raise ManagementError(f"QTM4J cannot find the case {case['key']}.")
        d = data[0]
        return {**case, "id": d["id"], "versionNo": (d.get("version") or {}).get("versionNo", 1)}

    def _cycle_id(self, cycle):
        if cycle.get("id"):
            return cycle["id"]
        if self.dry_run:
            return f'id({cycle["key"]})'
        r = self.http.post("/testcycles/search", params={"maxResults": 1},
                           json_body={"filter": {"projectId": self.project_id, "key": cycle["key"]}})
        data = r.get("data") or []
        if not data:
            raise ManagementError(f"QTM4J cannot find the cycle {cycle['key']}.")
        return data[0]["id"]

    def _folder(self, kind, path):
        """Creates the folder path level by level (kind: testcase-folders | testcycle-folders)."""
        tree = [] if self.dry_run else self.http.get(f"/projects/{self.project_id}/{kind}").get("data", [])
        parent_id, children = -1, tree
        for part in [p for p in path.strip("/").split("/") if p]:
            existing = next((f for f in children if f.get("name") == part), None)
            if existing:
                parent_id, children = existing["id"], existing.get("children") or []
            else:
                r = self.http.post(f"/projects/{self.project_id}/{kind}",
                                   json_body={"folderName": part, "parentId": parent_id})
                parent_id, children = r.get("id"), []
        return parent_id

    # --- repository ----------------------------------------------------------------------
    def create_folder(self, path):
        return self._folder("testcase-folders", path)

    def create_case(self, case, folder_id, folder_path):
        body = {
            "projectId": self.project_id,
            "summary": remote_title(case, 255),
            "description": with_time(case.get("description", ""), case),
            "precondition": case.get("preconditions", ""),
            "folderId": folder_id,
            "labels": self._labels(case.get("tags", []) + ["k0lmenIA"]),
        }
        priority = self._id_by_name("priorities", set(PRIORITIES.get(case.get("priority"), [])))
        if priority:
            body["priority"] = priority
        if case["type"] != "cucumber":
            body["steps"] = [{"stepDetails": p["action"], "testData": p["data"],
                              "expectedResult": p["result"]} for p in case["steps"]]
        with_field = body
        if native_time() and case.get("estimate"):
            with_field = {**body, "estimatedTime": hhmm(case["estimate"]["minutes"])}  # HH:mm
        r = try_with_time(lambda c: self.http.post("/testcases", json_body=c), with_field, body)
        created = {"key": r.get("key"), "id": r.get("id"), "versionNo": r.get("versionNo", 1)}
        if case["type"] == "cucumber":
            self.http.put(f'/testcases/{created["id"]}/versions/{created["versionNo"]}',
                          json_body={"bddScenario": case["gherkin"]})
        return created

    def _link_jql(self, story):
        return {"filter": {"jql": f"key in ('{story}')"}}

    def link_case_to_story(self, case, story):
        c = self._case(case)
        r = self.http.post(f'/testcases/{c["id"]}/version/{c["versionNo"]}/requirements/link',
                           json_body=self._link_jql(story))
        if isinstance(r, dict) and r.get("warningMessages"):
            raise ManagementError(f"QTM4J did not link {case['key']} to {story}: {r['warningMessages']}")

    # --- cycles --------------------------------------------------------------------------
    def create_cycle(self, name, description="", folder_path=None):
        body = {"projectId": self.project_id, "summary": name[:255], "description": description}
        if folder_path:
            body["folderId"] = self._folder("testcycle-folders", folder_path)
        r = self.http.post("/testcycles", json_body=body)
        return {"key": r.get("key"), "id": r.get("id")}

    def link_cycle_to_story(self, cycle, story):
        self.http.post(f"/testcycles/{self._cycle_id(cycle)}/requirements/link", json_body=self._link_jql(story))

    def add_cases_to_cycle(self, cycle, cases):
        cycle_id = self._cycle_id(cycle)
        resolved = [self._case(c) for c in cases]
        for i in range(0, len(resolved), 100):
            self.http.post(f"/testcycles/{cycle_id}/testcases", json_body={
                "testCases": [{"id": c["id"], "versionNo": c["versionNo"]} for c in resolved[i:i + 100]]})

    # --- results -------------------------------------------------------------------------
    def _execution_id(self, cycle_id, case):
        if self.dry_run:
            return "DRY-EXEC"
        start = 0
        while True:
            r = self.http.post(f"/testcycles/{cycle_id}/testcases/search",
                               params={"startAt": start, "maxResults": 100}, json_body={"filter": {}})
            for item in r.get("data", []):
                if item.get("key") == case["key"]:
                    return item.get("testCaseExecutionId")
            start += 100
            if start >= r.get("total", 0):
                return None

    def register_result(self, cycle, case, status, comment, evidence):
        cycle_id = self._cycle_id(cycle)
        execution = self._execution_id(cycle_id, case)
        if execution is None:  # the case was not in the cycle: it is added and looked up again
            self.add_cases_to_cycle({**cycle, "id": cycle_id}, [case])
            execution = self._execution_id(cycle_id, case)
        if execution is None:
            raise ManagementError(f"Cannot find the run of {case['key']} in {cycle['key']}.")
        result_id = self._id_by_name("execution-results", {self.statuses[status].lower()}, field="defaultName") \
            or self._id_by_name("execution-results", {self.statuses[status].lower()})
        if result_id is None and not self.dry_run:
            raise ManagementError(f"QTM4J does not have the result '{self.statuses[status]}' (configurable with QTM4J_STATUSES).")
        self.http.put(f"/testcycles/{cycle_id}/testcase-executions/{execution}",
                      json_body={"executionResultId": result_id, "comment": comment[:30000]})
        not_uploaded = []
        for file in evidence:
            path = Path(file)
            try:
                signed = self.http.get(f"/testcycles/{cycle_id}/testcase-executions/attachments/url",
                                       params={"projectId": self.project_id, "fileName": path.name,
                                               "testcaseExecutionId": execution})
                if self.dry_run:
                    print(f"[dry-run] S3 POST (multipart) {path.name}")
                    continue
                requests = need("requests")
                with open(path, "rb") as f:
                    s3 = requests.post(signed["endpoint_url"], data=signed["params"],
                                       files={"file": (path.name, f)}, timeout=300)
                if s3.status_code not in (200, 201, 204):
                    not_uploaded.append((file, f"S3 responded {s3.status_code}"))
            except ManagementError as e:
                not_uploaded.append((file, str(e)[:200]))
        return not_uploaded
