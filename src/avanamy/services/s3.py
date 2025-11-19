import boto3
import os

AWS_REGION = os.getenv("AWS_REGION")
AWS_BUCKET = os.getenv("AWS_S3_BUCKET")

s3_client = boto3.client("s3", region_name=AWS_REGION)

def upload_file(file_path: str, object_name: str):
    """
    Upload a local file to S3.
    """
    if not AWS_BUCKET:
        raise RuntimeError("AWS_S3_BUCKET is not set in environment variables")

    s3_client.upload_file(file_path, AWS_BUCKET, object_name)
    return f"s3://{AWS_BUCKET}/{object_name}"
