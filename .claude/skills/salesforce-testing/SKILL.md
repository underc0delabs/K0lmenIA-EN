---
name: salesforce-testing
description: How to test a Salesforce org (Sales Cloud, Service Cloud, Experience Cloud, CPQ, custom apps) — environments and sandboxes, access (profiles, permission sets, roles, OWD, sharing rules, FLS), automation (validation rules, flows, Apex triggers, order of execution, governor limits, bulk of 200), data (record types, picklists, duplicates, multicurrency, time zone), the Lightning interface (LWC, shadow DOM, dynamic IDs, spinners and toasts) with Playwright, APIs and integrations, Apex tests and coverage, seasonal releases, and the typical Salesforce bugs. Used by the salesforce-tester and the mappers when they automate a Salesforce app.
---

# Testing on Salesforce

Salesforce is not "just another website": almost everything you have to test is **configuration** (who sees what, what is validated, what is automated) and it changes by **profile**, **record type** and **data**. This skill says what to look at and how to test it without breaking anything.

## 1. Environments: never in production

```
+---------------+-----------------------------+----------------------------------------------+
| Org           | Data                        | What for                                     |
+===============+=============================+==============================================+
| Developer /   | No data (metadata only)     | Configuration and Apex testing with your own |
| Developer Pro |                             | test data                                    |
+---------------+-----------------------------+----------------------------------------------+
| Partial Copy  | Sample of production        | Functional QA and integration                |
+---------------+-----------------------------+----------------------------------------------+
| Full          | Full copy of production     | UAT, performance, release rehearsal          |
|               |                             | (careful: may contain real personal data)    |
+---------------+-----------------------------+----------------------------------------------+
| Scratch org   | Empty, ephemeral            | Development and CI                            |
+---------------+-----------------------------+----------------------------------------------+
| Production    | Real                        | **Not tested.** Read-only and with explicit  |
|               |                             | permission                                   |
+---------------+-----------------------------+----------------------------------------------+
```

- Sandbox login is through `https://test.salesforce.com` (or the My Domain `--<sandbox>.sandbox.my.salesforce.com`). If a URL doesn't say `sandbox`, `test` or `scratch`, **verify** it is not production (`Organization.IsSandbox`).
- After a **refresh** of the sandbox: the data goes back to production's (or empty), the test users may lose permissions and **email delivery is set to "System email only"** (Setup → Deliverability). If an email doesn't arrive in a sandbox, check that before reporting a bug.
- A **Full** or **Partial Copy** may have real personal data: don't copy it into reports or screenshots (mask or crop it). If the org uses **Data Mask**, ask whether it was applied.

## 2. Access: what breaks the most

Access is evaluated in layers; a user sees a piece of data only if **all** of them allow it:

1. **Object** (CRUD: read, create, edit, delete, view all, modify all) — profile + permission sets + permission set groups.
2. **Field** (FLS: visible / read only) — same source. A field hidden by FLS **does not appear** on the page, in reports or in the API for that user.
3. **Record** — OWD (default access: `Private`, `Read`, `ReadWrite`, `ControlledByParent`), role hierarchy, sharing rules (owner-based or criteria-based), teams (account/opportunity), manual sharing, Apex managed sharing, territories.
4. **Interface** — page layouts and Dynamic Forms by profile/record type, Lightning App Builder (component visibility), buttons and actions by layout, visible tabs and apps.

How to test it:
- **One test user per relevant profile** (don't use your admin to test permissions: the admin sees everything). Ask for them to exist or be created in the sandbox (that is an action with a side effect: it is confirmed).
- **Profile × object × action** matrix and **profile × sensitive field** (salaries, documents, card data, internal notes). The `permissions-tester` builds the role × route matrix; here you complete it with what is specific to Salesforce (FLS and sharing).
- Sharing: with a user who is **not the owner** and is not above in the hierarchy, try to view/edit someone else's record, through the interface, by direct URL (`/lightning/r/<Object>/<Id>/view`), by global search, by reports and by the API.
- **Login As** only if the admin enabled it and you were authorized; otherwise, test users with their own session.
- Experience Cloud (portals): the **guest user** and external users have their own external OWD and sharing sets; it is a classic source of data exposure. Test without a session what the guest sees.

## 3. Automation: validations, flows and Apex

**Order of execution on save** (simplified): system validation rules → before-save flows → before triggers → custom validation rules → duplicates → save → after triggers → assignment/auto-response → (legacy workflow/process builder) → after-save flows → roll-ups → commit → post-commit actions (emails, events, `@future`/queueable). Consequences for testing:
- A **before-save flow** can change a value before the validation sees it: test the combined effect, not each piece in isolation.
- **Asynchronous** actions (emails, `@future`, queueable, platform events, scheduled flows) are not done when the save finishes: **wait and re-query** (polling with a cap), don't set a "wait 5 seconds".
- Several **triggers on the same object** have no guaranteed order: if there is more than one, test combinations.

**Validation rules**: for each active rule, a case that **breaks** it (exact message and in which field it appears, or above the form) and one that **meets** it right at the edge. Also test them through the **API and import** (integrations trigger them too) and with the **integration user** (sometimes it is excluded by profile: confirm whether that is intentional).

**Flows**: for each active flow, each decision path; the record-triggered ones, on creation, edit and (if applicable) delete; the screen ones, with valid and invalid data, and the *Previous* button; the scheduled ones, with their entry condition. **Process Builder and Workflow Rules are retired** (end of support 2025-12-31): if they are still active, it is a risk and migrating them to Flow needs regression.

**Governor limits** (per transaction, synchronous Apex): 100 SOQL queries, 150 DML, 50,000 rows queried, 10,000 rows in DML, 10 s of CPU, 6 MB of heap (asynchronous: 200 SOQL, 60 s of CPU, 12 MB). They break with **volume**, not with a single record:
- **Bulk of 200**: inserting/updating 200 records at once (Data Loader, `sf data import`, the Bulk API or a list with mass edit) is the test that finds SOQL or DML inside a `for`. It is a data load: it is confirmed and only in a sandbox.
- Typical errors: `System.LimitException: Too many SOQL queries: 101`, `Apex CPU time limit exceeded`, `UNABLE_TO_LOCK_ROW` (concurrency), `FIELD_CUSTOM_VALIDATION_EXCEPTION` (a rule blocked), `INSUFFICIENT_ACCESS_OR_READONLY` (sharing), `ENTITY_IS_LOCKED` (in approval).

**Apex tests**: Salesforce requires **75% coverage** across the whole org to deploy to production and that each trigger has some coverage. High coverage is not quality: check that the tests **assert** something (`System.assert*`) and don't use `SeeAllData=true`. Running them (`sf apex run test --test-level RunLocalTests --code-coverage`) leaves no data, but consumes asynchronous limits: in a sandbox and with confirmation.

## 4. Data

- **Record types**: each one can have its layout, its picklist values and its validations. Test each flow with **each record type** and the default record type of each profile.
- **Picklists**: dependent ones (controlling → dependent), inactive values that remain in old records, **API name vs. label** (integrations send the API name; the interface shows the label, translated if there is Translation Workbench).
- **Relationships**: lookup (optional, no cascade delete) vs. master-detail (required, cascade delete, inherited sharing, roll-ups). Deleting a parent in master-detail deletes the children: test it **only** with your own data.
- **Duplicates**: rules and matching rules (block or warn), also through the API and import.
- **Multicurrency** and **time zone**: amounts with the record's currency vs. the corporate one, dated rates; dates/times are stored in UTC and shown in the **user's** zone (a classic case: a `Date` that changes day for users in another zone).
- **Formulas and roll-ups**: they recalculate on read (formulas) or on saving the child (roll-ups); test the edge (nulls, division by zero, rounding).
- **Test data**: created by you and tagged (a `QA-` prefix in the name), with no real personal data. Verify in the database with **read-only** SOQL (`sf data query` or the `run_soql_query` tool of the `salesforce` connector), never modifying records through the API to "arrange" a test.

## 5. Lightning interface with Playwright

- **Shadow DOM**: LWC components encapsulate their DOM. Playwright crosses the shadow DOM with `getByRole`, `getByLabel`, `getByText` and CSS (not with XPath). Always prefer role + accessible name (`getByRole('button', { name: 'Save' })`, `getByLabel('Account Name')`).
- **Dynamic IDs**: `input-123`, `combobox-456` change on each load: **never** use them as a locator. Nor the `slds-*` classes alone (they are style, they repeat).
- **Waits**: wait for the spinner to disappear (`lightning-spinner`) and for the confirmation **toast** to appear (`role="status"` / `role="alert"` with the expected text) before moving on; related lists and components load lazily on scroll.
- **Combobox and lookups**: the Lightning picklist is not a `<select>`: click the combobox → option by role `option`. Lookups search as you type: wait for the result and pick it by its text.
- **Navigation**: prefer the direct URL (`/lightning/o/Account/new`, `/lightning/r/Account/<Id>/view`) to walking menus. In console apps, each record opens a **tab** (subtab): close the ones you opened.
- **Login**: with MFA, don't automate the login; use the saved session (`npm run login` in k0lmena) of the test user. Each profile, its own saved session.
- **Language and format**: the interface depends on the **user's** language and locale; set them on the test users so the expected texts don't change.
- **Classic**: if the org still uses Salesforce Classic for some profile, it is a different interface: test it separately or confirm it is not used.

## 6. APIs and integrations

- APIs: REST (`/services/data/vXX.X/`), SOAP, **Bulk API 2.0** (volume), Composite (several operations in one), GraphQL, Streaming (**Platform Events**, **Change Data Capture**). The integration user has its own profile: test with **that** user, not with an admin.
- Authentication: Connected App / External Client App with OAuth (JWT bearer for server integrations). Tokens go in the `.env`, never in the chat (see the `token-testing` skill).
- Outbound callouts: **Named Credentials**; in a sandbox they must point to the third parties' **sandboxes** (verify it: a sandbox calling the production payment gateway is an incident).
- Typical integrations: ERP, payment gateway, digital signature, middleware (MuleSoft), marketing (Marketing Cloud, Account Engagement). For each one: create, update, third-party error (timeout, 500), retry and idempotency (don't duplicate the record if the third party retries).
- To design the API cases use `api-case-generator`; to run them, `api-runner`; to automate them, `api-mapper`.

## 7. Releases and regression

- Salesforce ships **three releases a year** (Spring, Summer, Winter). A few weeks earlier, the **preview sandboxes** get the new version: it is the window to run the regression and detect behavior changes before production.
- **Release Updates** (critical updates) activate on their own on a date: list them and test them activated in a sandbox.
- Your own deploys: `sf project deploy validate` (check-only) runs the tests without deploying; a deploy that fails for coverage or for a test is a finding. QA **does not deploy**: it asks for it.
- Minimum regression per release: login by profile, the main flows (lead → conversion → opportunity → close; case → assignment → resolution), the validations and flows touched, the integrations and the key reports/dashboards.

## 8. By cloud (quick checks)

- **Sales Cloud**: lead conversion (field mapping, duplicates), opportunity stages and probability, products and price lists, forecasting, quotes.
- **Service Cloud**: case creation by channel (email-to-case, web-to-case, chat), assignment and escalation rules, entitlements and milestones (SLA times in business hours), Omni-Channel, knowledge base.
- **Experience Cloud**: guest user, external signup and login, sharing sets, what each license type sees, SEO and public pages.
- **CPQ / Revenue Cloud**: price and product rules, volume discounts, approvals, quote document generation, rounding.
- **Reports and dashboards**: the result depends on the user who views it (or the dashboard's fixed "running user"): test with different profiles and verify they don't expose data through a running user with more access.

## 9. Typical Salesforce bugs (so you don't confuse them)

- *"The field doesn't appear"* → FLS or the profile/record type layout, not a page bug.
- *"The email doesn't arrive"* → sandbox deliverability, a template with fields without access, or it is asynchronous.
- *"It works with one record and fails with 200"* → governor limits: it **is** a bug (of the Apex or the flow).
- *"It fails sometimes"* → `UNABLE_TO_LOCK_ROW` (two processes on the same record), sharing recalculation or asynchrony.
- *"The data is different in the API"* → API name vs. label, currency, time zone.
- *"It works for the admin"* → the admin has *Modify All Data*: reproduce it with the real profile.

## 10. Rules

- **Only authorized sandboxes** (`SALESFORCE_AUTHORIZED_ORGS`), never production except reading with explicit permission.
- **No metadata**: don't deploy, don't change configuration (validations, flows, profiles, sharing), don't assign permissions. If a change is needed to test, it is **requested** from the admin.
- **Creating or modifying data** (through the interface, API or import) is an action with a side effect: it is confirmed, done with your own `QA-` data and in a sandbox.
- **No personal data or secrets** in reports, screenshots or cases.
