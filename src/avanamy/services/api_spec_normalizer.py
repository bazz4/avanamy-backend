# src/avanamy/services/api_spec_normalizer.py

from __future__ import annotations
from typing import Any, Dict, List
import logging
import threading
from opentelemetry import trace

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)

_local = threading.local()


def _normalize_api_spec(obj: Any) -> Any:
    """
    Internal recursive normalizer used by the public wrapper.
    """
    # --- Base types remain unchanged ---
    if obj is None or isinstance(obj, (int, float, bool)):
        return obj

    if isinstance(obj, str):
        return obj.strip()

    # --- Normalize lists ---
    if isinstance(obj, list):
        return [_normalize_api_spec(item) for item in obj]

    # --- Normalize dicts ---
    if isinstance(obj, dict):
        normalized: Dict[str, Any] = {}
        for key, value in obj.items():
            clean_key = str(key).strip().lower()
            normalized[clean_key] = _normalize_api_spec(value)
        return normalized

    # --- Convert any other type to string ---
    return str(obj)


def normalize_api_spec(obj: Any) -> Any:
    """
    Recursively normalize parsed API spec dictionaries so downstream
    tooling (diffing, embeddings, documentation generation, etc.)
    can depend on consistent structure.

    Rules:
      - Dict keys → lowercase
      - Strip whitespace
      - Convert scalars in XML → list when repeated
      - Ensure all content is JSON-serializable
    """

    # We avoid starting a tracer span on every recursive call by tracking
    # whether we're already inside a normalization operation on this thread.
    top_level = not getattr(_local, "in_normalize", False)
    if top_level:
        _local.in_normalize = True
    try:
        if top_level:
            with tracer.start_as_current_span("service.normalize_api_spec") as span:
                span.set_attribute("obj.type", type(obj).__name__)
                result = _normalize_api_spec(obj)
                logger.debug("Normalized object type=%s", type(obj).__name__)
                return result
        else:
            return _normalize_api_spec(obj)
    finally:
        if top_level:
            _local.in_normalize = False
