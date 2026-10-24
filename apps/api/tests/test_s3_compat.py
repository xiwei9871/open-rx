"""B0.1-04 — S3 compatibility verification for the dev object store (RustFS).

list_buckets alone proves nothing; this suite exercises the API surface the
asset domain will actually need: object CRUD, sha256 integrity, presigned
upload/download, unauthorized denial, multipart with abort, large payloads,
and volume persistence across container restart.

Gated: only runs when S3_COMPAT=1 (CI job / local compose). It talks to the
endpoint from settings — not a mock.
"""
import hashlib
import os
import subprocess
import uuid

import boto3
import pytest
from botocore.client import Config as BotoConfig
from botocore.exceptions import ClientError

from app.config import get_settings

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(os.environ.get("S3_COMPAT") != "1",
                     reason="S3 compat suite — set S3_COMPAT=1 with store up"),
]

_s = get_settings()
BUCKET = f"s3compat-{uuid.uuid4().hex[:8]}"
BODY = b"easyrs-s3-compat-" + os.urandom(64)
SHA = hashlib.sha256(BODY).hexdigest()


def _client(access=None, secret=None):
    return boto3.client(
        "s3", endpoint_url=_s.s3_endpoint_url,
        aws_access_key_id=access or _s.s3_access_key,
        aws_secret_access_key=secret or _s.s3_secret_key,
        config=BotoConfig(signature_version="s3v4",
                          s3={"addressing_style": "path"},
                          connect_timeout=3, read_timeout=30,
                          retries={"max_attempts": 2}),
    )


@pytest.fixture(scope="module")
def s3():
    c = _client()
    c.create_bucket(Bucket=BUCKET)
    yield c
    objs = c.list_objects_v2(Bucket=BUCKET).get("Contents", [])
    for o in objs:
        c.delete_object(Bucket=BUCKET, Key=o["Key"])
    c.delete_bucket(Bucket=BUCKET)


async def test_put_get_head_delete_sha256(s3):
    k = "roundtrip/blob.bin"
    s3.put_object(Bucket=BUCKET, Key=k, Body=BODY)
    head = s3.head_object(Bucket=BUCKET, Key=k)
    assert head["ContentLength"] == len(BODY)
    got = s3.get_object(Bucket=BUCKET, Key=k)["Body"].read()
    assert hashlib.sha256(got).hexdigest() == SHA
    s3.delete_object(Bucket=BUCKET, Key=k)
    with pytest.raises(ClientError):
        s3.head_object(Bucket=BUCKET, Key=k)


async def test_presigned_upload_and_download(s3):
    k = "presigned/blob.bin"
    put_url = s3.generate_presigned_url(
        "put_object", Params={"Bucket": BUCKET, "Key": k}, ExpiresIn=60)
    import httpx
    async with httpx.AsyncClient() as h:
        r = await h.put(put_url, content=BODY)
        assert r.status_code == 200, r.text
        get_url = s3.generate_presigned_url(
            "get_object", Params={"Bucket": BUCKET, "Key": k}, ExpiresIn=60)
        r = await h.get(get_url)
        assert r.status_code == 200
        assert hashlib.sha256(r.content).hexdigest() == SHA


async def test_unauthorized_access_denied(s3):
    bad = _client(access="easyrs_dev", secret="definitely-wrong-secret")
    with pytest.raises(ClientError):
        bad.list_objects_v2(Bucket=BUCKET)
    with pytest.raises(ClientError):
        bad.get_object(Bucket=BUCKET, Key="presigned/blob.bin")


async def test_multipart_upload_abort_and_complete(s3):
    k = "mp/big.bin"
    big = os.urandom(6 * 1024 * 1024)  # > 5MiB minimum part
    mpu = s3.create_multipart_upload(Bucket=BUCKET, Key=k)
    part = s3.upload_part(Bucket=BUCKET, Key=k, UploadId=mpu["UploadId"],
                        PartNumber=1, Body=big)
    # abort path leaves nothing behind
    mpu2 = s3.create_multipart_upload(Bucket=BUCKET, Key="mp/aborted.bin")
    s3.upload_part(Bucket=BUCKET, Key="mp/aborted.bin", UploadId=mpu2["UploadId"],
                   PartNumber=1, Body=b"x" * 1024)
    s3.abort_multipart_upload(Bucket=BUCKET, Key="mp/aborted.bin",
                              UploadId=mpu2["UploadId"])
    left = [o["Key"] for o in s3.list_objects_v2(Bucket=BUCKET).get("Contents", [])]
    assert "mp/aborted.bin" not in left
    s3.complete_multipart_upload(
        Bucket=BUCKET, Key=k, UploadId=mpu["UploadId"],
        MultipartUpload={"Parts": [{"PartNumber": 1, "ETag": part["ETag"]}]})
    got = s3.get_object(Bucket=BUCKET, Key=k)["Body"].read()
    assert hashlib.sha256(got).hexdigest() == hashlib.sha256(big).hexdigest()


async def test_large_object_20mb(s3):
    k = "large/20mb.bin"
    data = os.urandom(20 * 1024 * 1024)
    s3.put_object(Bucket=BUCKET, Key=k, Body=data)
    got = s3.get_object(Bucket=BUCKET, Key=k)["Body"].read()
    assert hashlib.sha256(got).digest() == hashlib.sha256(data).digest()


@pytest.mark.skipif(os.environ.get("S3_RESTART") != "1",
                    reason="container restart — opt-in via S3_RESTART=1")
async def test_volume_survives_restart(s3):
    k = "persist/marker.bin"
    s3.put_object(Bucket=BUCKET, Key=k, Body=BODY)
    compose = _s  # restart via compose file path
    r = subprocess.run(
        ["docker", "compose", "-f", "../infra/docker-compose.yml",  # repo root rel
         "restart", "minio"],
        cwd=os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stderr
    import asyncio, time
    # wait for the store to serve again
    for _ in range(60):
        try:
            if s3.head_object(Bucket=BUCKET, Key=k):
                break
        except ClientError:
            pass
        time.sleep(1)
    else:
        pytest.fail("store did not recover after restart")
    got = s3.get_object(Bucket=BUCKET, Key=k)["Body"].read()
    assert hashlib.sha256(got).hexdigest() == SHA
