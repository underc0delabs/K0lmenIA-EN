# Template — Bug report

> This is the template that the **`bug-report-generator`** agent follows.
> To change the output format, edit this template: the agent respects its fields and their order.
>
> Output format: **vertical block, one report per file.**
> Key rule: if information is missing, the agent **flags it and asks**, it never makes it up.

---

**ID:** `BUG-001` — unique and identifiable.

**Title:** `[Screen]` Descriptive title of the error.

**Story:** `US-XXX` — the story the affected flow belongs to (or *No story*).

**Status:** `Open` · `In progress` · `Resolved` · `Closed` · `Rejected` — a new bug starts as `Open`.

**Description:**
Briefly describe what the error is about, so the failure is clear.

**Preconditions:**
What has to be set up beforehand to be able to run the steps.

**Test Data:**
- User:
- Password:

**Steps to reproduce:**
1. Step 1
2. Step 2
3. Step 3
4. Step 4

**Actual Result:**
What is happening now.

**Expected Result:**
How the application should work.

**Evidence:**
Screenshot, video or log of the error.

**Severity:** `Critical` · `High` · `Medium` · `Low`

**Priority:** `Critical` · `High` · `Medium` · `Low`

**Related Test Case:** `TC-XXX` (if applicable)

**Version:** application version (Mobile) — *optional*

**Browser:** browser in which the failure was found.

**Environment:** environment in which the error was found (e.g.: testing, staging, production).

---

> **Agent note:** when some required data is not in the original observation, the report will include a final **"⚠️ Missing information"** section listing what is missing and why it is needed, instead of filling it in with assumptions.
