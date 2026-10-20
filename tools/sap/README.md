# SAP

**Read-only** survey of a SAP GUI for Windows session through the **Scripting API** (COM). Used by the `sap-tester` agent as a smoke check/survey before automating the flows.

- **`sap_gui.py`** (`npm run sap`) — connects to the already open SAP GUI, lists connections and sessions and, for each one, the system (SID), client, user, language, current transaction and program, plus metrics (round trips, response time). It confirms that Scripting is enabled and which system you are connected to.

```bash
npm run sap -- --output output/sap/survey.json
```

Read-only: it does not run transactions or change data. The `sap-tester` builds the flow automation (SAP GUI Scripting, Playwright for Fiori, OData with the api-runner).

**Requirements**: Windows, SAP GUI for Windows, `pip install pywin32`, and Scripting enabled on the server (RZ11 `sapgui/user_scripting = TRUE`) and on the client (Options → Accessibility & Scripting → Scripting). Always against a **QA client**, never production.
