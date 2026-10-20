"""Bruno and Insomnia collections → Postman, GraphQL in the Newman results and schema summaries."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import convert_collection as cc  # noqa: E402
import newman_to_results as nar  # noqa: E402
import summarize_graphql as rg  # noqa: E402

API = ROOT / "input" / "api"


def _requests(items):
    for i in items:
        if "item" in i:
            yield from _requests(i["item"])
        else:
            yield i


def _script(item, kind):
    return "\n".join(next(e["script"]["exec"] for e in item.get("event", []) if e["listen"] == kind))


# --------------------------------------------------------------------------- format

def test_detects_format_of_each_demo():
    assert cc.detect_format(API / "demo-bruno") == "bruno"
    assert cc.detect_format(API / "demo.insomnia.json") == "insomnia4"
    assert cc.detect_format(API / "demo.postman_collection.json") == "postman"
    assert cc.detect_format(API / "demo-graphql.postman_collection.json") == "postman"
    assert cc.detect_format(API / "auth-endpoints.md") is None


def test_insomnia_and_bruno_variables_end_up_as_postman():
    warnings = []
    assert cc.variables("{{ _.base_url }}/a/{{_['id-x']}}?t={{ token }}", warnings) == "{{base_url}}/a/{{id-x}}?t={{token}}"
    assert cc.variables("{{process.env.SECRET}}", warnings, "r") == "{{SECRET}}"
    cc.variables("{% response 'body', 'req_1', 'b64::JC5pZA==::46b' %}", warnings, "r")
    assert len(warnings) == 2 and "template tags" in warnings[1]


# --------------------------------------------------------------------------- Bruno

def test_parses_bru_blocks_with_disabled_and_text():
    blocks = cc.parse_bru("""meta {
  name: Login
  seq: 2
}

post {
  url: {{base_url}}/login
  body: json
  auth: bearer
}

headers {
  X-Tenant: demo
  ~X-Debug: 1
}

body:json {
  {
    "user": "ana"
  }
}

vars:secret [
  token,
  password
]
""")
    assert blocks["meta"]["name"] == ("Login", True)
    assert blocks["headers"]["X-Debug"] == ("1", False)
    assert json.loads(blocks["body:json"]) == {"user": "ana"}
    assert blocks["vars:secret"] == ["token", "password"]


def test_bruno_demo_converts_requests_asserts_and_environment():
    conv = cc.convert(API / "demo-bruno")
    assert conv.warnings == []
    folder = conv.collection["item"][0]
    assert folder["name"] == "Posts"
    names = [r["name"] for r in folder["item"]]
    assert names == ["API-001 — Get an existing post (High)", "API-002 — Create a post (Medium)",
                     "API-003 — Nonexistent post returns 404 (Medium)"]
    create = folder["item"][1]
    assert create["request"]["method"] == "POST" and create["request"]["url"] == "{{base_url}}/posts"
    assert json.loads(create["request"]["body"]["raw"])["title"] == "k0lmenIA"
    test = _script(create, "test")
    assert 'pm.test("res.status: eq 201", function () { expect(res.status).to.eql(201); });' in test
    assert 'expect(res.body.title).to.eql("k0lmenIA")' in test
    assert 'pm.collectionVariables.set("createdId", res.body.id);' in test
    assert "const res = {" in test  # the Bruno adapter
    assert conv.environment["values"] == [{"key": "base_url", "value": "https://jsonplaceholder.typicode.com", "enabled": True}]


def test_bruno_graphql_auth_secrets_and_warnings(tmp_path):
    (tmp_path / "bruno.json").write_text('{"version": "1", "name": "GQL", "type": "collection"}', encoding="utf-8")
    (tmp_path / "environments").mkdir()
    (tmp_path / "environments" / "Dev.bru").write_text("vars {\n  url: https://dev\n}\nvars:secret [\n  token\n]\n", encoding="utf-8")
    (tmp_path / "environments" / "Prod.bru").write_text("vars {\n  url: https://prod\n}\n", encoding="utf-8")
    (tmp_path / "Country.bru").write_text("""meta {
  name: Country
  type: graphql
  seq: 1
}

post {
  url: {{url}}/graphql
  body: graphql
  auth: bearer
}

auth:bearer {
  token: {{token}}
}

body:graphql {
  query Country($code: ID!) {
    country(code: $code) { name }
  }
}

body:graphql:vars {
  { "code": "AR" }
}

assert {
  res.body.data.country.name: eq Argentina
  res.body.errors: isUndefined
  res.status: strangeOperator 1
}

script:pre-request {
  const x = await bru.runRequest('other');
}
""", encoding="utf-8")
    (tmp_path / "Upload.bru").write_text("""meta {
  name: Upload
  seq: 2
}

post {
  url: {{url}}/upload
  body: multipartForm
  auth: awsv4
}

body:multipart-form {
  name: ana
  attachment: @file(./photo.png)
}
""", encoding="utf-8")
    conv = cc.convert(tmp_path, environment="dev")
    country, upload = conv.collection["item"]
    assert country["request"]["body"] == {"mode": "graphql", "graphql": {
        "query": "query Country($code: ID!) {\n  country(code: $code) { name }\n}", "variables": '{ "code": "AR" }'}}
    assert country["request"]["auth"]["bearer"][0]["value"] == "{{token}}"
    assert 'expect(res.body.data.country.name).to.eql("Argentina")' in _script(country, "test")
    assert upload["request"]["body"]["formdata"][1]["type"] == "file"
    assert {v["key"]: v["value"] for v in conv.environment["values"]} == {"url": "https://dev", "token": ""}
    warnings = " | ".join(conv.warnings)
    for expected in ("strangeOperator", "bru.runRequest", "awsv4", "attachment", "secret"):
        assert expected in warnings
    not_chosen = cc.convert(tmp_path)
    assert not_chosen.environment is None and any("several environments" in a for a in not_chosen.warnings)


# --------------------------------------------------------------------------- Insomnia

def test_insomnia_v4_demo_converts_variables_params_scripts_and_environment():
    conv = cc.convert(API / "demo.insomnia.json")
    assert conv.warnings == []
    reqs = list(_requests(conv.collection["item"]))
    assert [r["name"][:7] for r in reqs] == ["API-001", "API-002", "API-003"]  # sorted by metaSortKey
    assert reqs[0]["request"]["url"] == "{{base_url}}/posts/1"
    assert reqs[2]["request"]["url"] == "{{base_url}}/posts?userId=1"
    assert _script(reqs[0], "test").startswith("// Adapted from Insomnia")
    assert "const insomnia = pm;" in _script(reqs[0], "test")
    assert conv.environment["name"] == "JSONPlaceholder"


def test_insomnia_v4_graphql_auth_and_what_is_not_converted(tmp_path):
    export = {"_type": "export", "__export_format": 4, "resources": [
        {"_id": "wrk", "_type": "workspace", "parentId": None, "name": "API"},
        {"_id": "env", "_type": "environment", "parentId": "wrk", "name": "Base", "data": {"api": {"url": "https://x"}}},
        {"_id": "r1", "_type": "request", "parentId": "wrk", "name": "Country", "method": "POST", "url": "{{ _.api.url }}/graphql",
         "body": {"mimeType": "application/graphql", "text": json.dumps({"query": "query Country { country { name } }", "variables": {"c": 1}})},
         "authentication": {"type": "bearer", "token": "{{ _.token }}"}},
        {"_id": "r2", "_type": "request", "parentId": "wrk", "name": "Chained", "method": "GET",
         "url": "https://x/{% response 'body', 'r1', 'b64::JC5pZA==::46b' %}", "authentication": {"type": "oauth2"}},
        {"_id": "ut", "_type": "unit_test", "parentId": "s", "name": "test"},
    ]}
    file = tmp_path / "export.json"
    file.write_text(json.dumps(export), encoding="utf-8")
    conv = cc.convert(file)
    reqs = {r["name"]: r for r in conv.collection["item"]}
    country, chained = reqs["Country"], reqs["Chained"]
    assert country["request"]["url"] == "{{api.url}}/graphql"
    assert country["request"]["body"]["mode"] == "graphql"
    assert country["request"]["body"]["graphql"]["query"] == "query Country { country { name } }"
    assert json.loads(country["request"]["body"]["graphql"]["variables"]) == {"c": 1}
    assert country["request"]["auth"] == cc._auth_bearer("{{token}}")
    assert conv.environment["values"] == [{"key": "api.url", "value": "https://x", "enabled": True}]
    warnings = " | ".join(conv.warnings)
    assert "template tags" in warnings and "oauth2" in warnings and "unit tests" in warnings
    assert "auth" not in chained["request"]


def test_insomnia_v5_yaml(tmp_path):
    pytest.importorskip("yaml")
    file = tmp_path / "collection.yaml"
    file.write_text("""type: collection.insomnia.rest/5.0
name: Demo v5
collection:
  - name: Posts
    children:
      - url: "{{ _.base_url }}/posts/1"
        name: Get post
        method: GET
        meta: {sortKey: 2}
        scripts:
          afterResponse: "insomnia.test('200', () => insomnia.expect(insomnia.response.code).to.eql(200));"
      - url: "{{ _.base_url }}/posts"
        name: Create post
        method: POST
        meta: {sortKey: 1}
        body: {mimeType: application/json, text: '{"title": "x"}'}
        headers: [{name: Content-Type, value: application/json}]
environments:
  name: Base Environment
  data: {base_url: "https://jsonplaceholder.typicode.com"}
  subEnvironments:
    - name: Local
      data: {base_url: "http://localhost:3000"}
""", encoding="utf-8")
    assert cc.detect_format(file) == "insomnia5"
    conv = cc.convert(file)
    posts = conv.collection["item"][0]
    assert [r["name"] for r in posts["item"]] == ["Create post", "Get post"]
    assert posts["item"][1]["request"]["url"] == "{{base_url}}/posts/1"
    assert "insomnia.test" in _script(posts["item"][1], "test")
    assert conv.environment["name"] == "Local"
    assert conv.environment["values"][0]["value"] == "http://localhost:3000"


def test_save_writes_collection_and_environment(tmp_path):
    conv = cc.convert(API / "demo-bruno")
    col, env = cc.save(conv, tmp_path)
    assert col.name == "demo-bruno-k0lmenia-jsonplaceholder.postman_collection.json"
    assert json.loads(col.read_text(encoding="utf-8"))["info"]["schema"] == cc.SCHEMA
    assert env.exists() and cc.count_requests(conv.collection["item"]) == 3


# --------------------------------------------------------------------------- GraphQL

def test_newman_to_results_names_graphql_operation():
    gql = lambda q: {"item": {"name": "API-GQL-001 — Country by code (High)"}, "request": {"body": {"mode": "graphql", "graphql": {"query": q}}}}  # noqa: E731
    assert nar.graphql_operation(gql("query Country($c: ID!) { country(code: $c) { name } }")) == "query Country"
    assert nar.graphql_operation(gql("mutation CreatePost { create { id } }")) == "mutation CreatePost"
    assert nar.graphql_operation(gql("{ country { name } }")) == "query (anonymous)"
    raw = {"request": {"body": {"mode": "raw", "raw": json.dumps({"query": "query List { a }"})}}}
    assert nar.graphql_operation(raw) == "query List"
    assert nar.graphql_operation({"request": {"body": {"mode": "raw", "raw": "{}"}}}) == ""
    data = nar.convert({"run": {"executions": [gql("query CountryByCode { a }")]}})
    assert data["cases"][0]["title"] == "Country by code [GraphQL query CountryByCode]" and data["cases"][0]["priority"] == "High"


SDL = '''
"""Root"""
schema { query: Lookup mutation: Mutate }
type Lookup {
  "a country"
  country(code: ID!): Country
  countries(filter: CountryFilter = {name: "a"}, limit: Int = 10): [Country!]!
}
type Mutate { createCountry(data: CountryInput!): Country! }
type Country @key(fields: "code") { code: ID! name: String! status: Status currency: Money }
input CountryInput { name: String! status: Status = ACTIVE }
input CountryFilter { name: String }
enum Status { ACTIVE INACTIVE @deprecated(reason: "no") }
scalar Money
'''


def test_sdl_schema_summary():
    text = rg.summarize(rg.from_sdl(SDL))
    assert "## Query (2)" in text and "## Mutation (1)" in text
    assert "- `country(code: ID!)` → `Country`" in text
    assert "- `countries(filter: CountryFilter = «object», limit: Int = 10)` → `[Country!]!`" in text
    assert "- `createCountry(data: CountryInput!)` → `Country!`" in text
    assert "- `Status`: ACTIVE, INACTIVE" in text
    assert "- `CountryInput` { name: String!, status: Status }" in text
    assert "Custom scalars: Money" in text


def test_introspection_summary():
    ref = lambda kind, name=None, of=None: {"kind": kind, "name": name, "ofType": of}  # noqa: E731
    data = {"data": {"__schema": {
        "queryType": {"name": "Query"}, "mutationType": None, "subscriptionType": None,
        "types": [
            {"kind": "OBJECT", "name": "Query", "fields": [
                {"name": "users", "isDeprecated": False, "args": [{"name": "role", "type": ref("ENUM", "Role"), "defaultValue": None}],
                 "type": ref("NON_NULL", None, ref("LIST", None, ref("NON_NULL", None, ref("OBJECT", "User"))))},
                {"name": "old", "isDeprecated": True, "args": [], "type": ref("LIST", None, None)}]},
            {"kind": "OBJECT", "name": "User", "fields": [{"name": "id", "args": [], "type": ref("NON_NULL", None, ref("SCALAR", "ID"))}]},
            {"kind": "ENUM", "name": "Role", "enumValues": [{"name": "ADMIN"}, {"name": "READER"}]},
            {"kind": "OBJECT", "name": "__Type", "fields": []},
        ]}}}
    text = rg.summarize(rg.from_introspection(data))
    assert "- `users(role: Role)` → `[User!]!`" in text
    assert "- `old` → `…` (deprecated)" in text
    assert "- `Role`: ADMIN, READER" in text and "- `User` { id: ID! }" in text
    assert "__Type" not in text
    assert "kind name ofType { kind name ofType { kind name } }" in rg.introspection_query(2)
