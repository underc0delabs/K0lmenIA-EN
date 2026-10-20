"""Xray Cloud: GraphQL v2 (+ REST v2 to authenticate) and Jira Cloud REST for the links.

Docs: https://docs.getxray.app/display/XRAYCLOUD/GraphQL+API
      https://us.xray.cloud.getxray.app/doc/graphql/

Mapping:
- folder   -> Test Repository folder (identified by path, e.g. "/US-001/Signup")
- case     -> "Test" issue (Manual with steps or Cucumber with gherkin)
- cycle    -> "Test Execution" issue
- case-story link   -> Jira issue link of type "Test" (Xray coverage)
- cycle-story link  -> Jira issue link of type "Relates" (Xray does not define coverage for executions)
"""
import base64
import json
import os
from pathlib import Path

from adapters.base import Adapter, remote_title, with_time, native_time, try_with_time, jira_duration, hhmm
from common import ManagementError, Http, env

STATUSES = {
    "passed": "PASSED", "failed": "FAILED", "pending": "TODO",
    "in_progress": "EXECUTING", "blocked": "ABORTED",
}
PRIORITIES = {"Critical": "Highest", "High": "High", "Medium": "Medium", "Low": "Low"}


class XrayCloud(Adapter):
    name = "xray-cloud"

    def __init__(self, project, dry_run=False):
        super().__init__(project, dry_run)
        base = env("XRAY_CLOUD_URL", required=False, default="https://xray.cloud.getxray.app")
        self.xray = Http(base, dry_run=dry_run, name="xray")
        self.statuses = {**STATUSES, **json.loads(os.environ.get("XRAY_STATUSES", "{}") or "{}")}
        self.priorities = {**PRIORITIES, **json.loads(os.environ.get("MANAGEMENT_PRIORITIES", "{}") or "{}")}
        self.case_link_type = env("XRAY_LINK_CASE", required=False, default="Test")
        self.cycle_link_type = env("XRAY_LINK_CYCLE", required=False, default="Relates")
        self._jira = None
        self._project_id = None
        self._ids = {}
        if not dry_run:
            token = self.xray.post("/api/v2/authenticate", json_body={
                "client_id": env("XRAY_CLOUD_CLIENT_ID"), "client_secret": env("XRAY_CLOUD_CLIENT_SECRET")})
            token = token if isinstance(token, str) else token.get("text", "").strip('"')
            self.xray.headers["Authorization"] = f"Bearer {token}"

    # --- utilities ---------------------------------------------------------------
    def gql(self, query, variables=None):
        if self.dry_run:
            print(f"[dry-run] xray GraphQL {' '.join(query.split())[:300]} vars={json.dumps(variables or {}, ensure_ascii=False)[:400]}")
            return {}
        r = self.xray.post("/api/v2/graphql", json_body={"query": query, "variables": variables or {}})
        if r.get("errors"):
            raise ManagementError("Xray GraphQL: " + "; ".join(e.get("message", "") for e in r["errors"]))
        return r.get("data") or {}

    @property
    def jira(self):
        """Jira Cloud REST (email + API token): only for the issue links."""
        if self._jira is None and self.dry_run:
            self._jira = Http("https://jira.dry-run", dry_run=True, name="jira")
        if self._jira is None:
            token = base64.b64encode(f'{env("JIRA_EMAIL")}:{env("JIRA_API_TOKEN")}'.encode()).decode()
            self._jira = Http(env("JIRA_BASE_URL"), {"Authorization": f"Basic {token}"},
                              dry_run=self.dry_run, name="jira")
        return self._jira

    @property
    def project_id(self):
        if self._project_id is None:
            if self.dry_run:
                self._project_id = "DRY-PROJECT"
            else:
                d = self.gql("query($p:String){ getProjectSettings(projectIdOrKey:$p){ projectId } }",
                             {"p": self.project})
                self._project_id = (d.get("getProjectSettings") or {}).get("projectId")
                if not self._project_id:
                    raise ManagementError(f"Xray cannot find the project {self.project}.")
        return self._project_id

    def issue_id(self, item):
        """Xray mutations need the numeric issue id; we resolve it from the key."""
        if item.get("id") and not str(item["id"]).startswith("DRY"):
            return str(item["id"])
        key = item["key"]
        if self.dry_run:
            return f"id({key})"
        if key not in self._ids:
            r = self.jira.get(f"/rest/api/3/issue/{key}", params={"fields": "id"})
            self._ids[key] = str(r["id"])
        return self._ids[key]

    def _link(self, link_type, source_key, destination_key):
        """Jira issue link. With XRAY_LINK_INVERT=1 the direction is inverted if in your
        Jira the link ends up backwards (the story must show 'is tested by')."""
        inward, outward = source_key, destination_key
        if os.environ.get("XRAY_LINK_INVERT", "").strip() in ("1", "true", "on"):
            inward, outward = outward, inward
        self.jira.post("/rest/api/3/issueLink", json_body={
            "type": {"name": link_type}, "inwardIssue": {"key": inward}, "outwardIssue": {"key": outward}})

    # --- repository ---------------------------------------------------------------
    def create_folder(self, path):
        parts = [p for p in path.strip("/").split("/") if p]
        current = ""
        for part in parts:
            current += "/" + part
            exists = False
            if not self.dry_run:
                try:
                    d = self.gql("query($p:String,$r:String!){ getFolder(projectId:$p, path:$r){ path } }",
                                 {"p": self.project_id, "r": current})
                    exists = bool((d.get("getFolder") or {}).get("path"))
                except ManagementError:
                    exists = False
            if not exists:
                try:
                    self.gql("mutation($p:String,$r:String!){ createFolder(projectId:$p, path:$r){ folder{ path } warnings } }",
                             {"p": self.project_id, "r": current})
                except ManagementError as e:
                    if "exist" not in str(e).lower():
                        raise
        return "/" + "/".join(parts)

    def create_case(self, case, folder_id, folder_path):
        description = case.get("description", "")
        if case.get("preconditions"):
            description += f"\n\nPreconditions: {case['preconditions']}"
        fields = {
            "summary": remote_title(case, 250),
            "project": {"key": self.project},
            "description": with_time(description.strip() or case["title"], case),
            "labels": [e.replace(" ", "_") for e in case.get("tags", [])] + ["k0lmenIA"],
        }
        priority = self.priorities.get(case.get("priority"))
        if priority and os.environ.get("MANAGEMENT_SEND_PRIORITY", "1") != "0":
            fields["priority"] = {"name": priority}
        if case["type"] == "cucumber":
            query = ("mutation($j:JSON!,$g:String,$f:String){ createTest(testType:{name:\"Cucumber\"}, "
                     "gherkin:$g, folderPath:$f, jira:$j){ test{ issueId jira(fields:[\"key\"]) } warnings } }")
            variables = {"j": {"fields": fields}, "g": case["gherkin"], "f": folder_path}
        else:
            steps = [{"action": p["action"], "data": p["data"], "result": p["result"]} for p in case["steps"]]
            query = ("mutation($j:JSON!,$s:[CreateStepInput],$f:String){ createTest(testType:{name:\"Manual\"}, "
                     "steps:$s, folderPath:$f, jira:$j){ test{ issueId jira(fields:[\"key\"]) } warnings } }")
            variables = {"j": {"fields": fields}, "s": steps, "f": folder_path}
        # Estimated time in the Jira Original Estimate (if the project has time tracking).
        with_field = variables
        if native_time() and case.get("estimate"):
            with_field = {**variables, "j": {"fields": {**fields, "timetracking": {"originalEstimate": jira_duration(case["estimate"]["minutes"])}}}}
        d = try_with_time(lambda v: self.gql(query, v), with_field, variables)
        if self.dry_run:
            return {"key": f'DRY-{case["id"]}', "id": None}
        test = d["createTest"]["test"]
        return {"key": test["jira"]["key"], "id": str(test["issueId"])}

    def link_case_to_story(self, case, story):
        self._link(self.case_link_type, case["key"], story)

    # --- cycles -------------------------------------------------------------------
    def create_cycle(self, name, description="", folder_path=None):
        fields = {"summary": name, "project": {"key": self.project}, "labels": ["k0lmenIA"]}
        if description:
            fields["description"] = description
        d = self.gql("mutation($j:JSON!){ createTestExecution(jira:$j){ testExecution{ issueId jira(fields:[\"key\"]) } warnings } }",
                     {"j": {"fields": fields}})
        if self.dry_run:
            return {"key": "DRY-CYCLE", "id": None}
        te = d["createTestExecution"]["testExecution"]
        return {"key": te["jira"]["key"], "id": str(te["issueId"])}

    def link_cycle_to_story(self, cycle, story):
        self._link(self.cycle_link_type, cycle["key"], story)

    def add_cases_to_cycle(self, cycle, cases):
        ids = [self.issue_id(c) for c in cases]
        for i in range(0, len(ids), 100):
            self.gql("mutation($e:String!,$t:[String]){ addTestsToTestExecution(issueId:$e, testIssueIds:$t){ addedTests warning } }",
                     {"e": self.issue_id(cycle), "t": ids[i:i + 100]})

    # --- results ------------------------------------------------------------------
    def _test_run_id(self, cycle, case):
        query = "query($t:String,$e:String){ getTestRun(testIssueId:$t, testExecIssueId:$e){ id } }"
        variables = {"t": self.issue_id(case), "e": self.issue_id(cycle)}
        if self.dry_run:
            self.gql(query, variables)
            return "DRY-RUN"
        run = self.gql(query, variables).get("getTestRun")
        if not run:  # the case was not in the cycle: it is added and looked up again
            self.add_cases_to_cycle(cycle, [case])
            run = self.gql(query, variables).get("getTestRun")
        if not run:
            raise ManagementError(f"Cannot find the run of {case['key']} in {cycle['key']}.")
        return run["id"]

    def register_result(self, cycle, case, status, comment, evidence):
        run_id = self._test_run_id(cycle, case)
        self.gql("mutation($i:String!,$s:String!){ updateTestRunStatus(id:$i, status:$s) }",
                 {"i": run_id, "s": self.statuses[status]})
        self.gql("mutation($i:String!,$c:String!){ updateTestRunComment(id:$i, comment:$c) }",
                 {"i": run_id, "c": comment})
        not_uploaded = []
        limit = float(os.environ.get("MANAGEMENT_ATTACHMENT_LIMIT_MB", "0") or 0) * 1024 * 1024
        for file in evidence:
            path = Path(file)
            if limit and path.stat().st_size > limit:
                not_uploaded.append((file, f"exceeds {limit / 1048576:.0f} MB"))
                continue
            mime = {"png": "image/png", "gif": "image/gif", "webm": "video/webm", "mp4": "video/mp4"}.get(path.suffix.lstrip(".").lower(),
                                                                                     "application/octet-stream")
            data = "<base64>" if self.dry_run else base64.b64encode(path.read_bytes()).decode()
            try:
                self.gql("mutation($i:String!,$e:[AttachmentDataInput]!){ addEvidenceToTestRun(id:$i, evidence:$e){ addedEvidence warnings } }",
                         {"i": run_id, "e": [{"filename": path.name, "mimeType": mime, "data": data}]})
            except ManagementError as e:
                not_uploaded.append((file, str(e)[:200]))
        return not_uploaded
