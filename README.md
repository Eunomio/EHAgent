# 居安Agent（EHAgent）

EHAgent is a local-first multimodal risk-agent prototype for the competition period. Version `0.1.0` is the foundational skeleton: it deliberately runs without the Ezviz platform or physical devices and keeps all unimplemented integrations behind explicit adapter contracts.

## What v0.1.0 contains

- FastAPI backend with `/api/v1` contracts;
- SQLite persistence managed by Alembic;
- explicit `UNINITIALIZED`, `COMMISSIONING`, `ACTIVE`, `MAINTENANCE` and `SUSPENDED` modes;
- Replay and Manual camera adapters;
- engineering-only manual observation injection;
- resident, admin and engineering Vue route shells;
- tests, environment manifests and Windows scripts.

It does **not** claim Ezviz access, camera inference, risk scoring or production readiness yet.

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
./scripts/install.ps1
```

Replace `EHAGENT_ENGINEERING_API_KEY` in `.env` with a long random value before using engineering endpoints.

## Run

```powershell
./scripts/start.ps1
```

Then open:

- resident shell: <http://127.0.0.1:8000/>;
- OpenAPI: <http://127.0.0.1:8000/docs>;
- health: <http://127.0.0.1:8000/api/v1/health>.

For frontend development, keep the backend running and start Vite in a second terminal:

```powershell
npm.cmd --prefix frontend run dev
```

Open <http://127.0.0.1:5173/> for the resident, admin and engineering route shells.

## Test

```powershell
./scripts/test.ps1
```

## Engineering API authentication

Engineering routes require:

```http
X-Engineering-Key: <EHAGENT_ENGINEERING_API_KEY>
```

They also reject non-loopback clients. This is an initial engineering guard, not the final PIN/session implementation described by the PRD.

## Architecture rules

1. UI code calls only the local FastAPI service.
2. Business services depend on adapter contracts, never Ezviz response objects.
3. Every observation records both `source_type` and `runtime_mode`.
4. Replay/Manual data cannot be converted into real-device data.
5. State transitions are defined once in the domain layer.
6. Database changes are made only through Alembic migrations.
7. Secrets never enter frontend files, logs, fixtures or Git.

See [docs/architecture.md](docs/architecture.md) and [docs/development.md](docs/development.md) for module boundaries and the next implementation steps.
