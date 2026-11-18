"""Retire visitor-day identifiers while preserving daily totals."""
from .db import Session, now
from .visits import prune_activity


if __name__ == '__main__':
    with Session.begin() as db:
        prune_activity(db, now())
