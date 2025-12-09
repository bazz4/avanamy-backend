# tests/services/test_api_spec_diff.py

import json
from types import SimpleNamespace
from typing import List

import pytest

from avanamy.services.api_spec_diff import (
    ChangeType,
    SpecDiff,
    diff_dicts,
    diff_specs_by_id,
)


def _paths_and_types(diffs: List[SpecDiff]):
    """Utility for assertions: return a set of (path, change_type)."""
    return {(d.path, d.change_type) for d in diffs}


def test_diff_dicts_no_changes():
    old = {"a": 1, "b": {"c": 2}}
    new = {"a": 1, "b": {"c": 2}}

    diffs = diff_dicts(old, new)
    assert diffs == []


def test_diff_dicts_added_and_removed_and_modified():
    old = {
        "a": 1,
        "b": 2,
        "nested": {"x": 10, "y": 20},
    }
    new = {
        "a": 2,  # modified
        "c": 3,  # added
        "nested": {"x": 10},  # y removed
    }

    diffs = diff_dicts(old, new)
    pts = _paths_and_types(diffs)

    assert ("a", ChangeType.MODIFIED) in pts
    assert ("c", ChangeType.ADDED) in pts
    assert ("nested.y", ChangeType.REMOVED) in pts


def test_diff_dicts_type_change_counts_as_modified():
    diffs = diff_dicts({"value": {"nested": 1}}, {"value": "1"})
    assert len(diffs) == 1
    assert diffs[0].path == "value"
    assert diffs[0].change_type == ChangeType.MODIFIED


def test_diff_dicts_list_modified():
    old = {"items": [1, 2, 3]}
    new = {"items": [1, 2, 4]}

    diffs = diff_dicts(old, new)
    assert len(diffs) == 1
    d = diffs[0]
    assert d.path == "items"
    assert d.change_type == ChangeType.MODIFIED
    assert d.old == [1, 2, 3]
    assert d.new == [1, 2, 4]


def test_diff_specs_by_id_uses_repository(monkeypatch, db):
    base = SimpleNamespace(parsed_schema=json.dumps({"a": 1}))
    other = SimpleNamespace(parsed_schema=json.dumps({"a": 2, "b": 3}))

    def fake_get_by_id(_db, spec_id):
        if spec_id == 1:
            return base
        if spec_id == 2:
            return other
        return None

    monkeypatch.setattr(
        "avanamy.services.api_spec_diff.ApiSpecRepository.get_by_id",
        fake_get_by_id,
    )

    diffs = diff_specs_by_id(db, 1, 2)
    pts = _paths_and_types(diffs)
    assert ("a", ChangeType.MODIFIED) in pts
    assert ("b", ChangeType.ADDED) in pts


def test_diff_specs_by_id_missing_spec_raises(monkeypatch, db):
    monkeypatch.setattr(
        "avanamy.services.api_spec_diff.ApiSpecRepository.get_by_id",
        lambda *_: None,
    )

    with pytest.raises(ValueError):
        diff_specs_by_id(db, 10, 11)
