# 居安Agent（EHAgent）

EHAgent is a local-first multimodal risk-agent prototype for the competition period. Version `0.2.0` provides an honest, end-to-end demonstration slice for one corridor-obstruction scenario. It deliberately separates deterministic Replay/Manual demonstrations from future Ezviz and vision-model capabilities.

## What v0.2.0 contains

- FastAPI backend with `/api/v1` contracts;
- SQLite persistence managed by Alembic;
- explicit `UNINITIALIZED`, `COMMISSIONING`, `ACTIVE`, `MAINTENANCE` and `SUSPENDED` modes;
- an engineering test console with built-in Replay materials and local image preview;
- a visible Agent pipeline: observe, quality gate, deterministic risk rule and action;
- persisted cleanup tasks, idempotent resident feedback and audited state transitions;
- a before/after rescan flow that does not close a task merely because the resident clicks Done;
- an accessible resident task card with large targets, font scaling, speech and confirmations;
- explicit `REPLAY`/`MANUAL` labels on every demonstration result;
- tests, environment manifests and Windows scripts.

It does **not** claim Ezviz access, automatic camera inference, measured risk-model accuracy or production readiness. Uploaded images require an engineering-selected case label and remain `MANUAL` data.

## Prerequisites

- Windows 10/11;
- project Python 3.11 environment at `.venv`;
- Node.js 20 or newer for frontend development;
- Git;
- FFmpeg later, when standard-stream frame extraction is introduced.

The repository includes both `environment.yml` and pinned `requirements*.txt` files. The project environment is isolated under `.venv` and must never be committed.

## First-time setup

```powershell
Copy-Item .env.example .env
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\install.ps1
```

Replace `EHAGENT_ENGINEERING_API_KEY` in `.env` with a long random value before using engineering endpoints.

## Run

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\start.ps1
```

Then open:

- backend status: <http://127.0.0.1:8000/>;
- OpenAPI: <http://127.0.0.1:8000/docs>;
- health: <http://127.0.0.1:8000/api/v1/health>.

For frontend development, keep the backend running and start Vite in a second terminal:

```powershell
npm.cmd --prefix frontend run dev
```

Open:

- resident experience: <http://127.0.0.1:5173/>;
- product boundary dashboard: <http://127.0.0.1:5173/admin>;
- engineering test console: <http://127.0.0.1:5173/engineering>.

If the checkout is reached through a Windows directory junction, run Vite and production builds from the repository's physical path. Rollup may otherwise see the same input under two drive paths.

## Demonstrate the Agent loop

1. Put the system in `COMMISSIONING` from the engineering console.
2. Run **走廊中部有纸箱** and inspect the four visible Agent stages.
3. Open the resident page and confirm the task has a permanent demonstration label.
4. Use one of the four resident actions. `DONE` changes the task to `RESCAN_PENDING`.
5. Run **整改后的通畅走廊** to perform a comparable rescan and resolve the task.
6. Run **严重模糊的走廊** to verify that the quality gate refuses to judge.
7. Optionally upload a local image, choose its expected demo case and verify it is labelled `MANUAL` rather than inferred.

## Test

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\test.ps1
```

## Engineering API authentication

Engineering routes require:

```http
X-Engineering-Key: <EHAGENT_ENGINEERING_API_KEY>
```

They also reject non-loopback clients. The test console keeps the key only in browser `sessionStorage`. This is an engineering guard, not the final PIN/session implementation described by the PRD.

## Architecture rules

1. UI code calls only the local FastAPI service.
2. Business services depend on adapter contracts, never Ezviz response objects.
3. Every observation records both `source_type` and `runtime_mode`.
4. Replay/Manual data cannot be converted into real-device data and always display a demo label.
5. State transitions are defined once in the domain layer.
6. Database changes are made only through Alembic migrations.
7. Secrets never enter frontend files, logs, fixtures or Git.

See [docs/architecture.md](docs/architecture.md), [docs/product-vertical-slice.md](docs/product-vertical-slice.md) and [docs/development.md](docs/development.md) for module boundaries, product acceptance and next steps.
