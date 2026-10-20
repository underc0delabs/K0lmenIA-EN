# Salesforce (sf CLI)

QA tool for Salesforce orgs. Used by the `salesforce-tester` agent.

- **`inventory.py`** — surveys an **authorized** org (sandbox) **read-only**: the organization (sandbox vs. production), profiles and active users per profile, permission sets, record types, validation rules, flows (and any Process Builders still active), Apex triggers, Apex coverage, sharing model (OWD) of the objects, duplicate rules, approval processes and org limits. It computes findings (coverage < 75 %, active Process Builders, several triggers per object, open OWD, inactive rules, nearly exhausted limits) and test suggestions (one negative per validation, a bulk of 200 per trigger, flows per path, access per profile, record types). With `--apex` it also runs the local Apex tests with coverage. It writes `salesforce.json` and `salesforce-report.html` (`scripts/generate_salesforce_report.py`) to `output/salesforce/<story or alias>/`.

## Requirements

- **Salesforce CLI (`sf`)** on the PATH: `npm install --global @salesforce/cli` (`npm run doctor` warns if it is missing).
- The org **authorized locally** before using it:
  ```bash
  sf org login web --alias my-qa-sandbox --instance-url https://test.salesforce.com
  ```

## Usage

```bash
# Read-only inventory:
npm run salesforce -- --org my-qa-sandbox --story US-010 --confirm
# Specific objects for the sharing model:
npm run salesforce -- --org my-qa-sandbox --objects Account,Opportunity,Order__c --confirm
# Also run the Apex tests with coverage (sandbox only):
npm run salesforce -- --org my-qa-sandbox --apex --confirm
```

## Authorization and scope

- **Only orgs in `SALESFORCE_AUTHORIZED_ORGS`** in the `.env` (comma-separated aliases). `SALESFORCE_ORG` is the default org.
- **Never production**: the tool checks `Organization.IsSandbox` and stops. Surveying a production org read-only requires `--allow-production` **and** explicit authorization; even then, without `--apex`.
- It is **read-only**: the SOQL queries go to `sf data query` through a file. It does **not** create, edit or delete records, metadata, users or permissions. Running the Apex tests (`--apex`) leaves no data but consumes asynchronous limits; that is why it is confirmed.

Each person enables the **`salesforce`** MCP connector (read-only SOQL and `run_apex_test`) with `npm run connector -- activate salesforce`.
