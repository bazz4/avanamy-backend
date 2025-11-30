# src/avanamy/services/api_spec_parser.py

from __future__ import annotations
import json
import yaml
import xml.etree.ElementTree as ET
from typing import Any, Dict
import logging
from opentelemetry import trace

from avanamy.utils.file_utils import detect_file_type
from avanamy.metrics import spec_parse_failures_total

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)


def parse_api_spec(filename: str, raw_bytes: bytes) -> Dict[str, Any]:
    """
    Parse raw API spec into a Python dict.
    Supports JSON, YAML, and XML.
    """

    ftype = detect_file_type(filename, raw_bytes)
    text = raw_bytes.decode("utf-8")

    with tracer.start_as_current_span("service.parse_api_spec") as span:
        span.set_attribute("filename", filename)
        span.set_attribute("file.type", ftype)
        try:
            # --- JSON ---
            if ftype == "json":
                obj = json.loads(text)
                if not isinstance(obj, dict):
                    raise ValueError("JSON root must be an object")
                return obj

            # --- YAML ---
            if ftype == "yaml":
                obj = yaml.safe_load(text)
                if not isinstance(obj, dict):
                    raise ValueError("YAML root must be a mapping")
                return obj

            # --- XML ---
            if ftype == "xml":
                root = ET.fromstring(text)
                return _xml_to_dict(root)

            raise ValueError(f"Unsupported or unknown spec format: {ftype}")

        except Exception:
            spec_parse_failures_total.inc()
            logger.exception("Failed to parse API spec: filename=%s ftype=%s", filename, ftype)
            raise


def _xml_to_dict(elem: ET.Element) -> Dict[str, Any]:
    """
    Convert XML Element into a nested dict.
    Repeated tags become lists.
    Leaf text is preserved.
    """
    node: Dict[str, Any] = {}

    # Attributes (rare for API specs)
    for k, v in elem.attrib.items():
        node[f"@{k}"] = v

    # Children
    children = list(elem)
    if children:
        for child in children:
            child_value = _xml_to_dict(child)
            if child.tag not in node:
                node[child.tag] = []
            node[child.tag].append(child_value)
        return node

    # Leaf
    text = elem.text.strip() if elem.text else ""
    return text
