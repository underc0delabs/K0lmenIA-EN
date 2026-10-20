# Test management: Xray, QMetry (QTM4J) and AIO Tests

> **Azure DevOps Test Plans** does not go through `management.py`: it is integrated through the `azure-devops` MCP connector (see [`CONNECTORS.md`](../../CONNECTORS.md#azure-devops)). From here only `to_azure_devops.py` is used, which converts the cases to the connector's format:
>
> ```bash
> python scripts/management/to_azure_devops.py output/test-cases/manual/cases-US-001.xlsx [--ids TC-001,TC-003]
> ```

k0lmenIA's own integration with the test management tools, on top of their **official APIs**. The same commands work for all four variants:

```
+---------------------------+-----------------+---------------------------------------+
| Tool                      | MANAGEMENT_TOOL | API                                   |
+===========================+=================+=======================================+
| Xray Cloud                | xray-cloud      | GraphQL v2 + Jira Cloud REST (links)  |
+---------------------------+-----------------+---------------------------------------+
| Xray Server / Data Center | xray-dc         | REST raven 1.0 + Jira REST v2         |
+---------------------------+-----------------+---------------------------------------+
| QMetry for Jira Cloud     | qtm4j           | Open API (rest/api/latest)            |
+---------------------------+-----------------+---------------------------------------+
| AIO Tests (Jira Cloud)    | aio             | Public REST v1                        |
+---------------------------+-----------------+---------------------------------------+
```

Two agents use it; they provide the context while the script does the mechanical work (cheap in tokens):

- **`test-manager`**: folders, cases, links to stories, cycles and cases inside the cycles.
- **`results-publisher`**: after `npm test` in k0lmena, uploads the status, comment and evidence of each case to the cycle.

## Configuration

Everything goes in the root `.env` (see `.env.example`, section *Test management*):

```
+---------------+------------------------------------------+
| Tool          | Required variables                       |
+===============+==========================================+
| All           | MANAGEMENT_TOOL, MANAGEMENT_PROJECT      |
|               | (Jira project key)                       |
+---------------+------------------------------------------+
| xray-cloud    | XRAY_CLOUD_CLIENT_ID,                    |
|               | XRAY_CLOUD_CLIENT_SECRET, JIRA_BASE_URL, |
|               | JIRA_EMAIL, JIRA_API_TOKEN               |
+---------------+------------------------------------------+
| xray-dc       | XRAY_DC_URL and XRAY_DC_TOKEN (or        |
|               | XRAY_DC_USER and XRAY_DC_PASSWORD)       |
+---------------+------------------------------------------+
| qtm4j         | QTM4J_API_KEY (and QTM4J_BASE_URL if it  |
|               | is not the US region)                    |
+---------------+------------------------------------------+
| aio           | AIO_API_TOKEN                            |
+---------------+------------------------------------------+
```

Dependency: `requests` (it is in `requirements.txt`; the script installs it if missing).

## Commands

```bash
python scripts/management/management.py [--tool X] [--dry-run] <command> [options]

folder           --path "US-001 Signup/Manual"
upload-cases     --source <cases.xlsx | scenarios.feature> --folder "US-001 Signup" [--story PROJ-12] [--ids TC-001,TC-002] [--trace US-001]
link             --story PROJ-12 (--cases PROJ-45,PROJ-46 | --cycle PROJ-60)
create-cycle     --name "US-001 Sprint 5" [--story PROJ-12] [--cases ... | --trace US-001 [--ids ...]]
add-to-cycle     --cycle PROJ-60 (--cases ... | --trace US-001 [--ids ...])
extract-results  --report tools/k0lmena/reports/web/cucumber-report.json
publish-results  --cycle PROJ-60 --results output/management/results-<date>.json [--trace US-001] [--no-video]
```

- **Folders without a leading slash** (`"US-001 Signup/Manual"`): Git Bash converts arguments that start with `/` into Windows paths. The script detects it and warns you.
- **`--dry-run`** shows each request without sending it. Use it the first time with each tool.
- Every command prints a JSON with the result (the agents read it).

## How it all connects

```
cases-US-001.xlsx / US-001.feature ──upload-cases──► folder + cases (linked to PROJ-12)
                                                     │
                     output/management/US-001-<tool>.json   (TC-001 → PROJ-45, cycles created)
                                                     │
create-cycle ──► cycle with the cases (linked to PROJ-12)
                                                     │
npm test (k0lmena) ──► cucumber-report.json ──extract-results──► results + evidence
                                                     │
publish-results ──► status + comment + screenshot (and video if it failed) on each case of the cycle
```

- **Traceability** (`output/management/<US>-<tool>.json`): which `TC-XXX` is which remote key. It avoids duplicates (a case already uploaded is not created again) and makes it possible to publish results.
- **Scenario → case**: by the scenario's `@TC-XXX` tag (via traceability) or by a tag with the direct key (`@PROJ-45`). Since `TC-XXX` IDs repeat in every story, with `--trace US-001` only the scenarios that carry `@US-001` are translated; the rest go to `no_linked_case` with the reason (another story, no `@US`, case not uploaded). If a run covers several stories, publish once per story.
- **Safe retries**: `upload-cases` records each case in the traceability as soon as it creates it; if the link to the story fails, it is flagged and retried when you run the same command again, without duplicating the case. Attachments are resent in full if the API asks for a retry (429/5xx) and network cuts are retried automatically.
- **Evidence**: a screenshot always; a GIF of the walkthrough if the run was done with `EVIDENCE=both`; the full video only if the case failed. If a file exceeds the tool's limit, it is skipped and you are warned.

```
+--------------------+------------------------------------------+-----------------------+---------------------------------+
| Concept            | Xray Cloud / Server-DC                   | QTM4J                 | AIO Tests                       |
+====================+==========================================+=======================+=================================+
| Folder             | Test Repository folder                   | Test case folder      | Case folder                     |
+--------------------+------------------------------------------+-----------------------+---------------------------------+
| Case               | Test issue (Manual or Cucumber)          | Test case             | Case (Classic/BDD, Published)   |
+--------------------+------------------------------------------+-----------------------+---------------------------------+
| Cycle              | Test Execution issue                     | Test cycle            | Test cycle                      |
+--------------------+------------------------------------------+-----------------------+---------------------------------+
| Case - story       | "Test(s)" issue link (coverage)          | Requirement link      | jiraRequirementIDs              |
+--------------------+------------------------------------------+-----------------------+---------------------------------+
| Cycle - story      | "Relates" issue link                     | Requirement link      | jiraTaskIDs                     |
+--------------------+------------------------------------------+-----------------------+---------------------------------+
| Limit per          | Cloud: not documented / DC: 10 MB (Jira) | Not documented        | 100 MB                          |
| attachment         |                                          |                       |                                 |
+--------------------+------------------------------------------+-----------------------+---------------------------------+
```

Statuses: `passed` / `failed` / `blocked` / `pending` are mapped to PASSED / FAILED / ABORTED / TODO (Xray Cloud), PASS / FAIL / ABORTED / TODO (Xray DC), Pass / Fail / Blocked / Not Executed (QTM4J) and Passed / Failed / Blocked / Not Run (AIO). If your instance uses custom statuses, map them with `XRAY_STATUSES`, `QTM4J_STATUSES` or `AIO_STATUSES` (JSON).

## Validation status

The integration was built from the official documentation and tested with `--dry-run` and with a response simulator (including idempotency and the automatic addition of cases missing from the cycle), **without a real instance**. The first time you use each tool, run `--dry-run` first and then confirm these points, which the documentation does not make entirely clear:

```
+---------------+------------------------------------------+---------------------------------------+
| Tool          | Point to confirm                         | Adjustment if it does not match       |
+===============+==========================================+=======================================+
| xray-cloud    | The case-story link ends up with the     | XRAY_LINK_INVERT=1                    |
|               | story saying "is tested by"              |                                       |
+---------------+------------------------------------------+---------------------------------------+
| xray-cloud    | The link type is called "Test" (in       | XRAY_LINK_CASE=Tests                  |
|               | migrated instances it may be "Tests")    |                                       |
+---------------+------------------------------------------+---------------------------------------+
| xray-cloud    | The plain-text description is accepted   | Report it so it can be adapted        |
|               | (Jira Cloud v3 sometimes requires ADF    |                                       |
|               | format)                                  |                                       |
+---------------+------------------------------------------+---------------------------------------+
| xray-cloud    | The maximum evidence size (videos)       | MANAGEMENT_ATTACHMENT_LIMIT_MB        |
+---------------+------------------------------------------+---------------------------------------+
| xray-dc       | The field names "Test Type", "Cucumber   | Report it so it can be adapted        |
|               | Test Type" and "Cucumber Scenario"       |                                       |
+---------------+------------------------------------------+---------------------------------------+
| xray-dc       | Your Jira attachment limit (10 MB by     | MANAGEMENT_ATTACHMENT_LIMIT_MB        |
|               | default)                                 |                                       |
+---------------+------------------------------------------+---------------------------------------+
| all Xray      | Whether "blocked" should be ABORTED (or  | XRAY_STATUSES={"blocked":"BLOCKED"}   |
|               | a custom status such as BLOCKED)         |                                       |
+---------------+------------------------------------------+---------------------------------------+
| all Xray      | The priorities of your Jira (Highest,    | MANAGEMENT_PRIORITIES or              |
|               | High, Medium, Low)                       | MANAGEMENT_SEND_PRIORITY=0            |
+---------------+------------------------------------------+---------------------------------------+
| qtm4j         | Whether the apiKey header is enough      | Report it so it can be adapted        |
|               | (without Jira Basic auth)                |                                       |
+---------------+------------------------------------------+---------------------------------------+
| qtm4j         | Whether loading bddScenario leaves the   | Report it so it can be adapted        |
|               | case as BDD in the interface             |                                       |
+---------------+------------------------------------------+---------------------------------------+
| qtm4j         | Whether the Pass and WIP results exist   | QTM4J_STATUSES                        |
|               | (besides Fail, Blocked and Not Executed) |                                       |
+---------------+------------------------------------------+---------------------------------------+
| aio           | Whether the "Published" case status      | AIO_CASE_STATUS                       |
|               | exists (without it, cases cannot be      |                                       |
|               | added to cycles)                         |                                       |
+---------------+------------------------------------------+---------------------------------------+
| aio           | Whether saving the full case when        | Report it so it can be adapted        |
|               | linking the story overwrites other       |                                       |
|               | fields                                   |                                       |
+---------------+------------------------------------------+---------------------------------------+
```
