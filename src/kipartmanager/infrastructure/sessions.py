"""Borrow a caller's transaction, or retain the existing per-call transaction."""

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, text
from sqlalchemy.orm import Session


@contextmanager
def repository_session(
    engine: Engine, borrowed: Session | None, *, write: bool = False
) -> Iterator[Session]:
    if borrowed is not None:
        if not borrowed.in_transaction():
            raise RuntimeError("A borrowed session requires an active transaction.")
        yield borrowed
        borrowed.flush()
        return
    with Session(engine) as session:
        if write:
            with session.begin():
                session.execute(text("BEGIN IMMEDIATE"))
                yield session
        else:
            yield session
