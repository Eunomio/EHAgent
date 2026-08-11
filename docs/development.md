# Development guide

## Commands

```powershell
./scripts/install.ps1
./scripts/start.ps1
./scripts/test.ps1
./scripts/health.ps1
```

## Adding an adapter

1. Implement `CameraSource` from `app/adapters/base.py`.
2. Return normalized domain objects only.
3. Map vendor failures to internal adapter errors.
4. Add contract tests without real credentials.
5. Register the adapter in the composition root, not inside business services.

## Adding a database change

1. Update SQLAlchemy records.
2. Create an Alembic revision.
3. Test migration from an empty database and the previous release.
4. Do not call `Base.metadata.create_all()` in production startup.

## Version checklist

- update `VERSION`, `app.__version__`, `pyproject.toml` and frontend package version;
- update `CHANGELOG.md`;
- run backend and frontend tests;
- run Alembic from an empty database;
- run secret scanning and inspect `git diff --cached`;
- tag the commit as `vX.Y.Z` only after tests pass.
