"""Remove expired sessions and previews, and retire delivered cache events."""
from datetime import timedelta

from sqlalchemy import delete, update

from ..db import AdminSession, CacheInvalidation, ImportBatch, OperationReceipt, SeedPreview, Session, now
from ..visits import prune_activity


def cleanup():
    stamp = now()
    with Session.begin() as db:
        for model in (AdminSession, SeedPreview, OperationReceipt):
            db.execute(delete(model).where(model.expires_at < stamp))
        db.execute(update(ImportBatch).where(ImportBatch.expires_at < stamp, ImportBatch.status == 'preview')
                   .values(status='expired', payload={}))
        db.execute(delete(CacheInvalidation).where(CacheInvalidation.completed_at < stamp - timedelta(days=7)))
        prune_activity(db, stamp)


if __name__ == '__main__':
    cleanup()
