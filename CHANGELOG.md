# Changelog

All notable changes to EHAgent are documented in this file.

## [0.2.0] - 2026-08-12

### Added

- Interactive Replay/Manual material console with three deterministic corridor cases.
- Visible observe, quality, rule and action stages for explainable demonstrations.
- Persisted risk-task and idempotent resident-feedback state machines.
- Before/after rescan flow that resolves only a `RESCAN_PENDING` task.
- Accessible resident task card with font controls, speech, large actions and confirmations.
- Built-in source-labelled SVG materials and local image preview with manual-case disclosure.
- API integration tests for task creation, four-action feedback, provenance and rescan closure.

### Changed

- Replaced resident, engineering and admin route placeholders with usable product modules.
- Updated the README, architecture and PRD baseline for the v0.2.0 vertical slice.

### Known limitations

- No Ezviz device access or automatic vision inference is claimed.
- Manual uploads are engineering-labelled demonstrations, not model predictions.

## [0.1.0] - 2026-08-11

### Added

- Maintainable FastAPI application factory and versioned API skeleton.
- SQLite/SQLAlchemy persistence with an Alembic baseline migration.
- Explicit runtime modes and validated state transitions.
- Camera adapter contracts plus Replay and Manual implementations.
- Health, version, runtime and engineering manual-event endpoints.
- Separate resident, admin and engineering Vue route shells.
- Windows install, start, test and health-check scripts.
- Pinned Python and frontend environment manifests.
- Unit and API tests for the foundational behavior.
