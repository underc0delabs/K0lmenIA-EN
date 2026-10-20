# Test coverage — [US-XXX — Module]

> Report that complements the test case spreadsheet `cases-US-XXX.xlsx`.
> It summarizes **what the tests cover**, points out **ambiguities** and leaves **questions for the PO**.
>
> _(Illustrative example for US-001 — Login.)_

## Summary

- **Story:** US-001 — Login
- **Test cases generated:** 5 (TC-001 to TC-005)
- **Acceptance criteria covered:** 3 of 3
- **Test types:** positive (1), negative (3), edge (1)

## Coverage by acceptance criterion

```
+-------------+--------------------------------------+----------------------------+-------------------------------+
| Criterion   | Description                          | Test cases that cover it   | Coverage                      |
+=============+======================================+============================+===============================+
| AC1         | Login with valid credentials         | TC-002                     | Covered                       |
+-------------+--------------------------------------+----------------------------+-------------------------------+
| AC2         | Rejection with an incorrect password | TC-003                     | Covered                       |
+-------------+--------------------------------------+----------------------------+-------------------------------+
| AC3         | Lockout after 3 failed attempts      | TC-001                     | Partial (missing information) |
+-------------+--------------------------------------+----------------------------+-------------------------------+
```

## Coverage by test type

- **Positive:** TC-002 (login with valid data).
- **Negative:** TC-003, TC-004, TC-005.
- **Edge:** TC-001 (lockout exactly on the 3rd attempt). Technique: state transition (Active → Locked on the 3rd failed attempt; Locked + correct password → rejected).
- **Field validations:** TC-005 (required fields).

## Out of scope / not covered

- Password recovery (not part of US-001).
- Social login (not mentioned).

## Missing information

Data that doesn't appear in any source (story, comments, subtasks, epic, Confluence, Figma). The test cases that depend on it are highlighted in the spreadsheet and carry the `@missing-info` tag. They come from the sheet `output/context/context-US-001.md`.

```
+-------+--------------------------------------+-----------------------------------------+--------------+-----------------------------------------+----------+
| ID    | What is missing                      | Where it was searched                   | Affects      | Question for the PO                     | Status   |
+=======+======================================+=========================================+==============+=========================================+==========+
| MI-01 | Text of the message when the account | Story, comments, Figma, Confluence      | AC3 · TC-001 | What is the exact message when it gets  | Open     |
|       | gets locked                          |                                         |              | locked?                                 |          |
+-------+--------------------------------------+-----------------------------------------+--------------+-----------------------------------------+----------+
| MI-02 | Lockout duration (15 or 30 minutes)  | Story, Confluence (they contradict each | AC3 · TC-001 | Does the lockout last 15 or 30 minutes? | Open     |
|       |                                      | other)                                  |              |                                         |          |
+-------+--------------------------------------+-----------------------------------------+--------------+-----------------------------------------+----------+
```

## Ambiguities detected

Points of the story that are unclear or incomplete. **No values were made up:** where something had to be assumed, the assumption was stated in the spreadsheet's `Comments` and listed here.

1. **Lockout duration:** the story says "temporary lockout" but doesn't say how many minutes, and Confluence says 15 or 30. _(No value was chosen: TC-001 stays tied to MI-02.)_
2. **Attempt counter reset:** it isn't clear whether the 3 attempts are counted per session, over time, or until a successful login.
3. **Error message:** the exact text the user sees when the login fails or the account gets locked is not specified.

## Questions for the PO

1. How long exactly does the account lockout last after the 3 failed attempts?
2. Does the attempt counter reset over time, after a successful login, or never?
3. What is the exact message when incorrect credentials are entered? And when the account gets locked?
