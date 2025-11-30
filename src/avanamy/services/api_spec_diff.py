# src/avanamy/services/api_spec_diff.py

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from typing import Any, List

from sqlalchemy.orm import Session

from avanamy.repositories.api_spec_repository import ApiSpecRepository
import logging
from opentelemetry import trace

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


class ChangeType(str, Enum):
    ADDED = "added"
    REMOVED = "removed"
    MODIFIED = "modified"


@dataclass
class SpecDiff:
    """
    Represents a single difference between two specs.

    path:
        Dot-separated path into the JSON structure. Example:
        "paths./users.get.summary"
    change_type:
        "added", "removed", or "modified"
    old:
        Previous value (None for ADDED)
    new:
        New value (None for REMOVED)
    """
    path: str
    change_type: ChangeType
    old: Any
    new: Any


def _join_path(parent: str, key: str) -> str:
    if not parent:
        return key
    return f"{parent}.{key}"


def _diff_values(old: Any, new: Any, path: str, diffs: List[SpecDiff]) -> None:
    """
    Recursive helper to diff two arbitrary JSON-like values.
    Supports nested dicts and lists, plus primitives.
    """

    # Types differ → treat as modified at this path
    if type(old) is not type(new):
        if old != new:
            diffs.append(
                SpecDiff(
                    path=path or "<root>",
                    change_type=ChangeType.MODIFIED,
                    old=old,
                    new=new,
                )
            )
        return

    # Dict vs dict: recurse
    if isinstance(old, dict):
        old_keys = set(old.keys())
        new_keys = set(new.keys())

        # Removed keys
        for key in sorted(old_keys - new_keys):
            diffs.append(
                SpecDiff(
                    path=_join_path(path, str(key)),
                    change_type=ChangeType.REMOVED,
                    old=old[key],
                    new=None,
                )
            )

        # Added keys
        for key in sorted(new_keys - old_keys):
            diffs.append(
                SpecDiff(
                    path=_join_path(path, str(key)),
                    change_type=ChangeType.ADDED,
                    old=None,
                    new=new[key],
                )
            )

        # Keys present in both → recurse
        for key in sorted(old_keys & new_keys):
            _diff_values(
                old[key],
                new[key],
                _join_path(path, str(key)),
                diffs,
            )
        return

    # List vs list: for now, treat as a single value-level diff
    if isinstance(old, list):
        if old != new:
            diffs.append(
                SpecDiff(
                    path=path or "<root>",
                    change_type=ChangeType.MODIFIED,
                    old=old,
                    new=new,
                )
            )
        return

    # Primitive equality check
    if old != new:
        diffs.append(
            SpecDiff(
                path=path or "<root>",
                change_type=ChangeType.MODIFIED,
                old=old,
                new=new,
            )
        )


def diff_dicts(old: Any, new: Any) -> List[SpecDiff]:
    """
    Public API: diff two JSON-like objects (dicts/lists/primitives).

    Returns a list of SpecDiff objects describing what changed.
    """
    with tracer.start_as_current_span("service.diff_dicts") as span:
        span.set_attribute("old.type", type(old).__name__)
        span.set_attribute("new.type", type(new).__name__)
        diffs: List[SpecDiff] = []
        _diff_values(old, new, path="", diffs=diffs)
        logger.debug("Computed diffs: count=%d", len(diffs))
        return diffs


def diff_specs_by_id(db: Session, base_id: int, compare_id: int) -> List[SpecDiff]:
    """
    Convenience helper: load two ApiSpec rows from the DB by id,
    parse their `parsed_schema` JSON strings, and return the diff.

    Raises ValueError if either spec is not found.
    """
    with tracer.start_as_current_span("service.diff_specs_by_id") as span:
        span.set_attribute("base.id", base_id)
        span.set_attribute("compare.id", compare_id)

        base = ApiSpecRepository.get_by_id(db, base_id)
        if not base:
            raise ValueError(f"Base spec {base_id} not found")

        other = ApiSpecRepository.get_by_id(db, compare_id)
        if not other:
            raise ValueError(f"Compare spec {compare_id} not found")

        base_schema = json.loads(base.parsed_schema) if base.parsed_schema else {}
        other_schema = json.loads(other.parsed_schema) if other.parsed_schema else {}

        diffs = diff_dicts(base_schema, other_schema)
        logger.info("Diffed specs %s vs %s -> %d diffs", base_id, compare_id, len(diffs))
        return diffs
