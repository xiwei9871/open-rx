from contextlib import asynccontextmanager

import boto3
from botocore.client import Config as BotoConfig
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.modules.auth.router import router as auth_router
from app.modules.iam.router import router as iam_router

_s = get_settings()


def _ensure_bucket() -> None:
    try:
        s3 = boto3.client(
            "s3", endpoint_url=_s.s3_endpoint_url,
            aws_access_key_id=_s.s3_access_key,
            aws_secret_access_key=_s.s3_secret_key,
            config=BotoConfig(
                signature_version="s3v4",
                connect_timeout=3, read_timeout=5,
                retries={"max_attempts": 1},
            ),
        )
        buckets = {b["Name"] for b in s3.list_buckets().get("Buckets", [])}
        if _s.s3_bucket not in buckets:
            s3.create_bucket(Bucket=_s.s3_bucket)
    except Exception as e:  # storage optional at B0 — log, don't crash
        import logging
        logging.getLogger("easyrs").warning("S3 bucket check failed: %s", e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    if _s.env != "test":
        import asyncio
        await asyncio.wait_for(asyncio.to_thread(_ensure_bucket), timeout=8)
    yield


app = FastAPI(
    title="EasyRS API",
    version="0.1.0-b0",
    lifespan=lifespan,
    root_path="",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=_s.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(auth_router, prefix="/v1")
app.include_router(iam_router, prefix="/v1")


@app.get("/healthz", operation_id="healthz")
async def healthz():
    return {"status": "ok"}
