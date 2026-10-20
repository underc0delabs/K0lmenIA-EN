# Test cases — US-001 — Login

## Summary

```
+--------+-------------------------+----------------------------------+------------+---------+----------------+
| ID     | Title                   | Expected result                  | Priority   | Time    | Missing info   |
+========+=========================+==================================+============+=========+================+
| TC-001 | Account lockout after 3 | After the 3rd attempt the        | Critical   | 7.5 min | MI-01,         |
|        | failed attempts         | account gets locked (duration:   |            |         | MI-02          |
|        |                         | MI-02); the next attempt is      |            |         |                |
|        |                         | rejected even with the correct   |            |         |                |
|        |                         | password.                        |            |         |                |
+--------+-------------------------+----------------------------------+------------+---------+----------------+
| TC-002 | Login with valid        | The system authenticates the     | High       | 6 min   |                |
|        | credentials             | user and redirects them to their |            |         |                |
|        |                         | dashboard.                       |            |         |                |
+--------+-------------------------+----------------------------------+------------+---------+----------------+
| TC-003 | Login with an incorrect | The system denies access and     | High       | 7 min   |                |
|        | password                | shows a clear error message.     |            |         |                |
+--------+-------------------------+----------------------------------+------------+---------+----------------+
```

**Estimated manual run time:** 20.5 min in total (formula in `templates/time-estimation.md`).

## Case details

```
+--------+------------------+------------------------+------------------+--------------------+-------------------------+----------------------+------------+---------+--------------+
| ID     | Title            | Description            | Preconditions    | Test Data          | Steps                   | Expected Result      | Priority   | Time    | #Tags        |
+========+==================+========================+==================+====================+=========================+======================+============+=========+==============+
| TC-001 | Account lockout  | Verifies that the      | Registered user, | Email: maria.gonza | 1. Go to the login page | After the 3rd        | Critical   | 7.5 min | @login       |
|        | after 3 failed   | account gets locked    | active account   | lez@test.com       | 2. Wrong password       | attempt the account  |            |         | @security    |
|        | attempts         | after 3 consecutive    | and no previous  | Password: Wrong123 | (attempt 1)             | gets locked          |            |         | @US-001 @AC3 |
|        |                  | failed attempts (AC3). | attempts.        | (x3)               | 3. Repeat (attempt 2)   | (duration: MI-02);   |            |         | @missing-    |
|        |                  |                        |                  |                    | 4. Repeat (attempt 3)   | the next attempt is  |            |         | info         |
|        |                  |                        |                  |                    | 5. Retry with the       | rejected even with   |            |         |              |
|        |                  |                        |                  |                    | correct one             | the correct          |            |         |              |
|        |                  |                        |                  |                    |                         | password.            |            |         |              |
+--------+------------------+------------------------+------------------+--------------------+-------------------------+----------------------+------------+---------+--------------+
| TC-002 | Login with valid | Verifies that a        | Registered user, | Email: maria.gonza | 1. Go to the login page | The system           | High       | 6 min   | @login       |
|        | credentials      | registered user can    | with an active   | lez@test.com       | 2. Enter the registered | authenticates the    |            |         | @smoke       |
|        |                  | log in with a valid    | and unlocked     | Password: Test1234 | email                   | user and redirects   |            |         | @US-001 @AC1 |
|        |                  | email and password and | account.         |                    | 3. Enter the correct    | them to their        |            |         |              |
|        |                  | reach their dashboard  |                  |                    | password                | dashboard.           |            |         |              |
|        |                  | (AC1).                 |                  |                    | 4. Click "Log in"       |                      |            |         |              |
+--------+------------------+------------------------+------------------+--------------------+-------------------------+----------------------+------------+---------+--------------+
| TC-003 | Login with an    | Verifies that the      | Registered user, | Email: maria.gonza | 1. Go to the login page | The system denies    | High       | 7 min   | @login       |
|        | incorrect        | system denies access   | with an active   | lez@test.com       | 2. Enter the registered | access and shows a   |            |         | @negative    |
|        | password         | when the password does | and unlocked     | Password: Wrong123 | email                   | clear error message. |            |         | @US-001 @AC2 |
|        |                  | not match (AC2).       | account.         |                    | 3. Enter an incorrect   |                      |            |         |              |
|        |                  |                        |                  |                    | password                |                      |            |         |              |
|        |                  |                        |                  |                    | 4. Click "Log in"       |                      |            |         |              |
+--------+------------------+------------------------+------------------+--------------------+-------------------------+----------------------+------------+---------+--------------+
```

## Missing information

Data that does not appear in any of the sources consulted. The cases that depend on it carry the `@missing-info` tag: TC-001 (MI-01, MI-02).

```
+-------+--------------------------------------+-------------------------+--------------+-----------------------------------------+----------+
| ID    | What is missing                      | Where searched          | Impact       | Question for the PO                     | Status   |
+=======+======================================+=========================+==============+=========================================+==========+
| MI-01 | Text of the message when the account | Story, comments, Figma, | AC3 · TC-001 | What is the exact message when it gets  | Open     |
|       | gets locked                          | Confluence              |              | locked?                                 |          |
+-------+--------------------------------------+-------------------------+--------------+-----------------------------------------+----------+
| MI-02 | Lockout duration (15 or 30 minutes)  | Story, Confluence (they | AC3 · TC-001 | Does the lockout last 15 or 30 minutes? | Open     |
|       |                                      | contradict each other)  |              |                                         |          |
+-------+--------------------------------------+-------------------------+--------------+-----------------------------------------+----------+
```
