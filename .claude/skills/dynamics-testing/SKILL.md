---
name: dynamics-testing
description: How to test Microsoft Dynamics 365 and, by extension, other low-code CRM/ERP systems — environments and sandboxes (Dataverse, sandbox vs. production, managed/unmanaged solutions and their deployment), security (security roles, business units, teams, field-level access/column security, hierarchy), data model (tables/entities, columns, relationships, options/choices), logic (business rules, validation rules, Power Automate flows, plugins and workflows, Business Process Flows, calculations and roll-ups), model-driven app forms and views and Canvas/Power Apps, the Dataverse Web API (OData v4, read-only for surveying), FetchXML, duplicates, auditing, end-to-end business processes (Sales — lead→opportunity→quote→order; Customer Service — case→queue→SLA→resolution; Field Service), integrations and portals, how to test per role in the UI with Playwright, and the general idea that applies to other CRM/ERP systems (Salesforce already has its skill, SAP its own; Oracle, NetSuite, Zoho, Odoo follow the same pattern — non-production environments, roles, business logic, end-to-end processes and read API). Used by the dynamics-tester.
---

# Microsoft Dynamics 365 testing (and other CRM/ERP)

Dynamics 365 is a **low-code platform on top of Dataverse**: almost everything (tables, rules, flows, forms, roles) is **configured**, and that's where the bugs are. It is tested in a **non-production environment (sandbox)**, per role, following the business processes. The same approach applies to other CRM/ERP systems; Salesforce and SAP already have their own skills (`salesforce-testing`, `sap-testing`).

## 1. Environments and solutions

- **Dataverse** is the foundation. Test in a **sandbox** (copy), never in production.
- Changes travel as **solutions** (managed/unmanaged): verify that an imported solution doesn't break anything and that its dependencies are present.
- Confirm the **app** (model-driven or Canvas/Power App) and the modules in scope (Sales, Customer Service, Field Service, Finance & Operations…).

## 2. Security and access

- **Security roles** + **business units** + **teams**: they define what each user sees and does, with a scope (own, business unit, whole organization).
- **Column (field) security** for sensitive fields.
- Test **per role**: each one can do its own work and **not** someone else's (create/read/edit/delete per table, and per record according to the scope); direct URL access to a record from another unit.

## 3. Data model

- **Tables/entities**, columns (types, required, choices/option sets), **relationships** (1:N, N:N) and cascade delete behaviors.
- **Duplicates** (detection rules), **auditing** (which changes are recorded).

## 4. Business logic

- **Business rules** (on the form: show/hide, require, calculate), **validation rules**.
- **Business Process Flows** (the guided stages of a process): they advance according to the conditions.
- **Power Automate flows**, **plugins** and **workflows** (server-side logic): they fire on the right event, only once, and with the expected result; order of execution.
- **Calculations and roll-ups** (calculated and rollup fields): they give the right value and update when they should.

## 5. Forms, views and apps

- **Forms** per table and per role (visible/required fields), **views** (filters, columns, order), **dashboards**.
- **Canvas/Power Apps**: formulas (Power Fx), data connections, offline behavior if applicable.

## 6. Dataverse API (read-only survey)

- The **Web API** (OData v4) lets you survey tables, columns and metadata read-only; **FetchXML** for queries. Useful to understand the model before testing; no writes.

## 7. Business processes (end to end)

- **Sales**: lead → qualify → opportunity → quote → order → invoice; prices and price lists, discounts.
- **Customer Service**: case → queue → assignment → **SLA** (the clock runs and escalates) → resolution; entitlements.
- **Field Service / Finance & Operations** depending on the scope.
- Each process crosses roles, logic and data: the status and the fields must be consistent at each stage.

## 8. Automate

- The model-driven UI and the Canvas Apps are tested in the browser with **Playwright** (per role); locate by role/accessible name (generated IDs change).
- The model and the data, with the Dataverse **Web API** in read mode; emails/notifications with the `email-verifier`; permissions with the `permissions-tester`.

## 9. Other CRM/ERP systems

The pattern repeats: **non-production environment**, **roles/profiles**, **business logic** (rules, flows, triggers), **end-to-end processes** and a **read API** for surveying. It applies to Oracle, NetSuite, Zoho, Odoo, HubSpot and similar (Salesforce and SAP have their own skill). Confirm which one it is and adapt the artifact names.

## 10. Typical Dynamics/CRM-ERP bugs

- A role that sees or edits records it shouldn't (badly configured scope).
- A business rule or a plugin that doesn't fire, or fires twice.
- Business Process Flow that advances without meeting the stage condition.
- Roll-up or calculated field that doesn't update.
- SLA that doesn't run or doesn't escalate.
- Imported solution that breaks a form or leaves missing dependencies.
- Duplicate rule that doesn't detect (or blocks too much).
- Field with column security visible to someone who shouldn't see it.

## 11. Typical questions for the PO (Dynamics/CRM-ERP)

When it is not written down, they are `MI-XX`:

- Which CRM/ERP and which modules are in scope (Sales, Customer Service, F&O…)?
- Which environment/sandbox is used for testing (never production)? With which roles?
- Which end-to-end business processes must be covered?
- Which logic is critical (plugins, flows, BPF, roll-ups) and when must it fire?
- Are there SLAs and how must they behave?
- Model-driven, Canvas App or portal?
