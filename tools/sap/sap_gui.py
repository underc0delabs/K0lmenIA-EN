#!/usr/bin/env python3
"""
Read-only survey of a SAP GUI for Windows session through the Scripting API (COM).

Usage (from the repo root, on Windows, with SAP GUI open and logged on to a QA client):
    python tools/sap/sap_gui.py [--output output/sap/survey.json]

What it does (read-only):
- Connects to the SAP GUI that is already open through the Scripting API (it does not open or close sessions).
- Lists the open connections and sessions and, for each one, the system (SID), client, user,
  language, current transaction and program, and session metrics (round trips, response time).
- Works as a smoke check/survey: it confirms that Scripting is enabled and which system you are connected to.

It does not run transactions or change data. The sap-tester agent builds the flow automation.
Requirements: Windows, SAP GUI for Windows, `pip install pywin32`, and Scripting enabled on the server
(RZ11 sapgui/user_scripting = TRUE) and on the client (Options → Accessibility & Scripting → Scripting).
"""
import argparse
import json
import sys
from pathlib import Path


def _engine():
    """Returns the Scripting Engine of an open SAP GUI. Raises RuntimeError with a clear message if it cannot."""
    try:
        import win32com.client as win32
    except ImportError:
        raise RuntimeError("pywin32 is missing (Windows only): install it with `pip install pywin32`.")
    try:
        sapgui = win32.GetObject("SAPGUI")
    except Exception:
        raise RuntimeError("SAP GUI was not found. Open SAP GUI for Windows and log on to a QA client before surveying.")
    try:
        engine = sapgui.GetScriptingEngine
    except Exception:
        raise RuntimeError("SAP GUI Scripting is disabled. Enable it on the server (RZ11 sapgui/user_scripting = TRUE) "
                           "and on the client (Options → Accessibility & Scripting → Scripting).")
    return engine


def session_info(session):
    """Read-only data of a session (the SAP GUI Info object)."""
    i = session.Info
    def g(attr):
        try:
            return getattr(i, attr)
        except Exception:
            return None
    return {"system": g("SystemName"), "client": g("Client"), "user": g("User"), "language": g("Language"),
            "transaction": g("Transaction"), "program": g("Program"), "server": g("ApplicationServer"),
            "system_number": g("SystemNumber"), "screen": g("ScreenNumber"), "codepage": g("Codepage"),
            "round_trips": g("RoundTrips"), "response_time_ms": g("ResponseTime")}


def survey():
    """{"scripting": True, "connections": [{"description", "sessions": [session_info…]}]}."""
    engine = _engine()
    connections = []
    for ci in range(engine.Children.Count):
        conn = engine.Children(ci)
        sessions = []
        for si in range(conn.Children.Count):
            try:
                sessions.append(session_info(conn.Children(si)))
            except Exception as ex:
                sessions.append({"error": str(ex)[:160]})
        try:
            description = conn.Description
        except Exception:
            description = f"connection {ci}"
        connections.append({"description": description, "sessions": sessions})
    return {"scripting": True, "connections": connections}


def sessions_summary(connections):
    """Testable summary: connections, sessions and distinct systems (SID/client)."""
    sessions = [s for c in connections or [] for s in c.get("sessions") or [] if "error" not in s]
    systems = sorted({f'{s.get("system")}/{s.get("client")}' for s in sessions if s.get("system")})
    return {"connections": len(connections or []), "sessions": len(sessions), "systems": systems}


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass
    ap = argparse.ArgumentParser(description="Read-only survey of SAP GUI through the Scripting API.")
    ap.add_argument("--output", default="", help="path where to save the survey JSON (optional)")
    args = ap.parse_args(argv)
    try:
        data = survey()
    except RuntimeError as ex:
        print(f"[sap] {ex}", file=sys.stderr)
        return 2
    data["summary"] = sessions_summary(data["connections"])
    text = json.dumps(data, ensure_ascii=False, indent=2)
    if args.output:
        p = Path(args.output)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        print(f"[sap] Survey in {p}", file=sys.stderr)
    print(text)
    r = data["summary"]
    print(f"[sap] {r['connections']} connection(s), {r['sessions']} session(s): {', '.join(r['systems']) or '—'}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
