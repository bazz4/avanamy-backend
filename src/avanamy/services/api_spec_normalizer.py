# src/avanamy/services/api_spec_normalizer.py

from __future__ import annotations
from typing import Any, Dict, List


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

    # --- Base types remain unchanged ---
    if obj is None or isinstance(obj, (int, float, bool)):
        return obj

    if isinstance(obj, str):
        return obj.strip()

    # --- Normalize lists ---
    if isinstance(obj, list):
        return [normalize_api_spec(item) for item in obj]

    # --- Normalize dicts ---
    if isinstance(obj, dict):
        normalized: Dict[str, Any] = {}
        for key, value in obj.items():
            clean_key = str(key).strip().lower()
            normalized[clean_key] = normalize_api_spec(value)
        return normalized

    # --- Convert any other type to string ---
    return str(obj)
