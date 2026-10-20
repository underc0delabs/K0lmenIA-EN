#!/usr/bin/env python3
"""
Survey of a SOAP service from its WSDL, and generation of a sample envelope.
Read-only, no external dependencies (uses the standard library xml).

Usage (from the repo root):
    python tools/soap/wsdl.py --wsdl http://host/service?wsdl   [--output output/soap/service.json]
    python tools/soap/wsdl.py --wsdl C:/path/service.wsdl --operation GetUser

What it does:
- Reads the WSDL (from a URL or a file) and extracts the service, the endpoint, the SOAP version and the
  operations (name, SOAPAction, input/output messages).
- With `--operation`, prints a sample SOAP envelope for that operation (a base for the tests).

It does not invoke or modify the service: the soap-tester agent does that (with confirmation for operations
with side effects), sending the envelopes over HTTP.
"""
import argparse
import json
import sys
import urllib.request
from pathlib import Path
from xml.etree import ElementTree as ET

SOAP11 = "http://schemas.xmlsoap.org/wsdl/soap/"
SOAP12 = "http://schemas.xmlsoap.org/wsdl/soap12/"


def _ln(tag):
    """Local name of a namespaced tag ({ns}tag -> tag)."""
    return tag.split("}", 1)[-1] if "}" in tag else tag


def parse_wsdl(xml_text):
    """Parses the text of a WSDL. Returns service, endpoint, version and operations. Pure and testable."""
    root = ET.fromstring(xml_text)
    tns = root.get("targetNamespace")
    # soapAction per operation (from the bindings)
    actions, soap12 = {}, False
    for binding in root.iter():
        if _ln(binding.tag) != "binding":
            continue
        for child in binding:
            if _ln(child.tag) == "binding" and child.get("transport"):
                if SOAP12 in (child.tag or ""):
                    soap12 = True
        for op in binding:
            if _ln(op.tag) != "operation":
                continue
            name = op.get("name")
            for sub in op:
                if _ln(sub.tag) == "operation":
                    actions[name] = sub.get("soapAction", "")
                    if SOAP12 in (sub.tag or ""):
                        soap12 = True
    # portType operations (with their messages)
    operations = []
    for pt in root.iter():
        if _ln(pt.tag) != "portType":
            continue
        for op in pt:
            if _ln(op.tag) != "operation":
                continue
            name = op.get("name")
            inp = out = None
            for m in op:
                if _ln(m.tag) == "input":
                    inp = m.get("message") or m.get("name")
                elif _ln(m.tag) == "output":
                    out = m.get("message") or m.get("name")
            operations.append({"name": name, "soap_action": actions.get(name, ""), "input": inp, "output": out})
    # endpoint (service/port/address@location)
    endpoint, service = None, None
    for svc in root.iter():
        if _ln(svc.tag) != "service":
            continue
        service = svc.get("name")
        for port in svc:
            for addr in port:
                if _ln(addr.tag) == "address" and addr.get("location"):
                    endpoint = addr.get("location")
    return {"service": service, "endpoint": endpoint, "namespace": tns,
            "version": "1.2" if soap12 else "1.1", "operations": operations}


def envelope(operation, params=None, namespace="http://tempuri.org/", soap12=False):
    """Sample SOAP envelope for an operation. Pure and testable."""
    ns_env = "http://www.w3.org/2003/05/soap-envelope" if soap12 else "http://schemas.xmlsoap.org/soap/envelope/"
    body = ""
    for k, v in (params or {}).items():
        body += f"\n      <ns:{k}>{v}</ns:{k}>"
    return (f'<soapenv:Envelope xmlns:soapenv="{ns_env}" xmlns:ns="{namespace}">\n'
            f'  <soapenv:Header/>\n'
            f'  <soapenv:Body>\n'
            f'    <ns:{operation}>{body}\n'
            f'    </ns:{operation}>\n'
            f'  </soapenv:Body>\n'
            f'</soapenv:Envelope>')


def read(source):
    if source.lower().startswith(("http://", "https://")):
        with urllib.request.urlopen(source, timeout=30) as r:
            return r.read().decode("utf-8", "replace")
    return Path(source).read_text(encoding="utf-8", errors="replace")


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except Exception:
            pass
    ap = argparse.ArgumentParser(description="Survey of a SOAP service through its WSDL (read-only).")
    ap.add_argument("--wsdl", required=True, help="URL or path of the WSDL")
    ap.add_argument("--operation", default="", help="prints a sample envelope for this operation")
    ap.add_argument("--output", default="")
    args = ap.parse_args(argv)
    try:
        xml_text = read(args.wsdl)
        info = parse_wsdl(xml_text)
    except (OSError, ET.ParseError) as ex:
        print(f"[soap] Could not read or parse the WSDL: {ex}", file=sys.stderr)
        return 2
    if args.operation:
        print(envelope(args.operation, namespace=info.get("namespace") or "http://tempuri.org/",
                       soap12=info.get("version") == "1.2"))
        return 0
    text = json.dumps(info, ensure_ascii=False, indent=2)
    if args.output:
        p = Path(args.output)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        print(f"[soap] Data in {p}", file=sys.stderr)
    print(text)
    print(f"[soap] Service {info.get('service') or '—'} (SOAP {info.get('version')}): {len(info.get('operations') or [])} operation(s).", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
