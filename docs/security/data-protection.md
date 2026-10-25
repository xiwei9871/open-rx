# Data protection posture (MVP / Alpha)

## At rest

- **TOTP secrets**: Fernet-encrypted (`totp_secret_enc`); key from
  `TOTP_ENCRYPTION_KEY` in prod (fail-closed if absent), HKDF-derived from
  `SESSION_SECRET` in dev/test only.
- **Passwords**: argon2id (`argon2-cffi` recommended profile).
- **Sessions/challenges**: stored as hashes (`token_hash`), never raw.
- **PostgreSQL**: volume encryption is an infrastructure concern — the
  deploy runbook requires encrypted volumes/managed-disk encryption in any
  non-dev environment.
- **Object storage**: S3-compatible (RustFS/MinIO/S3). Production S3 should
  enable server-side encryption (SSE-S3/SSE-KMS); dev MinIO is plaintext.

## In transit

- Browser → web → api: TLS at the edge (reverse proxy) in any real
  deployment; the compose dev stack is plaintext localhost by design.
- Presigned S3 URLs: production `S3_PUBLIC_ENDPOINT_URL` must be HTTPS;
  `scripts/preflight.py` fails on `http://` endpoints in `ENV=prod`.
- Postgres/Redis links are plaintext inside the compose network; outside a
  single host use TLS (`sslmode=require`) per the deploy runbook.

## Upload controls (ASSET-010 / SAFE-005)

- 200 MB ceiling (`UPLOAD_MAX_BYTES`), declared sha256/bytes verified
  byte-exact at completion, STL structural validation, pluggable scan hook
  (`ASSET_AV_ENGINE=none|eicar_stub|<adapter>` — fail-closed on unknown
  engine), expired staging objects are reaped.
- **Honest AV status**: Alpha ships `none` and a sentinel `eicar_stub` only.
  That is a hook point plus a negative-path test — it is NOT real malware
  scanning and NOT a production security certification. A real deployment
  must wire an actual engine behind the adapter interface.

## Retention & deletion

- Upload staging objects expire and are deleted best-effort.
- `file_reference` revocation is soft (`revoked_at`); the asset object stays
  content-addressed per org.
- `python -m app.seed --purge` removes the entire synthetic dataset
  (dev/test only — refuses other ENV values).
