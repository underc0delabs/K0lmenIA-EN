"""summarize_openapi.py: base URL with basePath/servers, authentication → step, and endpoints, without network."""
import summarize_openapi as ro

SWAGGER2 = {
    "swagger": "2.0", "info": {"title": "Petstore", "version": "1"}, "host": "petstore.swagger.io", "basePath": "/v2",
    "schemes": ["https", "http"],
    "securityDefinitions": {"api_key": {"type": "apiKey", "name": "api_key", "in": "header"},
                            "basic": {"type": "basic"}},
    "paths": {
        "/pet/{petId}": {
            "parameters": [{"name": "petId", "in": "path", "required": True, "type": "integer", "format": "int64"}],
            "get": {"summary": "Finds", "security": [{"api_key": []}], "responses": {"200": {"description": "ok"}, "404": {"description": "not found"}}},
            "post": {"consumes": ["application/x-www-form-urlencoded"], "summary": "Updates with a form",
                     "parameters": [{"name": "name", "in": "formData", "type": "string"}], "responses": {"405": {"description": "Invalid input"}}},
        },
        "/pet": {"post": {"parameters": [{"in": "body", "name": "body", "required": True, "schema": {"$ref": "#/definitions/Pet"}}],
                          "responses": {"200": {"description": "ok"}}}},
        "/pet/{petId}/photo": {"post": {"consumes": ["multipart/form-data"],
                                        "parameters": [{"name": "file", "in": "formData", "type": "file"}], "responses": {}}},
    },
    "definitions": {"Pet": {"type": "object", "required": ["name"], "properties": {
        "id": {"type": "integer", "format": "int64"}, "name": {"type": "string", "example": "doggie"},
        "status": {"type": "string", "enum": ["available", "sold"]}, "owner": {"$ref": "#/definitions/Pet"}}}},
}

OPENAPI3 = {
    "openapi": "3.0.4", "info": {"title": "Store", "version": "2"},
    "servers": [{"url": "/api/{version}", "variables": {"version": {"default": "v3"}}}],
    "security": [{"bearer": []}],
    "components": {"securitySchemes": {"bearer": {"type": "http", "scheme": "bearer"},
                                       "key": {"type": "apiKey", "in": "query", "name": "key"}}},
    "paths": {"/user": {"post": {"requestBody": {"required": True, "content": {"application/json": {"schema": {
        "type": "object", "properties": {"email": {"type": "string", "format": "email"}, "age": {"type": "integer", "minimum": 18}}}}}},
        "responses": {"201": {"description": "created"}}}},
        "/public": {"get": {"security": [], "parameters": [{"name": "q", "in": "query", "schema": {"type": "string"}}], "responses": {}}}},
}


def test_swagger2_base_url_with_basepath_and_authentication():
    r = ro.summarize(SWAGGER2, "spec.json")
    assert r["api_baseurl"] == "https://petstore.swagger.io/v2"
    assert r["security"]["api_key"]["step"] == 'Given the request uses the API key in the header "api_key"'
    assert r["security"]["basic"]["step"] == "Given the request uses basic authentication"


def test_swagger2_endpoints_parameters_body_and_forms():
    eps = {(e["method"], e["path"]): e for e in ro.summarize(SWAGGER2, "spec.json")["endpoints"]}
    get = eps[("GET", "/pet/{petId}")]
    assert get["parameters"] == [{"in": "path", "name": "petId", "type": "integer (int64)", "required": True}]
    assert get["security"] == ["api_key"]
    assert get["responses"] == {"200": "ok", "404": "not found"}
    assert eps[("POST", "/pet/{petId}")]["body"]["type"] == "form"
    assert eps[("POST", "/pet/{petId}/photo")]["body"]["type"] == "multipart"
    ex = eps[("POST", "/pet")]["body"]["example"]
    assert ex["name"] == "doggie" and ex["status"] == "available" and ex["id"] == 1
    assert ex["owner"] is None  # circular reference: it is not expanded forever


def test_openapi3_relative_server_variables_and_global_security():
    r = ro.summarize(OPENAPI3, "https://store.test/docs/openapi.json")
    assert r["api_baseurl"] == "https://store.test/api/v3"
    eps = {(e["method"], e["path"]): e for e in r["endpoints"]}
    assert eps[("POST", "/user")]["security"] == ["bearer"]
    assert eps[("GET", "/public")]["security"] == []
    assert eps[("POST", "/user")]["body"]["example"] == {"email": "qa+{random}@test.com", "age": 18}
    assert r["security"]["key"]["step"] == 'Given the request uses the API key in the parameter "key"'
    md = ro.to_markdown(r, "spec")
    assert "API_BASEURL=https://store.test/api/v3" in md
    assert "### POST /user" in md


def test_relative_server_without_url_asks_to_complete():
    r = ro.summarize(OPENAPI3, "openapi.json")
    assert r["api_baseurl"] is None
    assert "relative" in r["base_note"]
