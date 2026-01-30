import hashlib
import os
from pathlib import Path
from typing import Optional, Tuple

import boto3

from app.config import settings


class StorageClient:
    def __init__(self):
        self.backend = settings.storage_backend.lower()
        self.local_path = Path(settings.local_storage_path)
        self.local_path.mkdir(parents=True, exist_ok=True)

        if self.backend == "s3":
            self.s3 = boto3.client(
                "s3",
                region_name=settings.s3_region,
                endpoint_url=settings.s3_endpoint_url,
                aws_access_key_id=settings.s3_access_key_id,
                aws_secret_access_key=settings.s3_secret_access_key,
            )
        else:
            self.s3 = None

    def save(self, image_id: int, filename: str, data: bytes) -> tuple[str, str]:
        digest = hashlib.sha256(data).hexdigest()
        safe_name = os.path.basename(filename)
        key = f"{image_id}/{digest}-{safe_name}"

        if self.backend == "s3":
            if not settings.s3_bucket:
                raise ValueError("S3_BUCKET is required when using s3 backend.")
            self.s3.put_object(Bucket=settings.s3_bucket, Key=key, Body=data)
            uri = f"s3://{settings.s3_bucket}/{key}"
            return uri, digest

        path = self.local_path / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        uri = str(path)
        return uri, digest

    def parse_s3_uri(self, uri: str) -> tuple[str, str]:
        if not uri.startswith("s3://"):
            raise ValueError("Not an S3 URI.")
        _, rest = uri.split("s3://", 1)
        bucket, key = rest.split("/", 1)
        return bucket, key

    def open_s3_stream(self, uri: str):
        if not self.s3:
            raise ValueError("S3 client not configured.")
        bucket, key = self.parse_s3_uri(uri)
        response = self.s3.get_object(Bucket=bucket, Key=key)
        filename = os.path.basename(key)
        return response["Body"], filename, response.get("ContentLength")

    def head_s3_object(self, uri: str) -> Tuple[str, Optional[int]]:
        if not self.s3:
            raise ValueError("S3 client not configured.")
        bucket, key = self.parse_s3_uri(uri)
        response = self.s3.head_object(Bucket=bucket, Key=key)
        filename = os.path.basename(key)
        return filename, response.get("ContentLength")


storage_client = StorageClient()
