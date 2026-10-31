# Stock/Host Non-Regression — Private Preview Deploy

Comparison of host services before vs after deploying `easyrs-preview`
(2026-10-25).

## Before (Phase 0 audit)

- 61-ish running containers incl. `water_saas-*`, `stock_research_dashboard-*`,
  `docker-nginx-1` (owns host :80/:443, Dify config), `lanproxy-client`,
  `monitor-agent`, mq_* platform, mysql, mongo, redis family, etc.
- Ports of interest: `:5185` water web, `127.0.0.1:5174` stock dashboard,
  `0.0.0.0:80/443` docker-nginx, lanproxy client → `www.manqiaotechnology.com`.
- Disk: 780G/1.1T used (76%); load ~1.2–2.2; 251G RAM.

## Changes made by this deploy

- Added project `easyrs-preview`: 6 containers (`postgres`, `redis`,
  `rustfs`, `migrate`, `api`, `web`), 3 named volumes, 1 bridge network.
- New host bindings: `192.168.3.185:5190` (web), `192.168.3.185:5191` (S3).
  Nothing bound to 80/443 or any pre-existing port.
- No edits to: `/etc/nginx/**`, `docker-nginx-1` config, lanproxy-client env,
  any other container, `daemon.json`, firewall rules, stock DB, host Redis
  config. No `docker system prune`, no volume deletion.
- New images: `easyrs-api:v0.1.0`, `easyrs-web:v0.1.0` + retagged base
  images pulled via daocloud mirror (docker.io unreachable from host).

## After (post-deploy verification)

- `water_saas` web: HTTP 200 on `:5185` ✔
- `stock_research_dashboard`: HTTP 200 on `127.0.0.1:5174` ✔
- Public `https://stock.manqiaotechnology.com/`: 200 ✔
- `docker-nginx-1` still sole owner of :80/:443 ✔
- Disk: 781G/1.1T (76%) — preview adds ~1.5G images + small volumes.
- Load unchanged (1.4–1.8 range, inside normal variation).
- All 61 pre-existing containers still running; preview adds 5 long-running
  + 1 one-shot.

Conclusion: **no non-regression detected.** The preview is additive and
fully namespaced.
