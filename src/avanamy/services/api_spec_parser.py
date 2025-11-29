# src/avanamy/services/api_spec_parser.py

import json
import yaml
import xml.etree.ElementTree as ET

from avanamy.utils.file_utils import detect_file_type

"""This file will:

take (filename, raw_bytes)

detect file type (using your existing file_utils)

parse into Python dict (normalized)

return a structured payload ready for DB"""

def parse_api_spec(filename: str, raw_bytes: bytes) -> dict:
    """
    Parses raw API spec bytes (JSON, YAML, XML) and returns a normalized dict.
    This dict will be stored in ApiSpec.parsed_schema.
    """

    ftype = detect_file_type(filename, raw_bytes)

    text = raw_bytes.decode("utf-8")

    if ftype == "json":
        return json.loads(text)

    if ftype == "yaml":
        return yaml.safe_load(text)

    if ftype == "xml":
        # Convert XML → dict
        root = ET.fromstring(text)
        return _xml_to_dict(root)

    raise ValueError(f"Unsupported or unknown spec format: {ftype}")


def _xml_to_dict(elem: ET.Element) -> dict:
    """
    Minimal, generic XML → dict converter.
    Good enough for early versions of API spec ingestion.
    """
    node = {}

    # Attributes become keys prefixed with '@'
    for k, v in elem.attrib.items():
        node[f"@{k}"] = v

    # Child elements
    children = list(elem)
    if children:
        for child in children:
            child_dict = _xml_to_dict(child)
            node.setdefault(child.tag, [])

            # If we see same tag multiple times, store as list
            node[child.tag].append(child_dict)
    else:
        # Leaf node
        if elem.text and elem.text.strip():
            return elem.text.strip()

    return node
