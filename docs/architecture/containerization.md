# Container architecture

This document covers container-specific decisions. See the
[system overview](system-overview.md) for the complete application architecture.

## Topology

```text
Browser :5173
    |
    v
web: unprivileged Nginx :8080
    |-- /          -> React production build
    |-- /health    -> web health response
    `-- /api/*     -> api:8000/*
                          |
                          v
                    FastAPI :8000
                          |
                          v
               financial_ai_runtime volume
```

Compose publishes Nginx on host port `5173` and FastAPI on `8000`. Browser API
requests use same-origin `/api`; Nginx resolves the internal Compose hostname
`api`. The direct API port keeps OpenAPI and diagnostics accessible locally.

## Images

`docker/api/Dockerfile` uses Python 3.12 and the locked `uv` dependencies. It
copies dependencies before application source for efficient caching, installs
the project non-editably, and runs as an unprivileged user. Startup applies
Alembic migrations, creates the category artifact only when missing, and then
starts Uvicorn. Conditional initialization protects a promoted model in the
persistent volume.

`docker/web/Dockerfile` is a multi-stage build. Node 22 installs the exact npm
lockfile and builds the Vite bundle; the final unprivileged Nginx image contains
only static output and server configuration. Nginx provides SPA fallback, the
API reverse proxy, health endpoint, and baseline response headers.

## Persistence and lifecycle

The named `financial_ai_runtime` volume mounts at `/app/data/runtime` and holds:

- SQLite data;
- generated training snapshots and the active model;
- feedback exports, candidates, reports, archives, and promotion receipts.

The fresh container does not need the market XGBoost artifact to serve the demo.
The forecast panel uses its labeled close-price EWMA reference on synthetic
prices. A separately built, checksum-verified XGBoost artifact can be placed in
the runtime volume for external instruments; the historical training data is
not redistributed in the Docker image.

```powershell
docker compose up --build --wait
docker compose logs --follow
docker compose down
```

`docker compose down` retains the volume. `docker compose down --volumes`
permanently deletes this container-managed runtime state. The `.dockerignore`
keeps local environments, dependency trees, builds, runtime data, Git metadata,
editor configuration, databases, and `.env` files out of build contexts.

## Health and CI

The API health check allows time for initial migrations and model generation.
The web service waits for a healthy API and exposes its own health endpoint.
Both containers use minimal init handling and unprivileged runtime users.

The independent `Containers` CI job:

1. validates the Compose configuration and builds both images;
2. starts the stack and waits for health checks;
3. probes FastAPI, Nginx, the proxy, and a demo forecast through the proxy;
4. prints logs on failure and always removes temporary CI resources.

This verifies the complete browser-facing route, not merely two isolated
processes.

## Boundaries

The stack is a reproducible local/deployment baseline. SQLite and a shared
runtime volume are appropriate for the single-instance demo. A production
system still needs an external database, separate durable model/feedback
storage, authentication, TLS, secrets management, image publication,
vulnerability scanning, monitoring, and cloud orchestration.
