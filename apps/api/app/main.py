from contextlib import asynccontextmanager

import boto3
from botocore.client import Config as BotoConfig
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.modules.auth.router import router as auth_router
from app.modules.iam.router import router as iam_router
from app.modules.clinical.router import router as clinical_router
from app.modules.assets.router import router as assets_router

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
_SAFE = {"GET", "HEAD", "OPTIONS"}


@app.middleware("http")
async def csrf_origin_guard(request, call_next):
    """CSRF defense for cookie-authenticated unsafe methods.

    Browsers cannot attach a custom header cross-origin without a CORS
    preflight, so requiring X-Requested-With makes cross-site form/fetch
    forgery impossible. Origin (when sent) must additionally be allowlisted.
    Non-browser clients (curl/tests) may omit Origin but must send the header.
    """
    if request.method not in _SAFE and request.url.path.startswith("/v1/"):
        from fastapi.responses import JSONResponse
        if request.headers.get("x-requested-with") != "XMLHttpRequest":
            return JSONResponse(status_code=403, content={
                "detail": {"code": "forbidden", "message": "CSRF header missing"}})
        origin = request.headers.get("origin")
        if origin and origin not in _s.cors_origin_list:
            return JSONResponse(status_code=403, content={
                "detail": {"code": "forbidden", "message": "Origin not allowed"}})
    return await call_next(request)


app.include_router(auth_router, prefix="/v1")
app.include_router(iam_router, prefix="/v1")
app.include_router(clinical_router, prefix="/v1")
app.include_router(assets_router, prefix="/v1")


@app.get("/healthz", operation_id="healthz")
async def healthz():
    return {"status": "ok"}
