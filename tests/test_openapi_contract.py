import re
import pytest

def _missing_definition_refs(spec: dict) -> set:
    # Recursively find all "$ref" values in the spec that start with "#/definitions/"
    refs = set()
    def search(obj):
        if isinstance(obj, dict):
            for k, v in obj.items():
                if k == "$ref" and isinstance(v, str) and v.startswith("#/definitions/"):
                    refs.add(v.split("/")[-1])
                else:
                    search(v)
        elif isinstance(obj, list):
            for item in obj:
                search(item)
    search(spec)
    
    # Return those that are not present in definitions
    definitions = spec.get("definitions", {})
    return {r for r in refs if r not in definitions}

def _validate_spec(spec: dict):
    if not spec.get("paths"):
        raise ValueError("no paths")
    missing = _missing_definition_refs(spec)
    if missing:
        raise ValueError(f"Missing definitions: {missing}")



def test_validate_spec_rejects_missing_paths():
    with pytest.raises(ValueError, match="no paths"):
        _validate_spec({"swagger": "2.0", "definitions": {}, "paths": {}})


def test_validate_spec_rejects_missing_definition_refs():
    spec = {
        "swagger": "2.0",
        "paths": {
            "/x": {
                "get": {
                    "responses": {
                        "200": {"schema": {"$ref": "#/definitions/Missing"}}
                    }
                }
            }
        },
        "definitions": {},
    }

    assert _missing_definition_refs(spec) == {"Missing"}
    with pytest.raises(ValueError, match="Missing"):
        _validate_spec(spec)


def test_validate_spec_accepts_defined_refs():
    spec = {
        "swagger": "2.0",
        "paths": {
            "/x": {
                "get": {
                    "responses": {
                        "200": {"schema": {"$ref": "#/definitions/Thing"}}
                    }
                }
            }
        },
        "definitions": {"Thing": {"type": "object"}},
    }

    _validate_spec(spec)
