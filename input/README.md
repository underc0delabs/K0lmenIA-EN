# input/ — the inputs for the agents

```
+------------------+------------------------------------------+---------------------------------------+
| Folder           | What goes in it                          | Suggested name                        |
+==================+==========================================+=======================================+
| `stories/`       | User stories with their acceptance       | `US-001-signup.md`                    |
|                  | criteria (`US-XXX-<topic>.md`)           |                                       |
+------------------+------------------------------------------+---------------------------------------+
| `documentation/` | Project documentation: the one the       | `INDEX.md`, `project/`, `api/`,       |
|                  | project-documenter builds (repository,   | `stories/<US or key>/dossier.md` (not |
|                  | stories, links, functional map) and the  | versioned)                            |
|                  | one you add by hand (manuals, minutes)   |                                       |
+------------------+------------------------------------------+---------------------------------------+
| `api/`           | API contracts, Postman collections and   | includes `auth-endpoints.md` and      |
|                  | environments, Bruno (folder with         | `demo.postman_collection.json`,       |
|                  | `bruno.json`) or Insomnia (`.json`/      | `demo-bruno/` and `demo.insomnia.json`|
|                  | `.yaml` export), Swagger/OpenAPI and     | (JSONPlaceholder), and a GraphQL demo |
|                  | GraphQL schemas (`.graphql`)             | (`demo-graphql.postman_collection`)   |
+------------------+------------------------------------------+---------------------------------------+
| `bugs/`          | Loose error observations to turn into    | `<topic>-observation.md`              |
|                  | reports                                  |                                       |
+------------------+------------------------------------------+---------------------------------------+
| `emails/`        | What has to arrive by email in each case | `expect-US-001.json`                  |
|                  | (email-verifier)                         |                                       |
+------------------+------------------------------------------+---------------------------------------+
| `logs/`          | Application logs for the log-analyst     | `app.log`, `access.log` (not          |
|                  | (not versioned)                          | versioned)                            |
+------------------+------------------------------------------+---------------------------------------+
```

If your team uses Jira or Azure DevOps, you don't need to copy the stories here: give the agents
the key (`PROJ-12`) or the work item ID (`1234`) with the connector active (see `CONNECTORS.md`).

## First use in five minutes

0. (Optional, recommended) Ask *"Document the project"*: the `project-documenter` reads the app repository, the stories and the website, and leaves the context in `documentation/` for the other agents (see the *Application repository* block of the `.env`).
1. Save a story in `input/stories/US-001-<topic>.md`: title, "As a / I want / So that" and the numbered acceptance criteria (`AC1`, `AC2`, …). To practice, you can use the "Crear cuenta" (create account) form of the practice site https://qarmy.ar/practica/automation (the `BASEURL` of `.env.example`).
2. In Claude Code, ask in order:
   - *"Analyze story US-001"* → ambiguities and questions for the PO in `output/story-analysis/`.
   - *"Generate the test cases for US-001"* → Excel spreadsheet, Markdown and coverage in `output/test-cases/manual/`.
   - *"Turn US-001 into BDD"* → `.feature` and coverage in `output/test-cases/bdd/`.
   - *"Run TC-001 of US-001 against <URL> in headless mode"* → HTML report with evidence in `output/runs/`.
3. For a bug, save your observation (even if it is messy) in `input/bugs/` and ask *"Write the bug report for input/bugs/<file>"* → `output/bug-reports/BUG-001.md`.

The `api/demo.postman_collection.json` collection points to JSONPlaceholder (a public test API): *"Run the demo collection from input/api"* runs it with Newman and leaves its report.
