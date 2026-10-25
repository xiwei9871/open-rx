import { execSync } from "node:child_process";

// Fresh rate-limit buckets for repeat E2E runs. Best-effort: CI brings a new
// redis; locally we flush the dev container's db (synthetic data only).
export default function globalSetup() {
  // Preview/public acceptance runs point at a deployed stack — never touch
  // its data plane from the dev-only reset hooks.
  if (process.env.PREVIEW_BASE_URL || process.env.E2E_BASE_URL) return;
  try {
    execSync("docker exec easyrs-dev-redis-1 redis-cli FLUSHDB",
             { stdio: "ignore", timeout: 5000 });
  } catch { /* redis not reachable via docker — limits may be stale */ }
  try {
    // The 2FA spec enrolls a factor on doctor@pa.dev — reset it so reruns get
    // a clean login->setup->enable path (CI brings a fresh DB anyway).
    execSync(`docker exec easyrs-dev-postgres-1 psql -U easyrs_admin -d easyrs -c "UPDATE user_account SET totp_enabled=false, totp_secret_enc=NULL WHERE email='doctor@pa.dev'"`,
             { stdio: "ignore", timeout: 5000 });
  } catch { /* postgres not reachable — 2FA spec may see a stale factor */ }
}
