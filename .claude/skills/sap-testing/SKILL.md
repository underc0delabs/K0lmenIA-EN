---
name: sap-testing
description: How to test SAP systems — SAP GUI for Windows (transactions/T-codes, SAP GUI Scripting API over COM, status bar messages, modes/sessions) and Fiori/UI5 (launchpad, tiles, apps, OData services, catalogs and groups); clients and environments (QA/sandbox vs. productive, transports, support packages and upgrades, conversion to S/4HANA), S/4HANA vs. ECC; authorizations and roles (PFCG, SU01, SU53, SUIM, authorization objects, segregation of duties/SoD); end-to-end business processes (Order to Cash, Procure to Pay, Record to Report, inventory); master and test data (materials, customers, vendors, accounts, transaction variants); background jobs and interfaces (jobs SM37, IDocs WE02, qRFC queues SM58, BAPIs); the smoke test, regression after a transport or an upgrade, performance (ST03, ST05, SAT, response and Fiori times) and security (SoD, least-privilege roles, scripting, RFC, PII); how to automate it with the Scripting API and with Playwright, typical bugs and questions for the PO. Used by the sap-tester and the mappers when they automate SAP.
---

# Testing on SAP

SAP is tested on **two fronts**: the **SAP GUI for Windows** (the classic transactions by code, the "T-codes") and **Fiori/UI5** (the launchpad web apps). Almost every business process crosses both, plus authorizations and master data. It is always tested against a **QA client**, never a productive one.

## 1. Environments and clients

- An SAP system has a **SID** (e.g. `DQ1`) and several **clients** (e.g. 100). The typical landscape is **DEV → QAS → PRD** and changes travel through **transports (TR)**. You test in QAS (or a QA client), with test data.
- **S/4HANA vs. ECC**: in S/4HANA the back office has a lot of Fiori and tables and transactions change (e.g. the finance data model, 40-character materials). Confirm the version: it changes what is tested and how.
- **When a regression is triggered**: after **importing a transport**, applying a **support package**, an **upgrade** or a **conversion to S/4HANA**. That is when the regression of the critical processes is run (§9).
- The **transport number** and the client are part of the bug's traceability.

## 2. SAP GUI for Windows

- You navigate by **T-codes** in the command field (`/n<tcode>` to go, `/o<tcode>` for a new session). The key transactions depend on the module (SD, MM, FI/CO, PP, HCM…).
- **Status bar messages**: SAP responds with messages of type **S** (success), **W** (warning), **E** (error) and **A** (abort). The type and number of the message (e.g. `VL 561`) are the objective verification of a step.
- **Transaction variants and layouts**: the same transaction may look different by variant, ALV layout or user parameterization; test with the variant the business uses.
- **SAP GUI Scripting** (the COM automation API) requires being enabled on the **server** (RZ11 `sapgui/user_scripting = TRUE`) and on the **client** (Options → Accessibility & Scripting). The `npm run sap` tool (`tools/sap/sap_gui.py`) surveys in read-only mode the system, the client, the user and the transaction of the open sessions.
- SAP GUI's own **Script Recording & Playback** generates a base script; the agent adapts it. The GUI **field ids** (`wnd[0]/usr/ctxt...`) are stable across runs but change across transaction versions.

## 3. Fiori / UI5

- The **Fiori Launchpad** shows **tiles** grouped into **catalogs** and **groups**, assigned by role. A tile that doesn't appear is usually a role/catalog issue, not an app bug.
- Fiori apps are **UI5** (web) and consume **OData services** (`/sap/opu/odata/...` or `/sap/opu/odata4/...`). They are automated as web with Playwright; the OData services, with the `api-runner` (metadata `$metadata`, `$filter`, `$expand`, `$batch`).
- App types: **transactional** (create/edit), **analytical** (KPIs, Smart Business) and **fact sheets**. The **Smart Controls** (SmartTable, SmartFilterBar) generate fields from the OData metadata.
- **Launchpad and cross navigation**: an app navigates to another by *semantic object + action*; test that the link lands with the correct parameter.

## 4. Authorizations and roles

- Permissions are built with **roles (PFCG)** made up of **authorization objects** (e.g. `V_VBAK_VKO` with activity 01/02/03). Users (**SU01**) have roles.
- **SU53** shows the user's last authorization failure: it is the evidence of "I was missing a permission". **SUIM** searches for who has what.
- Test **by role**: that each role can do what it should and **not** what it shouldn't (access by T-code and by object; in Fiori, which tiles it sees). A QA role shouldn't bring extra permissions.
- **Segregation of duties (SoD)**: dangerous combinations (e.g. creating a vendor **and** paying it) shouldn't fall on the same user. It is a security finding.

## 5. Business processes (end to end)

What has the most value is the complete process, not the standalone transaction:

- **Order to Cash (O2C/SD)**: sales order (VA01) → delivery (VL01N) → picking/WM → invoice (VF01) → posting. Verify stock, prices, taxes and the accounting documents.
- **Procure to Pay (P2P/MM)**: purchase requisition (ME51N) → purchase order (ME21N) → goods receipt (MIGO) → invoice (MIRO) → payment (F110). Three-way match: order, receipt and invoice.
- **Record to Report (R2R/FI-CO)**: journal entries, closings, reconciliations, reports.
- Each step leaves a **document** (document number) and affects stock, accounting or both; the books have to balance across modules.

## 6. Master and test data

- **Master data**: materials (MM01), customers/vendors (Business Partner, BP), accounts, plants, sales/purchasing organizations. Incomplete master data stops the process downstream.
- Use test data from the **QA client** (`QA-` prefix where possible) and note the documents created to trace them.
- **Dates and accounting periods**: many errors come from a closed period or a date out of range.

## 7. Background jobs and interfaces

- **Background jobs (SM37)**: that they are scheduled, run and finish without canceling; check the log (spool).
- **IDocs (WE02/WE05)**: status 53 (ok), 51 (application error), 02/30 (not sent); reprocessing (BD87).
- **qRFC/tRFC queues (SMQ1/SMQ2, SM58)**: stuck entries = interfaces that didn't process.
- **BAPIs and RFC**: if the flow calls a BAPI, test commit/rollback and error handling.

## 8. Smoke test

Fast and blocking, in the QA client:

1. Login to the SAP GUI and to Fiori with a test user.
2. Open a key transaction in scope (e.g. VA03 in display mode) without a dump.
3. The Fiori launchpad loads and the role's tiles appear.
4. SAP GUI Scripting is enabled (if the GUI is going to be automated).
5. There are no recent **ST22 dumps** for the user and no errors in sight.

## 9. Regression

- After a **transport, support package, upgrade or conversion to S/4HANA**: run the **critical processes** end to end (O2C and P2P at minimum), the transactions and apps the change touches, and the key reports, verifying the documents and the amounts.
- Ideally it is automated (SAP GUI Scripting for the GUI and Playwright for Fiori, via `web-mapper` and `npm test`), to repeat the regression without tokens after each transport.
- Check for **new dumps (ST22)** and **error messages** after the change.

## 10. Performance

- **Response times** per transaction and per Fiori app; **ST03** (system workload), **ST05** (SQL trace), **SAT/SE30** (ABAP trace) and **SM50/SM66** (work processes) show where the time goes.
- In **Fiori**, additionally, the CWV and the latency of the OData services (`web-performance-auditor` and, for load, `performance-mapper` with `performance-guide`).
- Watch out for reports/lists that bring millions of rows without a filter and for jobs that overlap at peak time.

## 11. Security

The scanning and exploitation are done by the `security-analyst` and the `web-pentester`; specific to SAP:

- **Least-privilege roles** and **segregation of duties (SoD)**: dangerous combinations kept separate.
- **SAP GUI Scripting**: enabling it lowers a security barrier; in a productive system it is usually restricted. Confirm that in QA it is intentional.
- **RFC and communication/service users**: with narrow permissions, not `SAP_ALL`; RFC destinations (SM59) without extra credentials.
- **Standard users** (SAP*, DDIC) with the default password = finding.
- **PII and sensitive data** on screens, downloads (lists to Excel) and logs; **masked** where appropriate.
- In **Fiori/OData**: that a service doesn't expose data without authorization and there is no IDOR through the entity id.

## 12. Automate

- **SAP GUI**: with the **Scripting API** (COM) from Python (`win32com`) or the language k0lmena uses; navigate by field ids (`wnd[0]/usr/...`), send the T-code through the command field and verify the **type and number of the message** in the status bar, not just the text.
- **Fiori**: with Playwright MCP (skill `e2e-execution`); wait for the OData responses before reading the UI; UI5 ids are long and change, locate by role and text.
- **OData**: with the `api-runner` (collection over `/sap/opu/odata/...`, with `$metadata`, `$filter`, `$batch` and CSRF token).
- Always test against the **QA client**; never automate writes against a productive system.

## 13. Typical SAP bugs

- An **ST22 dump** (ABAP runtime error) when running a transaction after a transport.
- Missing **authorization** (SU53) in a role that should be able to do the step.
- The process stops because of incomplete **master data** or a closed **accounting period**.
- Amounts or taxes that don't balance across SD, MM and FI.
- An **IDoc in 51** or a **stuck RFC queue**: the interface didn't process.
- A **job** that cancels or isn't scheduled.
- In **Fiori**, a **tile that doesn't appear** because of catalog/role, or an app that fails because of an OData service without authorization.
- **SoD**: a user who can create a vendor and pay it.
- A transaction variant different from the business's that hides required fields.

## 14. Typical questions for the PO (SAP)

When it isn't written down, they are `MI-XX`:

- Is it S/4HANA or ECC? Which release?
- Which processes are in scope (O2C, P2P, R2R…) and up to which step?
- Which system and client is it tested on (never productive)? With which users and roles?
- Is GUI Scripting enabled in QA for automation?
- Which Fiori apps and which OData services are in scope?
- What test master data is there and who creates it?
- Does the test cover authorizations/SoD, performance or only functional?
