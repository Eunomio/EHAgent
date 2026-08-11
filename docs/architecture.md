# Architecture

## Layers

```text
API / Vue shells
    ↓
Application services
    ↓
Domain models and state machines
    ↓
Repositories and adapter contracts
    ↓
SQLite / Replay / Manual / future Ezviz integration
```

## Dependency direction

- `app.domain` has no FastAPI, SQLAlchemy or vendor imports.
- `app.adapters` implements domain-facing contracts and never assesses risk.
- `app.services` orchestrates domain rules and persistence.
- `app.api` validates transport data and delegates to services.
- `app.db` owns SQLAlchemy models and sessions.
- `frontend` knows only local `/api/v1` contracts.

## Runtime and source separation

`runtime_mode` answers *why the system is running*; `source_type` answers *where the data came from*. A real camera used during commissioning remains test data:

```text
runtime_mode=COMMISSIONING
source_type=REAL_DEVICE
```

Neither field may be rewritten after event creation.

## Planned next vertical slice

1. persisted cleanup-task state machine;
2. resident four-action task card;
3. Replay before/after rescan sequence;
4. scene calibration API and Konva editor;
5. quality gate and optional vision dependencies;
6. `EzvizCameraAdapter` after the platform PoC.
