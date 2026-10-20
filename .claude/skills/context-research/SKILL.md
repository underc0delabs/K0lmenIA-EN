---
name: context-research
description: How to thoroughly research a story or feature before analyzing it, planning it, writing cases or automating it — the project documentation that the project-documenter builds in input/documentation/ (index, story dossier, code rules, messages, functional map), the story in Jira, Azure DevOps (Azure Boards) or another management tool (Linear, ClickUp, monday.com, Asana, Trello, Notion, YouTrack, Shortcut, GitHub or GitLab Issues) with its comments, subtasks, epic and linked issues, the related Confluence pages, the Figma designs, API contracts and local documentation — and how to record what is missing as "Missing information" (MI-XX) in a reusable context file. Use it in story-analyst, test-strategist, the case generators and the mappers when they work on a story.
---

# Context research

Before assuming, **search**. A story almost never has all the information in its description: decisions are usually in the comments, rules in the epic or in Confluence, the exact copy in Figma. This skill defines where to search, in what order, and how to record **what was found** and **what is missing**.

## 1. Is there already a context file?

Look for `output/context/context-<US>.md`. `<US>` is the `US-XXX` used by the cases and reports; if the story only has a tool key, use the key (`context-PROJ-12.md`). Before creating a context file, Grep for the key and the `US-XXX` in `output/context/` so you don't duplicate it, and write both in the **Story** header.

- If it exists and the story **has not changed** since then (compare the story's last-modified date —`updated` in Jira; for the other tools, see the equivalence table; if the story is a file in `input/stories/`, its modification date— with the context file's date) and the dossier in `input/documentation/` is not newer than the context file, **reuse it** and don't research again: it saves tokens.
- If it changed, or the person asks to update it, research again and replace the context file (keep the `MI-XX` items that are still open, with the same ID).

## 2. First, the project documentation

If `input/documentation/INDEX.md` exists (built by the `project-documenter` agent), read it **before** any other source: it says what context there is, where it comes from and whether it is current.

- **Story dossier** (`input/documentation/stories/<US or key>/dossier.md`): it already includes the story with its comments, decisions, relations, links, PRs and commits, touched files, screens, contradictions and testing hints. If its `updated` date is later than the story's last change, **use it as the main source** and don't go through Jira or Azure DevOps again (it saves tokens); if it is earlier, review only what changed afterwards.
- **Project documents** (`project/`): open only the ones that help with the story — `business-rules.md`, `messages.md` and `statuses-and-permissions.md` (search for the module or the field; don't read them in full), `functional-map.md` (the real fields and copy of the screen) and `api/` (contracts).
- **Cite the original source** listed in the document (`src/...:line`, the PR, the comment), not just the file in `input/documentation/`.
- The dossier's **Contradictions and doubts** are recorded as `MI-XX` in the context file (section 5).
- If there is no documentation or it is marked as *Review* or *Outdated* (the code changed; see `input/documentation/changes.md`), continue with the sources in section 3 and, in your answer, suggest asking the `project-documenter` to build or update it (don't invoke it yourself).

## 3. Where to search (in this order)

```
+-------------------------+------------------------------------------+-----------------------------------------+
| Source                  | What to look at                          | How                                     |
+=========================+==========================================+=========================================+
| **Story in Jira**       | Description, acceptance criteria,        | `atlassian` connector                   |
|                         | status, priority, labels, components,    |                                         |
|                         | version, attachments (names)             |                                         |
+-------------------------+------------------------------------------+-----------------------------------------+
| **Comments**            | **All of them**, from oldest to newest.  | `atlassian` connector                   |
|                         | They often hold decisions ("we agreed    |                                         |
|                         | the limit is 50") that override what the |                                         |
|                         | description says                         |                                         |
+-------------------------+------------------------------------------+-----------------------------------------+
| **Subtasks**            | Description and comments of each one     | `atlassian` connector                   |
|                         | (e.g. "Validate email on the backend")   |                                         |
+-------------------------+------------------------------------------+-----------------------------------------+
| **Epic / parent**       | Description and general rules of the     | `atlassian` connector                   |
|                         | feature; **sibling stories** in the same |                                         |
|                         | epic (title and description only) to     |                                         |
|                         | understand the full flow                 |                                         |
+-------------------------+------------------------------------------+-----------------------------------------+
| **Linked issues**       | "relates to", "blocks", "is blocked by", | `atlassian` connector                   |
|                         | "duplicates", linked bugs (already known |                                         |
|                         | bugs in the flow)                        |                                         |
+-------------------------+------------------------------------------+-----------------------------------------+
| **Confluence**          | Pages linked from the story, the epic or | `atlassian` connector                   |
|                         | the comments; if there are no links, a   |                                         |
|                         | search by the feature name in the        |                                         |
|                         | project space (at most 5 results, read   |                                         |
|                         | only the relevant ones)                  |                                         |
+-------------------------+------------------------------------------+-----------------------------------------+
| **Figma**               | Links to designs in the story, the epic  | `figma` connector                       |
|                         | or the comments: exact copy, error       |                                         |
|                         | messages, states (empty, loading,        |                                         |
|                         | error), required fields                  |                                         |
+-------------------------+------------------------------------------+-----------------------------------------+
| **API contracts**       | Swagger/OpenAPI or Postman collections   | `curl` / reading files                  |
|                         | (URL or `input/api/`): fields,           |                                         |
|                         | validations, response codes              |                                         |
+-------------------------+------------------------------------------+-----------------------------------------+
| **Local documentation** | `input/stories/`, `input/documentation/` | Reading files                           |
|                         | (section 2 and whatever the person left  |                                         |
|                         | by hand)                                 |                                         |
+-------------------------+------------------------------------------+-----------------------------------------+
| **App repository**      | Only if there is no current dossier: the | Repository connector (`github`,         |
|                         | PRs or commits with the story key and    | `gitlab`, `azure-devops` or `atlassian` |
|                         | the validations or messages in the code  | for Bitbucket); see `CONNECTORS.md`     |
|                         | they touch (targeted; the full           |                                         |
|                         | walkthrough belongs to the project-      |                                         |
|                         | documenter)                              |                                         |
+-------------------------+------------------------------------------+-----------------------------------------+
| **Previous work**       | `output/story-analysis/`, earlier cases  | Reading files                           |
|                         | for the same story or for sibling        |                                         |
|                         | stories, existing `.feature` files in    |                                         |
|                         | k0lmena                                  |                                         |
+-------------------------+------------------------------------------+-----------------------------------------+
```

**If the story is in Azure DevOps** (Azure Boards, `azure-devops` connector), go through the same sources with their equivalents: the work item (*User Story* / *Product Backlog Item*) with `wit_work_item` (`get`, description fields and *Acceptance Criteria*), its comments (`list_comments`), the child *Tasks*, the parent (*Feature* / *Epic*), the links (*Related*, *Predecessor/Successor*, *Tested By*, bugs) and the project **Wiki** instead of Confluence (`wiki`, `search_wiki`). The change date used to reuse the context file is `System.ChangedDate`.

**If the story is in another management tool**, go through it the same way, with that tool's connector (see `CONNECTORS.md`) and these equivalences:

```
+-----------------------------------+----------------------------------------+----------------+-------------------------------------+-----------------------------------+------------------------------------------+
| Tool                              | Story and criteria                     | Comments       | Subtasks / checklist                | Parent                            | Links · change date                      |
+===================================+========================================+================+=====================================+===================================+==========================================+
| Linear (`linear`)                 | Issue: description                     | Issue comments | Sub-issues                          | Project, cycle, parent issue      | Relations (blocks, related, duplicate) · |
|                                   |                                        |                |                                     |                                   | `updatedAt`                              |
+-----------------------------------+----------------------------------------+----------------+-------------------------------------+-----------------------------------+------------------------------------------+
| ClickUp (`clickup`)               | Task: description and custom fields    | Task comments  | Subtasks and checklists             | List, folder, space, parent task  | Relationships and dependencies ·         |
|                                   |                                        |                |                                     |                                   | `date_updated`                           |
+-----------------------------------+----------------------------------------+----------------+-------------------------------------+-----------------------------------+------------------------------------------+
| monday.com (`monday`)             | Item: columns and description          | Item updates   | Subitems                            | Board and group                   | Connect columns · last update            |
+-----------------------------------+----------------------------------------+----------------+-------------------------------------+-----------------------------------+------------------------------------------+
| Asana (`asana`)                   | Task: description and custom fields    | Task comments  | Subtasks                            | Project, section, parent task     | Dependencies · `modified_at`             |
+-----------------------------------+----------------------------------------+----------------+-------------------------------------+-----------------------------------+------------------------------------------+
| Trello (`trello`)                 | Card: description                      | Card comments  | Checklists                          | List and board                    | Cards attached as links · last activity  |
+-----------------------------------+----------------------------------------+----------------+-------------------------------------+-----------------------------------+------------------------------------------+
| Notion (`notion`)                 | Database page (properties and content) | Page comments  | To-do lists or subpages             | Database and parent page          | Database relations · `last_edited_time`  |
+-----------------------------------+----------------------------------------+----------------+-------------------------------------+-----------------------------------+------------------------------------------+
| YouTrack (`youtrack`)             | Issue: description and fields          | Issue comments | Subtasks (subtask link)             | Project and parent issue (epic)   | Links (relates, depends, duplicates) ·   |
|                                   |                                        |                |                                     |                                   | `updated`. Knowledge base articles       |
|                                   |                                        |                |                                     |                                   | instead of Confluence                    |
+-----------------------------------+----------------------------------------+----------------+-------------------------------------+-----------------------------------+------------------------------------------+
| Shortcut (`shortcut`)             | Story: description                     | Story comments | Story tasks                         | Epic, iteration, objective        | Story links · `updated_at`               |
+-----------------------------------+----------------------------------------+----------------+-------------------------------------+-----------------------------------+------------------------------------------+
| GitHub / GitLab Issues (`github`, | Issue: body                            | Issue comments | Task lists and sub-issues (GitHub), | Milestone, epic (GitLab), project | Linked issues and PRs · `updated_at`     |
| `gitlab`)                         |                                        |                | child tasks (GitLab)                |                                   |                                          |
+-----------------------------------+----------------------------------------+----------------+-------------------------------------+-----------------------------------+------------------------------------------+
```

In these tools the acceptance criteria almost never have their own field: look for them in the description (a *Criteria* section, a checklist, a numbered list) and, if they are not there, it is an `MI-XX`. If the tool has no wiki of its own, the documentation is usually in Notion, Confluence or the repository. For traceability, use the tool's ID (`ENG-142`, `#1234`, the card link), just like a Jira key.

Limits to avoid spending extra tokens: a single level of depth from the story (its direct links, not the links of the links), and from each source extract only what helps with testing (rules, validations, copy, states, permissions, data). Don't copy entire pages.

**If a connector is not active** (for example, there is no `atlassian`, `azure-devops` or the team's tool connector), don't replace it with assumptions: record the source as **Not available** in the context file and continue with the others. If the story was pasted in the chat or in `input/`, warn that the comments, subtasks and epic could not be reviewed.

## 4. How to interpret what you find

- **Comment vs. description**: a newer comment that records a **decision** (by the PO, analyst or team) overrides the description. Cite who and when.
- **Contradictions**: if two sources say different things and neither is a later explicit decision, **don't choose**: record it as a contradiction and as an `MI-XX`.
- **Design vs. story**: Figma copy counts as a source for messages and labels; if it contradicts the story, it is a contradiction.
- **The app is not a source of requirements**: what the application does today is useful as an observation, but it does not define the expected result.
- **Neither is the code**: a validation or a message in the repository says how it is implemented today. It helps to pin down a detail the story leaves open (the exact text of an error, a maximum length) by citing it as *observed in the code*; if it contradicts the story or a decision, it is a contradiction and an `MI-XX`, not the expected result.

## 5. "Missing information" (MI-XX)

Every detail needed for testing that **does not appear in any source** (or appears contradictory) is recorded as an `MI-XX` item, numbered per story (`MI-01`, `MI-02`, …):

- **What is missing**: specific ("text of the error message when entering an invalid email"), not generic ("details are missing").
- **Where it was searched**: the sources reviewed, so nobody repeats the search.
- **Impact**: which criteria or cases it affects.
- **Question**: ready to send to the PO.
- **Status**: `Open` until someone answers it; then `Resolved` with the answer and the source.

Rules that apply to all agents:

1. **Don't make things up**: if a case depends on an `MI-XX`, it is written anyway but flagged (see below). If an assumption is used to be able to write it, it is stated as an assumption tied to that `MI-XX`.
2. **Flag it in every artifact**:
   - Manual cases (JSON for `generate_cases.py`): field `"missing_info": ["MI-01"]` in the case and the `"missing_info"` list at the root. The script highlights those cases, adds the `@missing-info` label and adds the *Missing information* sheet.
   - BDD cases and k0lmena `.feature` files: tags `@missing-info @MI-01` on the scenario and a comment `# MISSING INFORMATION (MI-01): <what is missing>` above it.
   - Coverage reports: a **Missing information** section and, in the per-criterion table, coverage `Partial (missing information)`.
   - Mapping report: status `Missing information` on the affected steps.
   - Run reports and closure report: field `missing_info` in each case and the `missing_info` list (see the scripts).
3. **Reuse the IDs**: the same `MI-01` travels from the context file to the cases, to the `.feature`, to the reports and to the management tool. That way, when the PO answers, you know what to change.

## 6. The context file

Save it in `output/context/context-<US>.md` following `templates/context-template.md` and normalize it with `python scripts/format_tables.py`. Sections: sources consulted (including the documents in `input/documentation/` you used), feature summary, rules and findings per criterion (each with its source), decisions in comments, contradictions and **Missing information**. Answer the person with a short summary: sources reviewed, key findings and the list of open `MI-XX` items.
