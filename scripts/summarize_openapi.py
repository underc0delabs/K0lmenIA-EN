#!/usr/bin/env python3
"""
Summarizes a Swagger 2.0 or OpenAPI 3.x specification in a few lines, ready to automate with the
k0lmena steps (api-case-generator and api-mapper agents).

Usage (from the repo root; on Mac/Linux, python3):
    python scripts/summarize_openapi.py <url or .json/.yaml file> [--output summary.md] [--json]

What it resolves (what made hand-written tests fail):
  - **API_BASEURL**: the server with its basePath (Swagger 2: schemes + host + basePath; OpenAPI 3: the
    first `servers` entry, with its variables and, if it is relative, against the URL of the spec). The endpoints
    of the .feature are the spec paths as is: "/pet/{petId}", without repeating the basePath.
  - **Authentication**: each securityScheme with its matching step (Bearer, API key in a
    header or in the query, basic, OAuth2) and which endpoints require it.
  - **Endpoints**: method, path, parameters (path, query, header) with their type and whether they are required,
    how the body is sent (JSON or form), a sample body built from the schema and the documented statuses.

It keeps you from dumping the whole spec into the conversation. It does not call the API: it only reads the spec.
"""
import argparse
import json
import re
import sys
import urllib.request
from pathlib import Path
from urllib.parse import urljoin, urlparse

METHODS = ("get", "post", "put", "patch", "delete", "head", "options")


# ------------------------------------------------------------------ reading the spec
def read_text(source):
    if re.match(r"^https?://", source):
        req = urllib.request.Request(source, headers={"Accept": "application/json, application/yaml, */*"})
        with urllib.request.urlopen(req, timeout=30) as r:  # noqa: S310 (URL given by the person)
            return r.read().decode("utf-8-sig")
    path = Path(source)
    if not path.exists():
        raise SystemExit(f"{path} does not exist.")
    return path.read_text(encoding="utf-8-sig")


def parse(text):
    t = text.lstrip()
    if t.startswith("{"):
        return json.loads(t)
    try:
        import yaml
    except ImportError:
        raise SystemExit("The spec is YAML and pyyaml is missing: pip install -r requirements.txt")
    return yaml.safe_load(text)


# ------------------------------------------------------------------ $ref and schemas
def resolve(spec, node, seen=None):
    """Follows local $refs (#/definitions/X, #/components/schemas/X, parameters, bodies...)."""
    seen = seen or set()
    while isinstance(node, dict) and "$ref" in node:
        ref = node["$ref"]
        if not ref.startswith("#/") or ref in seen:
            return {"description": f"(external or circular reference: {ref})"}
        seen.add(ref)
        target = spec
        for part in ref[2:].split("/"):
            target = (target or {}).get(part.replace("~1", "/").replace("~0", "~"))
        node = target or {}
    return node or {}


def type_of(spec, schema):
    s = resolve(spec, schema)
    if "$ref" in (schema or {}):
        return schema["$ref"].split("/")[-1]
    t = s.get("type")
    if t == "array":
        return f"array<{type_of(spec, s.get('items') or {})}>"
    if s.get("enum"):
        return f"{t or 'string'} ({' | '.join(map(str, s['enum'][:8]))})"
    fmt = s.get("format")
    return f"{t}{f' ({fmt})' if fmt else ''}" if t else ("object" if s.get("properties") else "?")


def example(spec, schema, level=0, refs=()):
    """A sample value from the schema: example, default or enum if present; otherwise, one of the type."""
    ref = (schema or {}).get("$ref")
    if ref in refs or level > 5:
        return None
    s = resolve(spec, schema)
    refs = refs + ((ref,) if ref else ())
    for key in ("example", "default"):
        if key in s:
            return s[key]
    if s.get("enum"):
        return s["enum"][0]
    if "allOf" in s:
        out = {}
        for part in s["allOf"]:
            v = example(spec, part, level + 1, refs)
            if isinstance(v, dict):
                out.update(v)
        return out
    for key in ("oneOf", "anyOf"):
        if s.get(key):
            return example(spec, s[key][0], level + 1, refs)
    t = s.get("type") or ("object" if s.get("properties") else None)
    if t == "object":
        return {k: example(spec, v, level + 1, refs) for k, v in (s.get("properties") or {}).items()}
    if t == "array":
        item = example(spec, s.get("items") or {}, level + 1, refs)
        return [item] if item is not None else []
    if t == "integer":
        return s.get("minimum", 1)
    if t == "number":
        return s.get("minimum", 1.5)
    if t == "boolean":
        return True
    if t == "string":
        return {"date-time": "2026-01-01T00:00:00Z", "date": "2026-01-01", "email": "qa+{random}@test.com",
                "uuid": "{uuid}", "password": "Password123!"}.get(s.get("format"), "text")
    return None


# ------------------------------------------------------------------ base URL
def base_url(spec, source):
    is_url = re.match(r"^https?://", source or "")
    if spec.get("swagger"):
        u = urlparse(source) if is_url else None
        scheme = (spec.get("schemes") or [u.scheme if u else "https"])[0]
        host = spec.get("host") or (u.netloc if u else "")
        if not host:
            return None, "The spec has no host: fill in API_BASEURL by hand (server + basePath)."
        return f"{scheme}://{host}{(spec.get('basePath') or '').rstrip('/')}", None
    servers = spec.get("servers") or []
    if not servers:
        if is_url:
            return f"{urlparse(source).scheme}://{urlparse(source).netloc}", "The spec has no servers: the host it was downloaded from is used."
        return None, "The spec has no servers: fill in API_BASEURL by hand."
    srv = servers[0]
    url = srv.get("url", "")
    for name, var in (srv.get("variables") or {}).items():
        url = url.replace("{" + name + "}", str(var.get("default", "")))
    note = f"There are {len(servers)} servers; the first one was used ({servers[0].get('description') or url})." if len(servers) > 1 else None
    if not re.match(r"^https?://", url):
        if not is_url:
            return None, f"The server is relative ({url}): fill in API_BASEURL with the host + {url}."
        url = urljoin(source, url)
    return url.rstrip("/"), note


# ------------------------------------------------------------------ security
def security_schemes(spec):
    raw = spec.get("securityDefinitions") or (spec.get("components") or {}).get("securitySchemes") or {}
    out = {}
    for name, s in raw.items():
        s = resolve(spec, s)
        t = (s.get("type") or "").lower()
        scheme = (s.get("scheme") or "").lower()
        if t == "apikey" and s.get("in") == "header":
            step = f'Given the request uses the API key in the header "{s.get("name")}"'
            env = "API_KEY"
        elif t == "apikey" and s.get("in") == "query":
            step = f'Given the request uses the API key in the parameter "{s.get("name")}"'
            env = "API_KEY"
        elif t == "apikey" and s.get("in") == "cookie":
            step = f'Given the request uses the header "Cookie" with value "{s.get("name")}={{API_KEY}}"'
            env = "API_KEY"
        elif (t == "http" and scheme == "basic") or t == "basic":
            step, env = "Given the request uses basic authentication", "API_USER and API_PASSWORD"
        elif (t == "http" and scheme == "bearer") or t in ("oauth2", "openidconnect"):
            step, env = "Given the request uses the authentication token", "API_TOKEN (an already obtained token)"
        else:
            step, env = f"(type {t} {scheme}: no generic step)", "-"
        out[name] = {"type": t + (f" {scheme}" if scheme else "") + (f" in {s.get('in')}" if s.get("in") else ""),
                     "step": step, "variable": env}
    return out


# ------------------------------------------------------------------ endpoints
def endpoints(spec):
    v2 = bool(spec.get("swagger"))
    global_security = spec.get("security")
    out = []
    for path, item in (spec.get("paths") or {}).items():
        item = resolve(spec, item)
        common = item.get("parameters") or []
        for method in METHODS:
            op = item.get(method)
            if not op:
                continue
            params = {}
            for p in common + (op.get("parameters") or []):
                p = resolve(spec, p)
                params[(p.get("in"), p.get("name"))] = p
            ep = {"method": method.upper(), "path": path, "summary": op.get("summary") or op.get("operationId") or "",
                  "tags": op.get("tags") or [], "parameters": [], "body": None, "responses": {}, "deprecated": bool(op.get("deprecated"))}
            form = {}
            for (where, name), p in params.items():
                if where == "body":
                    ep["body"] = {"type": "json", "content_type": ((op.get("consumes") or spec.get("consumes") or ["application/json"])[0]),
                                  "example": example(spec, p.get("schema") or {}), "required": bool(p.get("required"))}
                elif where == "formData":
                    form[name] = {"type": p.get("type"), "required": bool(p.get("required"))}
                else:
                    kind = type_of(spec, p.get("schema") or p) if not v2 else type_of(spec, p)
                    ep["parameters"].append({"in": where, "name": name, "type": kind, "required": bool(p.get("required"))})
            if form:
                ct = (op.get("consumes") or spec.get("consumes") or ["application/x-www-form-urlencoded"])[0]
                multipart = "multipart" in ct or any(v["type"] == "file" for v in form.values())
                ep["body"] = {"type": "multipart" if multipart else "form", "content_type": ct, "fields": form}
            rb = resolve(spec, op.get("requestBody") or {})
            if rb.get("content"):
                ct, media = next(iter(rb["content"].items()))
                for preferred in ("application/json", "application/x-www-form-urlencoded"):
                    if preferred in rb["content"]:
                        ct, media = preferred, rb["content"][preferred]
                        break
                schema = (media or {}).get("schema") or {}
                if "json" in ct:
                    ex = media.get("example") or example(spec, schema)
                    ep["body"] = {"type": "json", "content_type": ct, "example": ex, "required": bool(rb.get("required"))}
                elif "form" in ct:
                    props = resolve(spec, schema).get("properties") or {}
                    req = set(resolve(spec, schema).get("required") or [])
                    ep["body"] = {"type": "form" if "urlencoded" in ct else "multipart", "content_type": ct,
                                  "fields": {k: {"type": type_of(spec, v), "required": k in req} for k, v in props.items()}}
                else:
                    ep["body"] = {"type": "other", "content_type": ct}
            for code, r in (op.get("responses") or {}).items():
                ep["responses"][str(code)] = (resolve(spec, r).get("description") or "").strip().split("\n")[0][:120]
            sec = op.get("security", global_security)
            ep["security"] = sorted({n for req in (sec or []) for n in req})
            out.append(ep)
    return out


def summarize(spec, source):
    if not isinstance(spec, dict) or not (spec.get("swagger") or spec.get("openapi")):
        raise SystemExit("It does not look like a Swagger/OpenAPI spec (the swagger or openapi field is missing).")
    base, note = base_url(spec, source)
    return {"title": (spec.get("info") or {}).get("title", ""), "api_version": (spec.get("info") or {}).get("version", ""),
            "format": f"Swagger {spec['swagger']}" if spec.get("swagger") else f"OpenAPI {spec['openapi']}",
            "api_baseurl": base, "base_note": note, "security": security_schemes(spec), "endpoints": endpoints(spec)}


# ------------------------------------------------------------------ output
def to_markdown(r, source):
    lines = [f"# {r['title'] or 'API'} ({r['format']}, version {r['api_version'] or '-'})", "", f"Source: {source}", "",
             "## .env configuration", "",
             f"API_BASEURL={r['api_baseurl'] or '<fill in: server + basePath>'}",
             "", "The `.feature` endpoints use the spec path as is (without repeating the basePath)."]
    if r["base_note"]:
        lines += ["", f"> {r['base_note']}"]
    lines += ["", "## Authentication", ""]
    if r["security"]:
        for name, s in r["security"].items():
            users = sum(1 for e in r["endpoints"] if name in e["security"])
            lines.append(f"- **{name}** ({s['type']}, {users} endpoint(s)): `{s['step']}` · variable: {s['variable']}")
    else:
        lines.append("- The spec does not declare authentication.")
    lines += ["", f"## Endpoints ({len(r['endpoints'])})", ""]
    for e in r["endpoints"]:
        tags = f" · {', '.join(e['tags'])}" if e["tags"] else ""
        dep = " · DEPRECATED" if e["deprecated"] else ""
        lines.append(f"### {e['method']} {e['path']}{tags}{dep}")
        if e["summary"]:
            lines.append(e["summary"])
        if e["security"]:
            lines.append(f"- Authentication: {', '.join(e['security'])}")
        for p in e["parameters"]:
            lines.append(f"- {p['in']} `{p['name']}`: {p['type']}{' (required)' if p['required'] else ''}")
        b = e["body"]
        if b and b["type"] == "json":
            lines.append(f"- JSON body ({b['content_type']}){' required' if b.get('required') else ''}: "
                         f"`{json.dumps(b['example'], ensure_ascii=False)[:400]}`")
        elif b and b["type"] in ("form", "multipart"):
            fields = ", ".join(f"{k} ({v['type']}{', required' if v['required'] else ''})" for k, v in b["fields"].items())
            step = "with the form:" if b["type"] == "form" else "(multipart: no generic step, e.g. file uploads)"
            lines.append(f"- {b['type'].capitalize()} body ({b['content_type']}) → `{step}` · fields: {fields}")
        elif b:
            lines.append(f"- {b['content_type']} body: no generic step")
        if e["responses"]:
            lines.append("- Documented responses: " + "; ".join(f"{c} {d}".strip() for c, d in e["responses"].items()))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Summarizes a Swagger 2.0 or OpenAPI 3.x spec to automate it with k0lmena")
    ap.add_argument("source", help="URL or .json/.yaml file of the spec")
    ap.add_argument("--output", help="saves the summary to this .md file (in addition to showing it)")
    ap.add_argument("--json", action="store_true", help="shows the summary as JSON")
    a = ap.parse_args(argv)
    r = summarize(parse(read_text(a.source)), a.source)
    text = json.dumps(r, ensure_ascii=False, indent=2) if a.json else to_markdown(r, a.source)
    if a.output:
        Path(a.output).parent.mkdir(parents=True, exist_ok=True)
        Path(a.output).write_text(text, encoding="utf-8")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
