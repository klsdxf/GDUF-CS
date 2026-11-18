"""Build synthetic data for the fixed-rate benchmark in an empty isolated PostgreSQL database."""
import os

from sqlalchemy import select

from ..db import Competition, Match, Session, engine
from ..services import result_service, roster_service, schedule_service
from ..infrastructure import outbox  # transactional event capture

MAPS = {'maps': [{'map_name': 'Mirage', 'score_a': 13, 'score_b': 7}]}


def confirm(db, match):
    result_service.save_result(match.id, {**MAPS, 'expected_version': match.version}, db)
    result_service.confirm_result(db, match.id, {'expected_version': match.version})


def seed_edition(edition, historical):
    with Session.begin() as db:
        slug = f'quality-{edition:02d}' if historical else 'quality-hot'
        competition = Competition(slug=slug, name=f'Quality fixture {edition}', season='2026',
                                  rules='Synthetic BO1', map_pool=['Mirage'])
        db.add(competition)
        db.flush()
        teams = [{'code': f'T{i:02d}', 'name': f'Fixture team {i}', 'contact': 'synthetic',
                  'members': [{'steam_id': str(76561198000000000 + i * 10 + j), 'nickname': f'P{i}-{j}',
                               'role': '正式', 'captain': j == 0} for j in range(5)]}
                 for i in range(32)]
        ids = roster_service.save_roster(db, competition, teams, 'create')
        roster_service.apply_competition_publication(competition.id, db)
        stage_id = schedule_service.create_stage({
            'competition_id': competition.id, 'name': 'Synthetic stage',
            'type': 'group_single' if historical else 'single',
            'config': {'best_of': 1, 'groups': 2, 'qualify': 2} if historical else {'best_of': 1},
        }, db)['data']['id']
        schedule_service.entries(stage_id, {'entries': ids}, db)
        schedule_service.generate_schedule(db, stage_id, {'idempotency_key': 'quality-seed'})
        schedule_service.publish_schedule(db, stage_id)
        if not historical:
            from ..content import announcement_save
            from ..db import Announcement
            announcement = announcement_save(db, Announcement(competition_id=competition.id, title='', body=''),
                                             {'title': 'Quality fixture', 'body': 'Synthetic', 'published': True})
            print(f'Hot edition: {slug}, announcement: {announcement["data"]["id"]}', flush=True)
            return
        matches = list(db.scalars(select(Match).where(Match.stage_id == stage_id).order_by(Match.round, Match.code)))
        for match in matches:
            if match.group:
                confirm(db, match)
        result_service.confirm_qualification(db, stage_id, {}, 'quality-seed')
        while any(not m.confirmed for m in matches):
            ready = [m for m in matches if not m.confirmed and m.a and m.b]
            if not ready:
                raise RuntimeError('Synthetic bracket did not reach a terminal state')
            for match in ready:
                confirm(db, match)
        roster_service.update_competition(competition.id, {'status': 'archived'}, db)


def main():
    url = engine.url
    if (os.getenv('GDUF_TEST_ISOLATED') != '1' or url.get_backend_name() != 'postgresql'
            or url.host not in ('localhost', '127.0.0.1') or url.database != 'gduf_perf'):
        raise SystemExit('Requires GDUF_TEST_ISOLATED=1 and a disposable local gduf_perf database')
    with Session() as db:
        if db.scalar(select(Competition.id).limit(1)):
            raise SystemExit('The performance database must be empty')
    for i in range(1, 31):
        seed_edition(i, historical=True)
        print(f'Archived edition {i}/30', flush=True)
    seed_edition(31, historical=False)


if __name__ == '__main__':
    main()
