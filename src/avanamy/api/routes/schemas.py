# src/avanamy/api/routes/schemas.py
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from datetime import datetime, timezone
import traceback
import asyncio
import json
import yaml
import xml.etree.ElementTree as ET
from typing import Tuple

from avanamy.services.s3 import upload_bytes
from avanamy.utils.file_utils import detect_file_type

router = APIRouter()

def _normalize_to_json_bytes(file_type: str, raw_bytes: bytes) -> Tuple[bytes, str]:
    """
    Normalize supported types to JSON bytes for storage.
    Returns (bytes, content_type)
    """
    if file_type == "json":
        # Validate JSON
        parsed = json.loads(raw_bytes.decode("utf-8"))
        out = json.dumps(parsed, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        return out, "application/json"

    if file_type == "yaml":
        parsed = yaml.safe_load(raw_bytes.decode("utf-8"))
        out = json.dumps(parsed, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        return out, "application/json"

    if file_type == "xml":
        # Keep XML as text inside a JSON wrapper (simple approach)
        root = ET.fromstring(raw_bytes.decode("utf-8"))
        xml_string = ET.tostring(root, encoding="unicode")
        wrapper = {"_xml": xml_string}
        out = json.dumps(wrapper, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        return out, "application/json"

    raise ValueError("Unsupported file type for normalization")

@router.post("/upload")
async def upload_schema(
    file: UploadFile = File(...),
    namespace: str = Form(...),
    name: str = Form(...)
):
    """
    Uploads a schema file (JSON/YAML/XML), normalizes to JSON bytes, stores in S3 under:
      schemas/{namespace}/{name}/{timestamp}.json
    Returns metadata including s3_key and s3:// url.
    """
    # read bytes from the UploadFile (async)
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Empty file uploaded")

    # Detect type
    file_type = detect_file_type(file.filename, raw)
    if file_type == "unknown":
        raise HTTPException(status_code=400, detail="Unsupported or unrecognized file type")

    # Normalize to JSON bytes
    try:
        normalized_bytes, content_type = _normalize_to_json_bytes(file_type, raw)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse/normalize file: {e}")

    # Timestamp (timezone-aware)
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")

    # S3 key
    safe_namespace = namespace.strip().replace(" ", "_")
    safe_name = name.strip().replace(" ", "_")
    s3_key = f"schemas/{safe_namespace}/{safe_name}/{timestamp}.json"

    # Upload in a thread to avoid blocking the event loop
    try:
        key, s3_url = await asyncio.to_thread(upload_bytes, s3_key, normalized_bytes, content_type)
    except Exception as e:

        print("\n!!!! ERROR DURING UPLOAD !!!!")
        print("Error:", e)
        traceback.print_exc()  # <-- shows full stack trace
        print("!!!! END ERROR !!!!\n")
        raise HTTPException(status_code=500, detail=f"S3 upload failed: {e}")

    return {
        "namespace": namespace,
        "name": name,
        "version": timestamp,
        "s3_key": key,
        "url": s3_url,
        "file_size": len(normalized_bytes),
        "original_filename": file.filename,
        "file_type": file_type,
    }
