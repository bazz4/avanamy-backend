# tests/services/test_api_spec_diff.py

import json
from typing import List

from sqlalchemy.orm import Session

from avanamy.services.api_spec_diff import (
    diff_dicts,
    diff_specs_by_id,
    ChangeType,
    SpecDiff,
)
from avanamy.repositories.api_spec_repository import ApiSpecRepository


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
        "a": 2,                 # modified
        "c": 3,                 # added
        "nested": {"x": 10},    # y removed
    }

    diffs = diff_dicts(old, new)
    pts = _paths_and_types(diffs)

    assert ("a", ChangeType.MODIFIED) in pts
    assert ("c", ChangeType.ADDED) in pts
    assert ("nested.y", ChangeType.REMOVED) in pts


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


def test_diff_specs_by_id_round_trip(db: Session):
    """
    Integration-style test that goes through the repository + DB to ensure
    diff_specs_by_id can compare two stored specs.
    """
    # Create base spec
    base_schema = {"a": 1, "b": {"x": 10}}
    base = ApiSpecRepository.create(
        db,
        name="base",
        version="1.0",
        description=None,
        original_file_s3_path="s3://base",
        parsed_schema=json.dumps(base_schema),
    )

    # Create compare spec
    other_schema = {"a": 2, "b": {"x": 10}, "c": 3}
    other = ApiSpecRepository.create(
        db,
        name="other",
        version="1.1",
        description=None,
        original_file_s3_path="s3://other",
        parsed_schema=json.dumps(other_schema),
    )

    diffs = diff_specs_by_id(db, base.id, other.id)
    pts = _paths_and_types(diffs)

    assert ("a", ChangeType.MODIFIED) in pts
    assert ("c", ChangeType.ADDED) in pts
    # b.x is unchanged
    assert all(d.path != "b.x" for d in diffs)
