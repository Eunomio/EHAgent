# Architecture

## Layers

```text
Resident API / Engineering API / Vue product modules
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

## Implemented v0.2.0 vertical slice

```text
Replay material or explicitly labelled manual image
    ↓
immutable ObservationEvent with source_type + runtime_mode
    ↓
quality gate → deterministic corridor rule
    ↓
persisted risk task → resident four-action feedback
    ↓
DONE → RESCAN_PENDING → clear-corridor replay → RESOLVED
```

The resident view may display a commissioning task only as an explicit demonstration preview. Such a task keeps `is_demo=true`, triggers no external notification and must not enter real-device metrics.

## Next vertical slice

1. real replay manifest and frame-file ingestion rather than bundled case definitions;
2. scene calibration API and editor;
3. optional ONNX quality/detection pipeline behind the same analysis contract;
4. task centre and dispute-review report;
5. `EzvizCameraAdapter` only after the platform PoC.
