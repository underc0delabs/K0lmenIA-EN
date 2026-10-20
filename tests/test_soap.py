"""SOAP tester: WSDL parsing, sample envelope and HTML report."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tools" / "soap"))

import generate_soap_report as gi  # noqa: E402
import wsdl  # noqa: E402

WSDL = """<?xml version="1.0"?>
<definitions xmlns="http://schemas.xmlsoap.org/wsdl/"
             xmlns:soap="http://schemas.xmlsoap.org/wsdl/soap/"
             xmlns:tns="http://example.org/customers"
             targetNamespace="http://example.org/customers">
  <portType name="CustomerPortType">
    <operation name="GetCustomer">
      <input message="tns:GetCustomerReq"/>
      <output message="tns:GetCustomerResp"/>
    </operation>
  </portType>
  <binding name="CustomerBinding" type="tns:CustomerPortType">
    <soap:binding transport="http://schemas.xmlsoap.org/soap/http" style="document"/>
    <operation name="GetCustomer">
      <soap:operation soapAction="http://example.org/customers/GetCustomer"/>
    </operation>
  </binding>
  <service name="CustomerService">
    <port name="CustomerPort" binding="tns:CustomerBinding">
      <soap:address location="https://host/ws"/>
    </port>
  </service>
</definitions>"""


def test_parse_wsdl():
    info = wsdl.parse_wsdl(WSDL)
    assert info["service"] == "CustomerService"
    assert info["endpoint"] == "https://host/ws"
    assert info["version"] == "1.1"
    assert info["namespace"] == "http://example.org/customers"
    ops = {o["name"]: o for o in info["operations"]}
    assert "GetCustomer" in ops
    assert ops["GetCustomer"]["soap_action"] == "http://example.org/customers/GetCustomer"


def test_envelope():
    env = wsdl.envelope("GetCustomer", {"id": "42"}, namespace="http://example.org/customers")
    assert "<ns:GetCustomer>" in env and "<ns:id>42</ns:id>" in env
    assert 'xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/"' in env  # SOAP 1.1 by default


def test_report(tmp_path, monkeypatch):
    monkeypatch.setenv("K0LMENIA_PORTAL", "0")
    data = {"title": "CustomerService — US-010", "service": {"name": "CustomerService", "endpoint": "https://host/ws", "version": "1.1"},
            "verdict": "1 badly mapped fault", "verdict_tone": "warn",
            "operations": [{"operation": "GetCustomer", "soap_action": "...", "result": "Passed", "detail": "ok"}],
            "tests": [{"id": "TC-001", "operation": "GetCustomer", "case": "Nonexistent customer", "result": "Failed",
                       "expected": "SOAP Fault NotFound", "actual": "HTTP 500"}],
            "findings": [{"id": "F-01", "severity": "High", "category": "Error handling", "text": "500 instead of a Fault",
                          "impact": "the client cannot tell the error apart", "how_to_reproduce": "request a nonexistent id", "recommendation": "return a Fault"}],
            "missing_info": [{"id": "MI-01", "what_is_missing": "defined Faults", "question": "which Faults does the operation define?"}]}
    (tmp_path / "a.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    gi.generate(tmp_path / "a.json", tmp_path / "i.html")
    html = (tmp_path / "i.html").read_text(encoding="utf-8")
    assert "CustomerService" in html and "500 instead of a Fault" in html and "Service operations" in html and "MI-01" in html
    assert "request a nonexistent id" in html


def test_invalid_json_fails(tmp_path):
    (tmp_path / "x.json").write_text("{", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        gi.generate(tmp_path / "x.json", tmp_path / "i.html")
