# src/avanamy/utils/file_utils.py
import json
import yaml
import xml.etree.ElementTree as ET
from typing import Literal

FileType = Literal["json", "yaml", "xml", "unknown"]

def detect_file_type(filename: str, raw_bytes: bytes) -> FileType:
    """
    Best-effort file type detection:
    1. Use extension if available
    2. Otherwise try parsing JSON, YAML, XML
    """
    name = (filename or "").lower()

    if name.endswith(".json"):
        return "json"
    if name.endswith((".yaml", ".yml")):
        return "yaml"
    if name.endswith(".xml"):
        return "xml"

    # Fallback: try to parse the bytes
    text = None
    try:
        text = raw_bytes.decode("utf-8")
    except Exception:
        pass

    if text is not None:
        # JSON?
        try:
            json.loads(text)
            return "json"
        except Exception:
            pass

        # YAML?
        try:
            yaml.safe_load(text)
            return "yaml"
        except Exception:
            pass

        # XML?
        try:
            ET.fromstring(text)
            return "xml"
        except Exception:
            pass

    return "unknown"
