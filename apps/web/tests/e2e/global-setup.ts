import { execSync } from "node:child_process";

// Fresh rate-limit buckets for repeat E2E runs. Best-effort: CI brings a new
// redis; locally we flush the dev container's db (synthetic data only).
export default function globalSetup() {
  try {
    execSync("docker exec easyrs-dev-redis-1 redis-cli FLUSHDB",
             { stdio: "ignore", timeout: 5000 });
  } catch { /* redis not reachable via docker — limits may be stale */ }
}
