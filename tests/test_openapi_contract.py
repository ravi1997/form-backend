from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml


DOCS_DIR = Path("docs")
OPENAPI_YAML = DOCS_DIR / "openapi.yaml"
OPENAPI_JSON = DOCS_DIR / "openapi_spec.json"


def _missing_definition_refs(spec: dict) -> set:
    refs = set()

    def search(obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if (
                    k == "$ref"
                    and isinstance(v, str)
                    and v.startswith("#/definitions/")
                ):
                    refs.add(v.split("/")[-1])
                elif not (
                    k == "$ref"
                    and isinstance(v, str)
                    and v.startswith("#/$defs/")
                ):
                    search(v)
        elif isinstance(obj, list):
            for item in obj:
                search(item)

    search(spec)
    definitions = spec.get("definitions", {})
    return {ref for ref in refs if ref not in definitions}


ALLOWED_UNRESOLVED_REFS = {
    "FormCreateSchema",
    "FormUpdateSchema",
    "AnalysisBoardCreateSchema",
    "AnalysisBoardUpdateSchema",
    "DashboardCreateSchema",
    "DashboardUpdateSchema",
    "SystemSettingsUpdateSchema",
    "FormResponseCreateSchema",
}


def _validate_spec(spec: dict):
    if not spec.get("paths"):
        raise ValueError("no paths")
    missing = _missing_definition_refs(spec) - ALLOWED_UNRESOLVED_REFS
    if missing:
        raise ValueError(f"Missing definitions: {missing}")
    security_defs = spec.get("securityDefinitions", {})
    if "Bearer" not in security_defs:
        raise ValueError("missing Bearer security definition")


def _load_json_spec() -> dict:
    return json.loads(OPENAPI_JSON.read_text())


def _load_yaml_spec() -> dict:
    return yaml.safe_load(OPENAPI_YAML.read_text())


def test_validate_spec_rejects_missing_paths():
    with pytest.raises(ValueError, match="no paths"):
        _validate_spec({"swagger": "2.0", "definitions": {}, "paths": {}})


def test_validate_spec_rejects_missing_definition_refs():
    spec = {
        "swagger": "2.0",
        "paths": {
            "/x": {
                "get": {
                    "responses": {"200": {"schema": {"$ref": "#/definitions/Missing"}}}
                }
            }
        },
        "definitions": {},
        "securityDefinitions": {"Bearer": {"type": "apiKey"}},
    }

    assert _missing_definition_refs(spec) == {"Missing"}
    with pytest.raises(ValueError, match="Missing definitions"):
        _validate_spec(spec)


def test_validate_spec_accepts_defined_refs():
    spec = {
        "swagger": "2.0",
        "paths": {
            "/x": {
                "get": {
                    "responses": {"200": {"schema": {"$ref": "#/definitions/Thing"}}}
                }
            }
        },
        "definitions": {"Thing": {"type": "object"}},
        "securityDefinitions": {"Bearer": {"type": "apiKey"}},
    }

    _validate_spec(spec)


def test_exported_openapi_documents_are_in_sync():
    json_spec = _load_json_spec()
    yaml_spec = _load_yaml_spec()

    assert json_spec == yaml_spec
    _validate_spec(json_spec)


def test_openapi_spec_documents_key_auth_transport_contracts():
    spec = _load_json_spec()
    auth_path = spec["paths"]["/mahasangraha/api/v1/auth/login"]["post"]
    refresh_path = spec["paths"]["/mahasangraha/api/v1/auth/refresh"]["post"]
    logout_path = spec["paths"]["/mahasangraha/api/v1/auth/logout"]["post"]

    assert "Bearer" in spec["securityDefinitions"]
    assert auth_path["responses"]["200"]["schema"]["properties"]["data"]["properties"][
        "access_token"
    ]["type"] == "string"
    assert refresh_path["security"] == [{"Bearer": []}]
    assert logout_path["security"] == [{"Bearer": []}]
