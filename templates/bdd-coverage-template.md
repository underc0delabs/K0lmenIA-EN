# BDD coverage — [US-XXX — Module]

> Report that complements the `US-XXX-name.feature` file.
> It maps each acceptance criterion to the scenarios that cover it.
>
> _(Illustrative example for US-001 — Login.)_

## Summary

- **Story:** US-001 — Login
- **Scenarios generated:** 4
- **Acceptance criteria covered:** 3 of 3

## Coverage by criterion

```
+-------------+------------------------------------+---------------------------------------+-------------------------------+
| Criterion   | Description                        | Scenarios that cover it               | Coverage                      |
+=============+====================================+=======================================+===============================+
| AC1         | Login with valid credentials       | TC-001 — Login with valid credentials | Covered                       |
+-------------+------------------------------------+---------------------------------------+-------------------------------+
| AC2         | Rejection with invalid credentials | TC-002 — Login with an invalid email  | Covered                       |
|             |                                    | format (Scenario Outline); TC-003 —   |                               |
|             |                                    | Login with an incorrect password      |                               |
+-------------+------------------------------------+---------------------------------------+-------------------------------+
| AC3         | Lockout after 3 failed attempts    | TC-004 — Account lockout after 3      | Partial (missing information) |
|             |                                    | attempts                              |                               |
+-------------+------------------------------------+---------------------------------------+-------------------------------+
```

## Scenario detail by criterion

```
+-------------+---------------------------------------+-----------------+------------------------------------------+
| Criterion   | Scenario                              | Type            | Key steps                                |
+=============+=======================================+=================+==========================================+
| AC1         | TC-001 — Login with valid credentials | Happy path      | Given a registered user, When they enter |
|             |                                       |                 | valid credentials, Then they reach the   |
|             |                                       |                 | dashboard                                |
+-------------+---------------------------------------+-----------------+------------------------------------------+
| AC2         | TC-002 — Login with an invalid email  | Negative        | When they enter an email without a valid |
|             | format                                |                 | format (Examples), Then they see the     |
|             |                                       |                 | invalid format message                   |
+-------------+---------------------------------------+-----------------+------------------------------------------+
| AC2         | TC-003 — Login with an incorrect      | Negative        | When they enter an incorrect password,   |
|             | password                              |                 | Then they see the error message          |
+-------------+---------------------------------------+-----------------+------------------------------------------+
| AC3         | TC-004 — Account lockout after 3      | Negative / edge | Given 2 previous failed attempts, When   |
|             | attempts                              |                 | the third attempt fails, Then the        |
|             |                                       |                 | account gets locked (duration: MI-02)    |
+-------------+---------------------------------------+-----------------+------------------------------------------+
```

## Missing information

Data that doesn't appear in any source. The scenarios that depend on it carry `@missing-info @MI-XX` and the comment `# MISSING INFORMATION (MI-XX): …` in the `.feature`.

```
+-------+--------------------------------------+-----------------------------------------+--------------+-----------------------------------------+----------+
| ID    | What is missing                      | Where it was searched                   | Affects      | Question for the PO                     | Status   |
+=======+======================================+=========================================+==============+=========================================+==========+
| MI-01 | Text of the message when the account | Story, comments, Figma, Confluence      | AC3 · TC-004 | What is the exact message when it gets  | Open     |
|       | gets locked                          |                                         |              | locked?                                 |          |
+-------+--------------------------------------+-----------------------------------------+--------------+-----------------------------------------+----------+
| MI-02 | Lockout duration (15 or 30 minutes)  | Story, Confluence (they contradict each | AC3 · TC-004 | Does the lockout last 15 or 30 minutes? | Open     |
|       |                                      | other)                                  |              |                                         |          |
+-------+--------------------------------------+-----------------------------------------+--------------+-----------------------------------------+----------+
```

## Pending / to be confirmed

The open `MI-XX` (marked with `# MISSING INFORMATION` in the `.feature`) and whatever still has to be defined before automating:

- Exact duration of the account lockout after 3 failed attempts (to be confirmed with the PO).
- Exact text of the error messages.
