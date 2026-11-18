"""Compare the original and current schedule queries on the same synthetic database."""
import json
import os
from pathlib import Path
import subprocess
import sys
from statistics import median
from time import perf_counter
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'backend'))

from sqlalchemy import event, func, select, text

from app.db import Audit, Competition, Match, Session, engine
from app.public import matches


def original(ref):
    file = subprocess.check_output(['git', 'show', f'{ref}:backend/app/public.py'], cwd=ROOT)
    module = ModuleType('app.quality_baseline_public')
    exec(compile(file, '<baseline public.py>', 'exec'), module.__dict__)
    return module.matches


def measure(read):
    statements = []
    wall_ms = []

    def collect(connection, cursor, statement, parameters, context, many):
        if statement.lstrip().upper().startswith('SELECT'):
            statements.append(statement)

    event.listen(engine, 'before_cursor_execute', collect)
    try:
        counts = []
        for _ in range(3):
            start = perf_counter()
            result = read()
            wall_ms.append((perf_counter() - start) * 1000)
            counts.append(len(statements))
            statements.clear()
        return {'matches': len(result['data']), 'select_counts': counts,
                'median_wall_ms': round(median(wall_ms), 2)}
    finally:
        event.remove(engine, 'before_cursor_execute', collect)


def main():
    if os.getenv('GDUF_TEST_ISOLATED') != '1' or engine.url.database != 'gduf_perf' or engine.url.host not in (
            'localhost', '127.0.0.1'):
        raise SystemExit('Requires a disposable local gduf_perf database')
    os.environ['PUBLIC_CACHE_DISABLED'] = '1'
    baseline_ref = sys.argv[1] if len(sys.argv) > 1 else '12f1330'
    if not baseline_ref.isalnum():
        raise SystemExit('Provide a Git commit hash')
    baseline = original(baseline_ref)
    with Session() as db:
        counts = {name: db.scalar(select(func.count()).select_from(model)) for name, model in
                  [('editions', Competition), ('matches', Match), ('audit_events', Audit)]}
        hot_id = db.scalar(select(Competition.id).where(Competition.slug == 'quality-hot'))
        if hot_id is None:
            raise SystemExit('Synthetic data generation must finish first')
        plan = db.execute(text("""
            EXPLAIN (ANALYZE, BUFFERS)
            SELECT id FROM matches WHERE competition_id = :edition AND published IS TRUE
            ORDER BY scheduled_at ASC NULLS LAST, round, code, id
        """), {'edition': hot_id}).scalars().all()
    report = {'baseline': baseline_ref, 'data': counts, 'postgresql_plan': plan, 'schedule': {}}
    for slug in ('quality-hot', 'quality-01'):
        def old():
            with Session() as db:
                return baseline(slug, None, None, None, db=db)
        report['schedule'][slug] = {'before': measure(old), 'after': measure(lambda: matches(slug))}
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
