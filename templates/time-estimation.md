# Estimated manual run time

Every test case (manual or BDD) carries an **estimated manual run time**: how long a person who knows the application takes to run it end to end, with the environment ready. It is calculated by `scripts/estimation.py` and appears in:

- the test case spreadsheet (`generate_cases.py`): **Estimated Time (min)** column, with the total at the bottom, and in the `.md`;
- the test management tool when the cases are uploaded (`management.py upload-cases`): in the description of each case and, if the tool has one, in its time field —Jira's **Original Estimate** in Xray Cloud and Server/DC, **estimatedTime** in QTM4J, **estimatedEffort** in AIO Tests—; for Azure DevOps it travels in the JSON from `to_azure_devops.py` and as a tag;
- the test case selection (`select_cases.py`) and the case reviewer (`case-reviewer`).

## The formula

```
case time = (setup + Σ time of each step + logging) × factor     → rounded up to 0.5 min (minimum 1)

step time = action + data + verification
```

```
+--------------+------------------------------------------+
| Part         | How it is calculated                     |
+==============+==========================================+
| Action       | According to the step's verb (table      |
|              | below)                                   |
+--------------+------------------------------------------+
| Data         | 0.15 min for each extra piece of data in |
|              | the step (beyond the fields already      |
|              | counted)                                 |
+--------------+------------------------------------------+
| Verification | 0.5 min if the step has an expected      |
|              | result (or is a Then), + 0.25 for each   |
|              | extra check (up to 4)                    |
+--------------+------------------------------------------+
| Setup        | 1 min (open the environment and read the |
|              | case) + 0.5 per precondition (up to 3) + |
|              | 2 if data or users have to be created    |
+--------------+------------------------------------------+
| Logging      | 0.5 min (mark the result and save the    |
|              | evidence) + 0.1 per step                 |
+--------------+------------------------------------------+
| Factor       | 1.1 for negative or edge cases (they     |
|              | must be observed more carefully); 1 for  |
|              | the rest. `ESTIMATION_FACTOR` in the     |
|              | `.env` multiplies everything (for        |
|              | example 1.3 for someone who is new to    |
|              | the application)                         |
+--------------+------------------------------------------+
```

```
+------------------------------------+---------------+------------------------------------------+
| Step action (verb)                 | Minutes       | Examples                                 |
+====================================+===============+==========================================+
| Navigate                           | 0.5           | go to, open, access, visit the section   |
+------------------------------------+---------------+------------------------------------------+
| Click or select                    | 0.25          | click, press, select, check, save        |
+------------------------------------+---------------+------------------------------------------+
| Fill in fields                     | 0.3 per field | fill in, type, enter the email and the   |
|                                    |               | password                                 |
+------------------------------------+---------------+------------------------------------------+
| Log in                             | 1             | log in, sign in with their user          |
+------------------------------------+---------------+------------------------------------------+
| Upload or download a file          | 1             | attach, upload an image, download,       |
|                                    |               | export                                   |
+------------------------------------+---------------+------------------------------------------+
| Wait for an email, SMS or process  | 2             | wait, receive the email, check the inbox |
+------------------------------------+---------------+------------------------------------------+
| Query the database, an API or logs | 2             | query the database, call the endpoint    |
+------------------------------------+---------------+------------------------------------------+
| Read or browse                     | 0.5           | scroll, review, read the detail          |
+------------------------------------+---------------+------------------------------------------+
| Any other action                   | 0.5           |                                          |
+------------------------------------+---------------+------------------------------------------+
```

Example: *"Login with an incorrect password"* (1 precondition; steps: go to the login page, fill in the email and the password with 2 pieces of data, click Continue with 2 extra checks) = (setup 1.5 + steps 0.5 + 0.6 + 1.25 + logging 0.8) × 1.1 = 5.12 → **5.5 min** (rounded up to 0.5). The last step adds 0.25 for the click + 0.5 for the first check + 0.5 for the two extra ones in the expected result.

## Adjusting it

- **A single case**: write the time in the *Estimated Time (min)* column of the spreadsheet (or `"time_min"` in the JSON of `generate_cases.py`): that value takes precedence over the formula and the steps are distributed proportionally.
- **The whole team**: `ESTIMATION_FACTOR` in the `.env` (1 by default).
- **No native field in the test management tool**: `MANAGEMENT_NATIVE_TIME=0` (the time stays only in the description). If the tool rejects the field (for example, a Jira project without time tracking), the case is still created, without it.
- **See the estimate of a spreadsheet**: `python scripts/estimation.py output/test-cases/manual/cases-US-001.xlsx`.

It is an estimate for planning, not a measurement: compare it with how long the real runs take and adjust the factor.
