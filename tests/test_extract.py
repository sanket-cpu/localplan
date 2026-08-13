"""Tests for the schema transforms at the AI boundary. No model calls.

Both transforms exist because the schema Pydantic emits and the schema Ollama's
grammar compiler accepts are not the same document. Each one works around a
failure that took a live 400 or a validation error to discover, so each gets a
regression test.
"""

import json

from localplan.extract import _OPS_SCHEMA, _drop_patterns, _require_all


def test_require_all_marks_every_property_required():
    # Pydantic marks defaulted fields optional — including the `op`
    # discriminator. Constrained decoding then drops `op` from later array
    # elements and the union fails with union_tag_not_found.
    schema = {
        "type": "object",
        "properties": {"op": {"type": "string"}, "id": {"type": "integer"}},
        "required": ["id"],
    }
    assert set(_require_all(schema)["required"]) == {"op", "id"}


def test_require_all_recurses_into_nested_objects():
    schema = {
        "type": "object",
        "properties": {
            "ops": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"op": {"type": "string"}},
                },
            }
        },
    }
    result = _require_all(schema)
    assert result["properties"]["ops"]["items"]["required"] == ["op"]


def test_drop_patterns_removes_regex_constraints_at_every_depth():
    # Ollama's grammar compiler has no regex support; one `pattern` anywhere
    # fails the whole request with "failed to parse grammar" (HTTP 400).
    schema = {
        "properties": {
            "fixed_start": {"type": "string", "pattern": "^x$"},
            "nested": {"items": [{"pattern": "^y$"}]},
        }
    }
    assert "pattern" not in json.dumps(_drop_patterns(schema))


def test_the_shipped_schema_carries_no_patterns_and_requires_every_field():
    assert "pattern" not in json.dumps(_OPS_SCHEMA)
    assert _OPS_SCHEMA["required"] == ["ops"]
    for name, defn in _OPS_SCHEMA["$defs"].items():
        assert set(defn["required"]) == set(defn["properties"]), name
