# US-901 — Account signup

**As a** store visitor
**I want** to create an account
**So that** I can shop and track my orders

## Description

The signup form asks for:

- **Name**: required, between 2 and 50 characters.
- **Email**: required, with a valid format. There cannot be two accounts with the same email.
- **Username**: required, between 4 and 20 characters (letters, numbers and underscore).
- **Password**: required.
- **Date of birth**: required. The minimum age to sign up is **18 years**.

When the account is created, an activation email is sent.

## Acceptance criteria

- **AC1** — With all valid data, the account is created and the message "Account created! Check your email to activate it." is shown.
- **AC2** — If the email is already registered, an error message is shown and the account is not created.
- **AC3** — The password must be secure.
- **AC4** — Only people over 16 can sign up.
- **AC5** — If the username has fewer than 4 or more than 20 characters, "Username must be between 4 and 20 characters" is shown and the account is not created.

## Comments (copied from Jira, PROJ-901)

- **2026-09-01 — Ana Pérez (PO):** "I confirm that the name accepts accents, ñ and apostrophes (for example, O'Connor)."
- **2026-09-03 — Leo Gómez (Dev):** "Is the email case-sensitive when detecting duplicates (uppercase vs. lowercase)?" *(no answer)*
