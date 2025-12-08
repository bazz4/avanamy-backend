# src/avanamy/utils/filename_utils.py

import os
import re
import unicodedata
from uuid import UUID, uuid4
from pathlib import Path


def slugify_filename(name: str) -> str:
    """
    Convert any name into a safe S3 slug usable inside a key.
    """
    if not name:
        return "file"

    name = unicodedata.normalize("NFKD", name)
    name = name.encode("ascii", "ignore").decode("ascii")

    name = re.sub(r"[^a-zA-Z0-9._-]+", "-", name)
    name = name.strip("._-")
    name = name.lower()

    return name or "file"


def get_file_extension(filename: str) -> str:
    """
    Extract extension from a filename ("file.yaml" -> ".yaml").
    Returns empty string if not found.
    """
    _, ext = os.path.splitext(filename or "")
    return ext.lower()

