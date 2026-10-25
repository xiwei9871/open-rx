"""S3 client helpers (S1a-03).

Two endpoints on purpose:
- internal client: server-side ops (head/get/copy/delete of staging + assets)
- presign client: URLs minted against the PUBLIC endpoint so a browser can
  reach them (docker-compose publishes :9000 on localhost; inside the cluster
  the service is `minio:9000` — the host differs, the signatures must be
  computed for the host the client will actually dial).
"""
import boto3
from botocore.config import Config as BotoConfig

from app.config import get_settings

_s = get_settings()


def _client(endpoint: str):
    return boto3.client(
        "s3", endpoint_url=endpoint,
        aws_access_key_id=_s.s3_access_key,
        aws_secret_access_key=_s.s3_secret_key,
        config=BotoConfig(signature_version="s3v4"),
        region_name="us-east-1",
    )


def s3():
    """Server-side client — internal endpoint."""
    return _client(_s.s3_endpoint_url)


def s3_presign():
    """Client used ONLY to generate presigned URLs for browsers."""
    return _client(_s.s3_public_endpoint_url or _s.s3_endpoint_url)
