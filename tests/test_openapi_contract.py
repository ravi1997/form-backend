import pytest

from scripts.export_openapi import _missing_definition_refs, _validate_spec


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
