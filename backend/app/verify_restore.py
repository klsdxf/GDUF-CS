"""Verify restored links and emit a deterministic digest of historical data."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

from fastapi.encoders import jsonable_encoder
from sqlalchemy import func, select

from .db import (
    Session, Advancement, Announcement, Competition, CompetitionPartner, Match, Member,
    Prize, PrizeAllocation, Registration, ResultPage, ResultPathMatch, ResultPlacement,
    ResultRelease, ResultTestMatch, RosterSnapshot, SeedBatch, SeedEntity, Sponsor, Stage,
)


COUNTED = (Competition, Stage, Registration, Member, RosterSnapshot, Match, Advancement, Announcement,
           ResultPage, ResultPlacement, ResultPathMatch, Sponsor, CompetitionPartner, Prize,
           PrizeAllocation, ResultRelease, ResultTestMatch, SeedBatch, SeedEntity)


def fingerprint(items):
    canonical = json.dumps(jsonable_encoder(items), sort_keys=True, separators=(',', ':'), ensure_ascii=False)
    return hashlib.sha256(canonical.encode()).hexdigest()


def media_hashes():
    media_dir = Path(os.getenv('MEDIA_DIR', 'storage/media'))
    output = {}
    for image in sorted(media_dir.rglob('*')):
        if image.is_file():
            with image.open('rb') as source:
                output[image.relative_to(media_dir).as_posix()] = hashlib.file_digest(source, 'sha256').hexdigest()
    return output


def manifest(db):
    counts = {model.__tablename__: db.scalar(select(func.count()).select_from(model)) for model in COUNTED}
    for page in db.scalars(select(ResultPage).where(ResultPage.current_release_id.is_not(None))):
        release = db.get(ResultRelease, page.current_release_id)
        if not release or release.result_page_id != page.id or release.status != 'published':
            raise ValueError(f'Invalid release reference: {page.id}')
    for release in db.scalars(select(ResultRelease).order_by(ResultRelease.id)):
        if fingerprint(release.public_snapshot) != release.content_sha256:
            raise ValueError(f'Invalid release snapshot digest: {release.id}')
    snapshots = db.execute(select(RosterSnapshot.__table__).order_by(
        RosterSnapshot.registration_id, RosterSnapshot.version)).mappings()
    matches = db.execute(select(Match.id, Match.rosters).order_by(Match.id)).mappings()
    return {'counts': counts, 'roster_sha256': fingerprint([dict(row) for row in snapshots]),
            'match_rosters_sha256': fingerprint([dict(row) for row in matches]),
            'media_sha256': media_hashes()}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--expect', action='store_true', help='compare the manifest with JSON on stdin')
    args = parser.parse_args()
    with Session() as db:
        value = manifest(db)
    if args.expect and json.load(sys.stdin) != value:
        raise SystemExit('Restored manifest does not match the backup')
    print(json.dumps(value, sort_keys=True, ensure_ascii=False))


if __name__ == '__main__':
    main()
