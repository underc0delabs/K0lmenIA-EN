# Desktop

**Read-only** survey of the control tree of a Windows desktop app with **pywinauto** (UI Automation). Used by the `desktop-tester` agent as input to locate the controls before automating.

- **`controls.py`** (`npm run desktop`) — connects to an already open app by title (regex) or PID, with the `uia` backend (modern WPF/UWP/WinForms) or `win32` (classic Win32), and dumps the control tree (type, name, automation id, class) with a summary (total, by type, how many lack an accessible name). It is the app's "DOM".

```bash
npm run desktop -- --title "Invoicer.*" --output output/desktop/tree.json
npm run desktop -- --process 1234 --backend win32 --depth 5
```

It does not click or change anything. For **Electron** apps, automate them as web (Playwright); this is for **native Windows** apps. Test execution is handled by the `desktop-tester` (Appium + WinAppDriver, pywinauto, or Playwright for Electron).

**Requirements**: Windows, `pip install pywinauto`. For driving with Appium: Appium + Windows Application Driver (WinAppDriver).
