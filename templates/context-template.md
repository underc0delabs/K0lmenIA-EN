# Context — [US-XXX — Feature]

> Context sheet built before analyzing, designing or automating the tests (skill `context-research`).
> It gathers what was found in every source and records **what is missing** as `MI-XX`.
>
> _(Illustrative example for US-001 — Login.)_

- **Story:** PROJ-12 / US-001 — Login
- **Updated in Jira:** 2026-10-05 14:20 · **Sheet generated:** 2026-10-08 10:15
- **Missing information:** 2 open items (MI-01, MI-02)

## Sources consulted

```
+-----------------------+-----------------------------+-----------+------------------------------------------+
| Source                | Reference                   | Status    | Contribution                             |
+=======================+=============================+===========+==========================================+
| Project documentation | input/documentation/        | Consulted | Up-to-date dossier (2026-10-07): PR      |
|                       | stories/PROJ-12/dossier.md  |           | #318, login messages in the code         |
+-----------------------+-----------------------------+-----------+------------------------------------------+
| Story                 | PROJ-12                     | Consulted | Criteria AC1 to AC3                      |
+-----------------------+-----------------------------+-----------+------------------------------------------+
| Comments              | 7 comments                  | Consulted | Decision about the lockout (see below)   |
+-----------------------+-----------------------------+-----------+------------------------------------------+
| Subtasks              | PROJ-13, PROJ-14            | Consulted | Email format validation in the backend   |
+-----------------------+-----------------------------+-----------+------------------------------------------+
| Epic                  | PROJ-5 Authentication       | Consulted | 30-minute session rule                   |
+-----------------------+-----------------------------+-----------+------------------------------------------+
| Linked issues         | PROJ-40 (bug)               | Consulted | Known bug: the button is enabled with an |
|                       |                             |           | empty email                              |
+-----------------------+-----------------------------+-----------+------------------------------------------+
| Confluence            | "Authentication rules"      | Consulted | Password policy                          |
+-----------------------+-----------------------------+-----------+------------------------------------------+
| Figma                 | Login screen, frame 12:340  | Consulted | Credential error texts                   |
+-----------------------+-----------------------------+-----------+------------------------------------------+
| API contract          | input/api/auth-endpoints.md | Consulted | POST /login returns 401 and 423          |
+-----------------------+-----------------------------+-----------+------------------------------------------+
```

## Feature summary

Two or three lines on what the feature does, who uses it and the main flow, according to the sources.

## Rules and findings by criterion

```
+-------------+----------------------------------------+--------------------------------------+
| Criterion   | Finding                                | Source                               |
+=============+========================================+======================================+
| AC1         | Login accepts email (not username) and | Story                                |
|             | password                               |                                      |
+-------------+----------------------------------------+--------------------------------------+
| AC2         | Message: "Incorrect email or password" | Figma, frame 12:340                  |
+-------------+----------------------------------------+--------------------------------------+
| AC3         | Lockout after 3 consecutive failed     | Comment by A. Pérez (PO), 2026-10-02 |
|             | attempts                               |                                      |
+-------------+----------------------------------------+--------------------------------------+
```

## Decisions recorded in comments

- **2026-10-02 · A. Pérez (PO):** the attempt counter resets after a successful login. This replaces what the description said ("per session").

## Contradictions

- The story says "15-minute lockout" and the Confluence page "Authentication rules" says 30 minutes. There is no later decision → recorded as MI-02.

## Missing information

```
+-------+--------------------------------------+------------------------------------+---------------------+-----------------------------------------+----------+
| ID    | What is missing                      | Where it was searched              | Impact              | Question for the PO                     | Status   |
+=======+======================================+====================================+=====================+=========================================+==========+
| MI-01 | Text of the message when the account | Story, comments, Figma, Confluence | AC3 · lockout cases | What is the exact message when the      | Open     |
|       | gets locked                          |                                    |                     | account gets locked?                    |          |
+-------+--------------------------------------+------------------------------------+---------------------+-----------------------------------------+----------+
| MI-02 | Lockout duration (15 or 30 minutes)  | Story, Confluence                  | AC3 · unlock cases  | Does the lockout last 15 or 30 minutes? | Open     |
+-------+--------------------------------------+------------------------------------+---------------------+-----------------------------------------+----------+
```
