"""Test management integration: publishing per story and API retries."""
import http.server
import threading

import pytest

import common
import management


class FakeTrace:
    def __init__(self, name, cases, us=None):
        self.path = type("R", (), {"stem": name, "name": name + ".json"})()
        self.data = {"cases": cases, **({"us": us} if us else {})}

    def key_of(self, cid):
        return (self.data["cases"].get(cid) or {}).get("key")


PATTERN = r"^PROJ-(TC-)?\d+$"


def test_tc_from_another_story_is_not_published():
    trace = FakeTrace("US-001-xray-cloud", {"TC-001": {"key": "PROJ-45"}})
    own = {"tags": ["US-001", "TC-001"]}
    other = {"tags": ["US-002", "TC-001"]}
    no_us = {"tags": ["TC-001"]}
    direct = {"tags": ["PROJ-99"]}
    assert management._key_from_result(own, trace, PATTERN) == ("PROJ-45", None)
    key, reason = management._key_from_result(other, trace, PATTERN)
    assert key is None and "another story" in reason
    key, reason = management._key_from_result(no_us, trace, PATTERN)
    assert key is None and "@US-001" in reason
    assert management._key_from_result(direct, trace, PATTERN) == ("PROJ-99", None)


def test_invalid_traceability_name():
    with pytest.raises(common.ManagementError):
        common.Traceability("../../outside", "xray-cloud")


def test_retry_resends_full_attachment(tmp_path):
    received = []

    class Server(http.server.BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
            received.append(b"EVIDENCE" * 50 in body)
            if len(received) == 1:
                self.send_response(503)
                self.send_header("Retry-After", "1")
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(b'{"ok": true}')

        def log_message(self, *args):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), Server)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    file = tmp_path / "e.png"
    file.write_bytes(b"EVIDENCE" * 50)
    http_ = common.Http(f"http://127.0.0.1:{srv.server_port}")
    with open(file, "rb") as f:
        assert http_.post("attachment", files={"file": ("e.png", f, "image/png")}) == {"ok": True}
    srv.shutdown()
    assert received == [True, True]


def test_network_cut_gives_clear_error(monkeypatch):
    monkeypatch.setattr(common.time, "sleep", lambda s: None)
    with pytest.raises(common.ManagementError, match="did not respond"):
        common.Http("http://127.0.0.1:1").get("x")


def test_waits_retry_after():
    assert common._retry_wait("3", 0) == 3
    assert common._retry_wait(None, 2) == 4
    assert common._retry_wait("Wed, 21 Oct 2015 07:28:00 GMT", 0) >= 1
