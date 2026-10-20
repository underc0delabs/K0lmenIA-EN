"""Reading the .env (scripts/_env.py): same rules as dotenv and scripts/mcp/read-env.js."""
from _env import read_env


def test_basic_rules(tmp_path):
    file = tmp_path / ".env"
    file.write_text(
        "﻿# comment\n"
        "SIMPLE=value\n"
        "export WITH_EXPORT=yes\n"
        "SPACES =  with spaces   \n"
        "COMMENT=abc # this is dropped\n"
        'QUOTES="with # hash"\n'
        "SINGLE='literal'\n"
        "EMPTY=\n"
        "# COMMENTED=no\n",
        encoding="utf-8",
    )
    v = read_env(file)
    assert v["SIMPLE"] == "value"
    assert v["WITH_EXPORT"] == "yes"
    assert v["SPACES"] == "with spaces"
    assert v["COMMENT"] == "abc"
    assert v["QUOTES"] == "with # hash"
    assert v["SINGLE"] == "literal"
    assert v["EMPTY"] == ""
    assert "COMMENTED" not in v


def test_nonexistent_file(tmp_path):
    assert read_env(tmp_path / "does-not-exist.env") == {}


def test_doctor_alternative_variables():
    import doctor
    # Xray Server/DC: token, or user and password
    assert doctor.missing(["XRAY_DC_TOKEN|XRAY_DC_USER+XRAY_DC_PASSWORD"], {"XRAY_DC_USER": "u", "XRAY_DC_PASSWORD": "p"}) == []
    assert doctor.missing(["XRAY_DC_TOKEN|XRAY_DC_USER+XRAY_DC_PASSWORD"], {"XRAY_DC_USER": "u"}) != []
    assert doctor.missing(["A", "B"], {"A": "1"}) == ["B"]
