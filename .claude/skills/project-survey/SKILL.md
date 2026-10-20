---
name: project-survey
description: How to survey an ENTIRE project via MCP (not a single story) to understand what it's about — sweep Jira and Confluence, Azure DevOps (Boards, Wiki and Repos), GitHub, GitLab, Linear, ClickUp, monday.com, Asana, Trello, Notion, YouTrack, Shortcut and Figma with scoped queries (JQL, WIQL, searches), sample large backlogs without reading them in full, extract modules, actors, flows, integrations, environments, decisions, backlog status and team, and detect ambiguities, contradictions, gaps and outdated documentation to turn them into prioritized questions for the team. Used by the project-researcher; also useful for anyone who has to get up to speed on a whole project.
---

# Project survey

The `context-research` skill investigates **one story** in depth. This skill surveys **a whole project** across its breadth: what the product is, what state it's in, who decides, what's clear and what isn't. The goal is that a newcomer understands the project in one read and knows **what to ask**.

Golden rule: **breadth first, depth only where needed.** A project can have thousands of issues; you don't read them all. You read the structure (epics, components, wiki, README) in full and sample the details with judgment.

## 1. Starting from a board URL

Most commonly the person pastes **a board URL** (board, dashboard, backlog or project). From it you get the tool and the project/board, without asking for anything else:

```
+------------------------------------------------------------------+------------------------------------------------+
| URL (examples)                                                   | What it gives you                              |
+==================================================================+================================================+
| .../jira/software/projects/PROJ/boards/12                        | Jira (atlassian), project PROJ, board 12       |
| .../jira/software/c/projects/PROJ/boards/12/backlog              | Jira, project PROJ (backlog)                   |
| .../jira/dashboards/10200                                        | Jira dashboard: read its gadgets for the       |
|                                                                  | project(s) and filters                         |
| .../browse/PROJ-123                                              | Jira, project PROJ (entry issue)               |
| dev.azure.com/ORG/PROJ/_boards/board/t/TEAM/Stories              | Azure DevOps, org ORG, project PROJ, team      |
| dev.azure.com/ORG/PROJ/_backlogs/backlog/TEAM/Epics              | Azure DevOps, project PROJ, Epics level        |
| dev.azure.com/ORG/PROJ/_sprints/...                              | Azure DevOps, project PROJ, iteration          |
| linear.app/COMPANY/team/ENG/board                                | Linear, team ENG                               |
| trello.com/b/abc123/dashboard                                    | Trello, board abc123                           |
| COMPANY.monday.com/boards/123456                                 | monday.com, board 123456                       |
| app.clickup.com/9999/v/b/li/123                                  | ClickUp, list/space                            |
| notion.so/COMPANY/Board-abc...                                   | Notion, that board's database                  |
| github.com/ORG/REPO/projects/4  ·  .../issues                    | GitHub Projects / issues of the ORG/REPO repo  |
| gitlab.com/GROUP/PROJ/-/boards                                   | GitLab, project GROUP/PROJ                     |
+------------------------------------------------------------------+------------------------------------------------+
```

Rules when starting from a URL:
- **Check the connector**: if the URL is from Jira and `atlassian` isn't active (or from Azure DevOps and `azure-devops` isn't, etc.), don't make things up: say what to activate (`npm run connector -- activate <name>`, `CONNECTORS.md`) and continue with what you do have.
- **A dashboard** is not a project: read its gadgets/filters to discover the project(s), the saved JQL/queries and the board(s) it references, and survey those.
- **A filtered board** (by a JQL, a team, a label) narrows the scope: survey what the board shows and say so (the project may have more than that board).
- If the URL isn't enough to identify the project (shortened, an SSO in between), ask for the project key or name.

## 2. Survey scope

Before reading, settle (from the request, the URL or the `.env`):

- **Which project**: Jira key (`PROJ`), Azure DevOps project (`ADO_PROJECT`), Confluence space, Linear team, the tool's workspace, repository (`REPO_PROVIDER` + `REPO_NAME`).
- **Time window** for what's "active": by default, the **last 90 days** (what moved in that period) + everything that's open.
- **Depth**: `quick` (structure + small sample, ~30 items), `normal` (default, ~80 items read in detail) or `full` (~200 items; only if the person asks for it: it uses a lot of tokens).
- **Optional focus**: a module, an epic or a release ("survey only the payments module").

If no tool is connected and there's no material in `input/`, no survey is possible: return which connectors to activate (`npm run configure` or `npm run connector -- activate <name>`, see `CONNECTORS.md`).

## 3. Reading order

```
+----+------------------------------+-----------------------------------------------+
| #  | Source                       | What for                                      |
+====+==============================+===============================================+
| 1  | input/documentation/         | If the project-documenter already built the   |
|    | (INDEX.md, project/)         | baseline, reuse it: don't reread what's still |
|    |                              | current. Read only what's marked Review or    |
|    |                              | what it doesn't cover                         |
+----+------------------------------+-----------------------------------------------+
| 2  | Wiki / Confluence / Notion   | Product vision, architecture, glossary,       |
|    | (root pages of the space)    | environments, integrations, decisions (ADR),  |
|    |                              | existing onboarding                           |
+----+------------------------------+-----------------------------------------------+
| 3  | Epics / Features             | The module map and the status of each one     |
|    | (all of them, title,         |                                               |
|    | status, short description    |                                               |
|    | only)                        |                                               |
+----+------------------------------+-----------------------------------------------+
| 4  | Active backlog (sample)      | What's being worked on, how stories are       |
|    |                              | written, which criteria are missing           |
+----+------------------------------+-----------------------------------------------+
| 5  | Open bugs (count + the       | Fragile areas of the product, severities      |
|    | Critical/High ones)          |                                               |
+----+------------------------------+-----------------------------------------------+
| 6  | Sprints / iterations /       | Team pace, next delivery, dates               |
|    | releases / versions          |                                               |
+----+------------------------------+-----------------------------------------------+
| 7  | Repository (README, docs/,   | Stack, how to run it, environments, CI, who   |
|    | CODEOWNERS, CI, the app's    | owns what. Read-only and without copying      |
|    | .env.example)                | secrets                                       |
+----+------------------------------+-----------------------------------------------+
| 8  | Figma (files linked from     | Designed screens and flows vs. what the       |
|    | epics or the wiki)           | backlog says                                  |
+----+------------------------------+-----------------------------------------------+
| 9  | Test management (Test        | What's tested today, whether there's          |
|    | Plans, Xray, output/)        | regression, whether there's automation        |
+----+------------------------------+-----------------------------------------------+
```

## 4. Queries per tool (scoped)

Always request **only the fields you need** and with a **result limit**. Paginate only if the count justifies it.

### Jira and Confluence (`atlassian` connector)

- Epics: `project = PROJ AND issuetype = Epic ORDER BY updated DESC` (all of them; fields `summary, status, description` trimmed, `fixVersions`).
- Counts by status and type (without fetching the issues): one search per relevant combination, or the total returned by the search with a small `maxResults`.
- Active backlog: `project = PROJ AND issuetype in (Story, Task) AND (statusCategory != Done OR updated >= -90d) ORDER BY priority DESC, updated DESC`.
- Open bugs: `project = PROJ AND issuetype = Bug AND statusCategory != Done ORDER BY priority DESC`.
- Stories without criteria / without a description (signs of ambiguity): `project = PROJ AND issuetype = Story AND statusCategory != Done AND description is EMPTY`.
- Blocked or with dependencies: `project = PROJ AND (status = Blocked OR issueLinkType = "is blocked by") AND statusCategory != Done`.
- Versions and sprints: the project's versions (`fixVersions` with their date) and the active sprint (`sprint in openSprints()`).
- Confluence: the space tree (titles); read the root pages and the ones named like *Vision*, *Architecture*, *Glossary*, *Environments*, *Onboarding*, *Decisions*, *Business rules*, *Integrations*. One CQL search per space and title (`space = SPACE AND title ~ "architecture"`), at most 15 pages.

### Azure DevOps (`azure-devops` connector)

- Work items via WIQL (`work-items` domain): epics and features (`[System.WorkItemType] IN ('Epic','Feature')`), active backlog (`[System.State] <> 'Closed' OR [System.ChangedDate] >= @Today - 90`), open bugs sorted by `Microsoft.VSTS.Common.Severity`.
- The project's iterations and areas (`work` domain): the current iteration and the upcoming ones with their dates; **areas** are often the best module map.
- Wiki (`wiki` domain): the page tree and the key pages (same titles as in Confluence).
- Repos (`repositories` domain): README, `docs/`, pipelines (`azure-pipelines.yml`) and recent PRs (titles).
- Test Plans (`test-plans` domain): existing plans and suites (names and counts only).
- Change date: `System.ChangedDate`; owner: `System.AssignedTo` (display name).

### Other tools

Use the equivalences from the table in the `context-research` skill (section *Where to look*): Linear projects/cycles, ClickUp lists and spaces, monday.com boards and groups, Asana projects and sections, Trello lists, Notion databases, YouTrack projects, Shortcut epics and iterations, GitHub/GitLab milestones and issues. In all of them: **the full structure, the details sampled**.

### Repository (`github`, `gitlab`, `azure-devops`, `atlassian` for Bitbucket)

Read-only and only the general stuff: `README`, `docs/`, `CONTRIBUTING`, `CODEOWNERS`, CI files, `docker-compose`, the app's `.env.example` (variable **names**, never values), first- and second-level folder structure. The fine-grained walk through code rules belongs to the `project-documenter`.

## 5. Sampling large backlogs

With more items than the chosen depth, read a **stratified** sample in detail (description, criteria and comments):

1. Everything **Critical/High** that's open (stories and bugs), up to a third of the sample.
2. What's in the **current sprint or iteration** and the next release.
3. **At least 2 items per active epic** (so no module is left blind).
4. The **most commented** or **most reopened** ones (a sign of discussion or ambiguity).
5. The rest, the most recently updated.

For everything else, counts only (by status, type, epic, priority). In the report, state **how many items there are, how many you read in detail and with what criterion**: the reader has to know how representative it is.

### Deep walk (epic → story → task → comments → links)

For each item in the sample, go down the hierarchy and bring back what helps to understand and test:

1. **Epic / feature**: title, status, description, and the list of **stories** under it (with their status). That gives you the modules and their progress (stories done / total).
2. **Story**: description, **acceptance criteria** (or their absence → gap), status, owner (display name), priority, and the list of **tasks/subtasks** with their status. Count the tasks; read in detail only those that contribute rules.
3. **Tasks / subtasks**: the technical work that implements the story (backend validation, endpoint, job); integrations and implementation details come from here.
4. **Comments** (on the epic, the story and the tasks): **from oldest to newest**. They're gold: decisions ("we agreed on 12 installments"), changes in criteria and open questions live here. A comment with a later **decision** overrides the description (cite who and when); an unresolved discussion is an ambiguity or a gap.
5. **Reference links**: every link that appears in the description or the comments — Confluence/Wiki, Figma, Google Docs/SharePoint, a repo, an API contract, an external URL. Follow them **one level only**:
   - With a connector (Confluence, Azure DevOps Wiki, Figma): open them and extract what's useful.
   - Private ones without a connector (Google Docs, SharePoint, someone else's Notion): **don't** make up their content; note them as a **Pending** reference with where they came from and which connector/permission would be needed.
   - Collect **all** the links in a reference list (type, title, URL, which item it came from, whether it was read): it's what a new QA will want to open first.

This feeds the report's **"Epics, stories and tasks"** section (the walked tree, with comments and links per item) and the **"Reference links"** section. Only one level deep from each item (its tasks and its direct links, not the links of the links), and from each source only what helps testing: don't copy whole pages.

## 6. What to extract

- **Product summary**: what it is, who it's for, what problem it solves, in one or two quotable sentences.
- **Modules**: from epics, areas, components or repo folders; each one with its status (in development, stable, planned), its progress (stories done / total) and its source.
- **Actors and roles** of the application (not of the team): who uses what.
- **Key flows** end to end (signup, purchase, approval…), with the epics or stories that implement them.
- **Integrations**: external systems (payment gateways, CRM, ERP, identity providers, queues, third parties) with the integration type if documented.
- **Environments**: dev, QA, staging, production, with their URL **only if it's public or in the documentation** (never credentials).
- **Stack and architecture** at a high level (from the repo and the wiki).
- **Team and whom to ask**: roles (PO, tech lead, QA lead, design) with the **display name** shown in the tool. No emails, phone numbers or personal data.
- **Recorded decisions**: what was decided, by whom, when and where (comment, ADR, page).
- **Backlog status**: totals by status and type, open bugs by severity, current sprint/iteration and upcoming releases with dates.
- **How it's tested today**: test plans, suites, automation, what isn't tested.
- **Glossary**: domain terms and acronyms, with their definition and source.
- **Timeline**: past and upcoming milestones (releases, sprints, go-lives).

Every piece of data **with its source** (`PROJ-12`, `Confluence "Architecture"`, `wiki/Environments`, `README.md`, `#318`). Whatever has no source doesn't go in.

## 7. Concept maps

So that it's clear **how the project is built** and **how it works**, build at least two maps (they go in the JSON's `maps` field and are drawn as diagrams in the report and the presentation):

- **Architecture**: the pieces of the system and how they connect — frontend(s), backend/services, database(s), queues, and **external systems** (payment gateway, identity, third parties). Group by layer (`group`: Frontend, Backend, Data, External). It comes from the repo (README, `docker-compose`, folders), the wiki and any existing diagrams.
- **How it works**: the **main flow** end to end (buy, sign up, approve, charge), step by step, with the important branches (ok / rejection / retry). It comes from the epics, the stories and the functional map.
- Optional: **modules / domain** (the product and its modules and submodules), useful when the architecture isn't documented.

Each map is a list of **nodes** (`id`, `label`, `group`, short `note`) and directed **links** (`from`, `to`, optional `label` on the arrow). The node without incoming arrows is the root; the columns and the legend are calculated automatically. **Build them only from what was surveyed**: if there's no evidence of the architecture, don't make it up — leave the modules map and record the gap as `AMB-XX`.

## 8. Ambiguities, contradictions and gaps

This is the most valuable part for a new QA. Classify each finding:

```
+-----------------+------------------------------------------+---------------------------------------------+
| Type            | What it is                               | Signals to find it                          |
+=================+==========================================+=============================================+
| Ambiguity       | A text allows more than one reading      | "fast", "easy", "etc.", "and/or", "as       |
|                 |                                          | appropriate", "similar to", "should",       |
|                 |                                          | "handle errors", criteria without numbers,  |
|                 |                                          | without an actor or an observable result    |
+-----------------+------------------------------------------+---------------------------------------------+
| Contradiction   | Two sources say different things         | Story vs. epic, description vs. comment     |
|                 |                                          | without an explicit decision, wiki vs.      |
|                 |                                          | backlog, Figma vs. story, README vs. wiki   |
|                 |                                          | (environments, versions)                    |
+-----------------+------------------------------------------+---------------------------------------------+
| Gap             | Something needed isn't in any source     | Stories without acceptance criteria,        |
|                 |                                          | modules without documentation, roles        |
|                 |                                          | without defined permissions, integrations   |
|                 |                                          | without a contract, no documented           |
|                 |                                          | environments, no definition of "done"       |
+-----------------+------------------------------------------+---------------------------------------------+
| Outdated        | The documentation doesn't reflect the    | Pages not edited for more than 6 months     |
|                 | current state                            | that describe modules still changing;       |
|                 |                                          | closed epics with open stories; releases    |
|                 |                                          | with a past date that were never closed     |
+-----------------+------------------------------------------+---------------------------------------------+
| Dependency      | Something blocks or depends on a third   | "blocked by" issues, integrations without a |
|                 | party or on another pending decision     | sandbox, "to be defined" decisions          |
+-----------------+------------------------------------------+---------------------------------------------+
```

For each one record: **ID** (`AMB-01`, `AMB-02`, …, numbered within the survey), **type**, **what** (concrete: *"PROJ-45 says 'the refund is immediate' and the 'Payment rules' page says 48 business hours"*), **sources** (both, if it's a contradiction), **impact** on testing (`High`, `Medium`, `Low`) and the **question** that resolves it.

Don't choose between two contradictory sources or fill a gap: **you ask**. If a specific story ends up with missing data, in addition to the `AMB-XX` mention that an `MI-XX` belongs in its sheet (it's recorded with `context-research` when someone works on that story).

## 9. Questions for the team

Every relevant ambiguity, contradiction or gap ends in a **question** (`Q-01`, `Q-02`, …):

- **Concrete and answerable** (*"Is a card refund immediate or does it take up to 48 business hours? (PROJ-45 vs. 'Payment rules')"*), never *"How do refunds work?"*.
- **To whom**: PO, tech lead, QA lead, design, business, security, infrastructure (the role; if the tool shows who it is, their display name).
- **Priority** (`Critical`, `High`, `Medium`, `Low`): Critical if it blocks testing something in the next delivery; High if it affects a main flow.
- **Why it matters** and the related **AMB-XX** or story.

Also, a short list of **getting-started questions** every new QA should ask even if they don't come from a finding, only those the documentation doesn't answer: access and environments, test data, definition of done, how bugs are reported and prioritized, what gets automated, deployment windows, who approves a release.

## 10. Risks for QA

From what was surveyed, the risks that affect how to test (not generic business risks): critical modules without criteria, integrations without a sandbox, critical bugs open in a main flow, upcoming releases with undefined stories, no test environments, no regression automation. Each one with a level (`High`, `Medium`, `Low`), reason and suggested mitigation.

## 11. Unavailable sources

If a connector isn't active, a page is private or the search returns an error, note the source as **Not accessible** with the reason and what would be needed (activating the connector, a permission, a token). Never replace an inaccessible source with assumptions. The report has to make clear **what was read and what wasn't**.

## 12. Hygiene

- **No secrets or personal data**: no tokens, passwords, emails, phone numbers or customer data that appear in tickets. If a ticket exposes them, mention that the ticket contains sensitive data without copying it.
- **Read-only**: you don't comment, change statuses or create anything in any tool.
- **Short quotes**: extract the rule or the sentence, don't paste whole pages.
- **Absolute dates** (`2026-10-19`), never "last week".
