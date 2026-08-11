"""Database engine and session factory owned by the application instance."""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import cast

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker


class Database:
    """Small explicit wrapper that keeps global database state out of imports."""

    def __init__(self, url: str) -> None:
        connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
        self.engine: Engine = create_engine(url, connect_args=connect_args, future=True)
        self._session_factory = sessionmaker(
            bind=self.engine,
            expire_on_commit=False,
            class_=Session,
        )

    @contextmanager
    def session(self) -> Iterator[Session]:
        """Open a transaction, committing on success and rolling back on error."""

        session = self._session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def ping(self) -> bool:
        """Check whether the configured database can execute a trivial query."""

        with self.engine.connect() as connection:
            result = cast(int, connection.execute(text("SELECT 1")).scalar_one())
            return result == 1

    def dispose(self) -> None:
        """Release pooled database resources."""

        self.engine.dispose()
