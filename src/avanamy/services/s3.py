# src/avanamy/services/s3.py
import os
import boto3
from botocore.exceptions import ClientError
from typing import Tuple
import logging
from opentelemetry import trace

AWS_REGION = os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION") or "us-east-1"
AWS_BUCKET = os.getenv("AWS_S3_BUCKET")  # must be set

_s3_client = boto3.client(
    "s3",
    region_name=AWS_REGION,
    # boto3 will pick credentials from env, ~/.aws, or IAM role
)

logger = logging.getLogger(__name__)
tracer = trace.get_tracer(__name__)

def upload_bytes(key: str, data: bytes, content_type: str = None) -> Tuple[str, str]:
    """
    Synchronously upload bytes to S3.
    Returns (s3_key, s3_url)
    """
    if not AWS_BUCKET:
    # Don't raise at import time in tests; let callers handle, but warn.
        raise RuntimeError("AWS_S3_BUCKET is not set in environment variables")
    
    try:
        kwargs = {"Bucket": AWS_BUCKET, "Key": key, "Body": data}
        if content_type:
            kwargs["ContentType"] = content_type

        with tracer.start_as_current_span("s3.upload") as span:
            span.set_attribute("s3.key", key)
            span.set_attribute("file.size", len(data) if data is not None else 0)
            logger.info("Uploading to S3: %s", key)
            _s3_client.put_object(**kwargs)

        s3_url = f"s3://{AWS_BUCKET}/{key}"
        return key, s3_url
    except ClientError:
        logger.error("S3 upload failed for key=%s", key)
        raise

def download_bytes(key: str) -> bytes:
    """
    Download raw bytes from S3 for the given key.
    """
    if not AWS_BUCKET:
        raise RuntimeError("AWS_S3_BUCKET is not set in environment variables")

    try:
        with tracer.start_as_current_span("s3.download") as span:
            span.set_attribute("s3.key", key)
            logger.info("Downloading from S3: %s", key)
            resp = _s3_client.get_object(Bucket=AWS_BUCKET, Key=key)
            body = resp.get("Body")
            if body is None:
                return b""
            return body.read()
    except ClientError:
        logger.error("S3 download failed for key=%s", key)
        raise