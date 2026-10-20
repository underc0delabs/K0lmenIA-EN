# Mailpit — test mailbox for emails

[Mailpit](https://mailpit.axllent.org) (free, MIT) is a **test** mail server: the application sends its emails to it over SMTP and Mailpit stores them **without delivering them to anyone**. That way you can verify signup, password recovery, order or notification emails without using real mailboxes.

It is used by the `email-verifier` agent (`npm run emails`) and by the k0lmena email steps (`tools/emails/emails.steps.ts`).

## Starting it

With Docker (recommended):

```bash
docker compose -f tools/mailpit/docker-compose.yml up -d
```

Or without Docker: download the executable from [github.com/axllent/mailpit/releases](https://github.com/axllent/mailpit/releases) and run `mailpit`.

- Web and API: http://localhost:8025 (this is `MAILPIT_URL` in the root `.env`).
- SMTP: `localhost:1025`, no user and no TLS.

## Connecting the application

In the **test environment** (never in production), configure the application's SMTP like this:

| Setting       | Value                                                                 |
| ------------- | --------------------------------------------------------------------- |
| SMTP server   | `localhost` (or the IP or name of the machine where Mailpit runs)     |
| Port          | `1025`                                                                |
| User/password | anything (or empty)                                                   |
| TLS/SSL       | disabled                                                              |

If the application runs on another server, Mailpit must be reachable from there, and `MAILPIT_URL` must point to that machine.

## Using it

```bash
npm run emails -- --to ana@test.com --expect input/emails/expect-US-001.json   # reviews and compares with what is expected
npm run emails -- --to ana@test.com --wait 1 --timeout-s 60                 # waits for it to arrive after triggering the send
npm run emails -- --clean-mailbox                                               # deletes the whole test mailbox
```

Steps for the k0lmena `.feature` files (web and api):

```gherkin
Given the test mailbox is empty
Then an email arrives at "ana@test.com" with the subject "Confirm your account"
And the email contains "Hello Ana"
And the email does not contain "undefined"
And the email has the attachment "invoice.pdf"
When I save the link from the email that contains "/confirm" as "confirmationLink"
```

Mailpit also checks the HTML compatibility with email clients (Outlook, Gmail, Apple Mail…) and the links of each message: the verifier uses those two checks.
