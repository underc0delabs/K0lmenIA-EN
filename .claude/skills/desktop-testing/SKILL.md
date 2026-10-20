---
name: desktop-testing
description: How to test Windows desktop applications — by technology (WinForms, WPF, UWP/WinUI, classic Win32, Electron, Java Swing/SWT, Qt) and its automation tool (Appium + Windows Application Driver/WinAppDriver, pywinauto with UI Automation, Playwright/CDP for Electron, Java Access Bridge for Java); the control tree and locators (AutomationId, Name, ControlType, ClassName) and how to survey it read-only (controls.py); functional tests (windows and modal dialogs, menus and toolbars, forms and field validation, keyboard shortcuts, focus and tab order, drag and drop, clipboard, multi-document); installation and smoke (installer, first launch, update and rollback, uninstall, UAC/administrator permissions); files and data (open/save, formats, paths with spaces and Unicode, file system permissions); OS integration (registry, services, tray, notifications, multi-monitor and DPI/scaling, printing); regression after a new version, performance (startup, memory and CPU, leaks, UI responsiveness, large files), security (storage of credentials and secrets on disk or in the registry, executable signing, secure updates, least privilege) and accessibility (UIA names, keyboard, screen readers); how to automate it, typical bugs and questions for the PO. Used by the desktop-tester and by the mappers when they automate a desktop app.
---

# Desktop application testing (Windows)

A desktop app is not a website: it lives in the operating system (windows, registry, files, services, permissions) and is automated with **UI Automation**, not with a browser (except Electron). The first thing is to know **which technology it is built with**, because that defines the tool.

## 1. Before testing

- **UI technology**: WinForms, WPF, UWP/WinUI, classic Win32, **Electron** (embedded web), **Java** (Swing/SWT) or **Qt**. It changes the locator and the tool.
- App **version and build**, **operating system** (Windows 10/11, Server), **architecture** (x86/x64/ARM) and **resolution/DPI scaling** (100/125/150/200 %): many layout bugs show up with high DPI or on small screens.
- **Installer** (MSI, EXE, MSIX, ClickOnce, portable) and whether it requires **administrator privileges (UAC)**.
- **Test environment**: a QA machine or VM, not the production one; test data and a way to return to the initial state (restore, reinstall).

## 2. Automation tool by technology

```
+---------------------------+---------------------------------------------------------------+
| Technology                | How it is automated                                           |
+===========================+===============================================================+
| WinForms / WPF / WinUI    | Appium + WinAppDriver, or pywinauto with the `uia` backend    |
| Classic Win32             | pywinauto `win32` backend (or `uia` if it exposes UIA)        |
| UWP                       | Appium + WinAppDriver (by the package AppId)                  |
| Electron                  | Like the web: Playwright/Chromium DevTools (not UI Automation)|
| Java (Swing/SWT)          | Java Access Bridge (enable it) + UIA, or Java tools           |
| Qt                        | UIA if it exposes accessibility; otherwise Squish or OCR/image|
+---------------------------+---------------------------------------------------------------+
```

- **Appium + WinAppDriver** (Windows Application Driver) is the path that matches the Appium k0lmena already uses for mobile: `windows` driver, `app` = executable path or AppId. It needs Windows **Developer Mode** and WinAppDriver running.
- **pywinauto** is used to **survey** (dump the control tree read-only, `npm run desktop`) and to drive the app from Python.
- **Electron** is not automated with UIA: it is Chromium; use Playwright against its renderer process.

## 3. Control tree and locators

- Controls are located by **AutomationId** (the most stable, if the developer set it), **Name** (accessible name), **ControlType** (Button, Edit, List…) and **ClassName**.
- **Survey the tree** with `tools/desktop/controls.py` (`npm run desktop --title "<regex>"`): it is the app's "DOM" and shows which controls have an AutomationId and which lack an accessible name (a problem for automation **and** for accessibility).
- Avoid locating by position/index or by coordinates: they break when the layout or the DPI changes.

## 4. Functional tests

- **Windows and dialogs**: modals that block the main window, closing with the X / Esc / Cancel, confirmation when exiting with unsaved changes, windows that don't end up off-screen.
- **Menus and toolbars**: menu, toolbar, context menu (right click), ribbon; items enabled/disabled according to state.
- **Forms and validation**: required fields, formats (numbers, dates, masks), length limits, error messages, and **focus** going to the first field with an error.
- **Keyboard**: shortcuts (Ctrl+S, Ctrl+Z/Y, F1…), logical **tab order**, Enter/Esc in dialogs, mnemonics (Alt+letter).
- **Drag and drop**, **clipboard** (copy/paste between the app and others), and **multi-document (MDI)** if applicable.
- **State and persistence**: window size/position, recent files, preferences that survive a restart.

## 5. Installation, update and smoke

- **Installation**: clean install, choosing a folder with spaces/Unicode, with and without admin privileges (UAC), shortcuts and Start menu entries.
- **First launch** (smoke): the app opens without errors, the main window loads and a basic action works.
- **Update**: from the previous version to the new one keeping data and preferences; **rollback** if it fails.
- **Uninstall**: removes files, shortcuts and (as expected) registry keys; which user data is intentionally left behind.

## 6. Smoke test

Quick and blocking, on the QA VM:

1. The app opens without errors or crashes and the main window loads.
2. Login (if applicable) with a test user.
3. A core action in scope (opening a document, creating a record) works.
4. Saving and reopening keeps the data.
5. Closing the app doesn't leave the process hanging.

## 7. Files and data

- **Open/save**: each supported format, nonexistent file, corrupt file, read-only file, file opened by another process (lock), long/Unicode path, network drive.
- **File system permissions**: saving to a folder without permission gives a clear error, not a crash.
- **Autosave and recovery** after an unexpected shutdown.

## 8. Operating system integration

- **Registry and configuration**: where it stores the config (registry, `%AppData%`, `%ProgramData%`); it must not require writing to `Program Files`.
- **Services and background processes**, **tray icon** and **notifications**.
- **Multi-monitor and DPI**: moving the window between monitors with different scaling without breaking the layout or cutting off text.
- **Printing** and print preview, if applicable.

## 9. Regression

- After **a new version or a patch**: run the main flow (extended smoke), the areas the change touches and compatibility with file formats from previous versions.
- Ideally it is automated (Appium/WinAppDriver or pywinauto via `web-mapper`/mapper and `npm test`) to repeat the regression on each build without tokens.

## 10. Performance

- **Cold and warm startup**, **memory and CPU usage** at idle and under use, **memory leaks** (handles, memory that grows and doesn't go down after closing documents).
- **UI responsiveness**: it must not freeze ("Not Responding") during long operations; there should be feedback (progress) and the UI must not block the thread.
- **Large files** / many records: load and scroll times. Measure with the resource monitor; for load, coordinate with `performance-guide`.

## 11. Security

Scanning and exploitation are done by the `security-analyst` and the `web-pentester` (for the network/services part); specific to desktop:

- **Credentials and secrets**: not stored in plain text in files, the registry or logs; use DPAPI/Credential Manager. Tokens must not be left readable in `%AppData%`.
- Valid **signature of the executable and the installer** (Authenticode); **secure updates** (over HTTPS and signed), not a channel that can be spoofed.
- **Least privilege**: the app doesn't run as administrator if it doesn't need to; it doesn't write to protected paths.
- **Communications** with the backend over TLS; certificates validated (no `TrustAll`).
- **Sensitive data** in memory and in temporary disk files; cleanup on close.

## 12. Accessibility

- Controls have an **accessible name (UIA Name)** and the correct **ControlType**: what is missing for a screen reader is also missing for automation (`controls.py` flags it).
- **Full keyboard navigation**, visible focus, contrast, and the OS text scaling must not cut off content.

## 13. Automate

- **Appium + WinAppDriver**: session with `platformName: Windows`, `app` = path of the .exe or AppId; locate by AutomationId/Name/ControlType; wait for the window/control to exist before acting.
- **pywinauto**: `uia` backend (modern) or `win32` (classic); `connect(title_re=..., process=...)`, then `window(...).child_window(auto_id=..., control_type=...)`.
- **Electron**: Playwright against the renderer process (it is Chromium), not UIA.
- First **survey** the tree with `controls.py` to choose stable locators; avoid indexes and coordinates.
- Leave a clean state between scenarios (close dialogs, return to the initial screen, delete test data).

## 14. Typical desktop bugs

- Broken layout or cut-off text with **high DPI** or on small screens.
- The app **freezes** ("Not Responding") during a long operation with no feedback.
- **Memory/handle leak**: memory grows and doesn't go down when closing documents.
- Modal dialog that doesn't take focus or that lets you keep using the main window.
- Data or preferences **lost** when upgrading versions.
- Unhandled error (crash/stack trace) when opening a corrupt file or one without permission.
- Controls **without an AutomationId or accessible name**: they can't be automated or read with a screen reader.
- The app requires **administrator privileges** unnecessarily or writes to `Program Files`.
- Credentials stored in plain text in the registry or in `%AppData%`.
- Process that **keeps hanging** after closing the window.

## 15. Typical questions for the PO (desktop)

When it is not written down, they are `MI-XX`:

- Which technology is the app built with (WinForms/WPF/UWP/Electron/Java/Qt)?
- Which Windows versions and which DPI scalings must be supported?
- How is it installed (MSI/EXE/MSIX/ClickOnce) and does it require admin?
- Where does it store the configuration and the user data?
- Which file formats does it open/save, and must compatibility with old versions be maintained?
- Are there backends/services it integrates with, and over which channel?
- Does the testing include installation/update, performance, security and accessibility, or only functional?
