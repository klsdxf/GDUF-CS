"""Exercise both fresh migrations and a frozen, genuine revision-003 schema."""
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import pytest


@pytest.mark.parametrize('legacy',[False,'002','003'])
def test_migrate_and_preserve_legacy_data(tmp_path,legacy):
    path=tmp_path/'migration.db'
    if legacy:
        with sqlite3.connect(path) as db:
            db.executescript((Path(__file__).parent/'fixtures/schema003.sql').read_text(encoding='utf-8'))
            db.execute("INSERT INTO competitions VALUES ('old','old-cup','Existing cup','2025','Club','','Rules','[]','{}','archived',1,0,8,0,NULL)")
            db.execute("INSERT INTO registrations VALUES ('team','old','OLD','Existing team','','private-contact','','OLD','OLD','[]',1,1)")
            db.execute("INSERT INTO roster_snapshots VALUES ('team',1,'Existing team','','','OLD','OLD','[]')")
            if legacy=='002':
                for table in ('prize_allocations','result_path_matches','result_placements','result_releases','competition_result_pages','prizes','competition_partners','sponsors'):
                    db.execute('DROP TABLE '+table)
                for table in ('registrations','roster_snapshots'):
                    for column in ('english_name','emblem_text','poster_title_lines'):
                        db.execute(f'ALTER TABLE {table} DROP COLUMN {column}')
                db.execute("UPDATE alembic_version SET version_num='002'")
    env={**os.environ,'DATABASE_URL':'sqlite:///'+path.as_posix()}
    result=subprocess.run([sys.executable,'-m','alembic','upgrade','head'],cwd=Path(__file__).parents[1],env=env,capture_output=True,text=True)
    assert result.returncode==0,result.stdout+result.stderr
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT version_num FROM alembic_version').fetchone()[0]=='004'
        tables={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert {'result_test_matches','seed_batches','seed_entities','seed_previews'}<=tables
        assert db.execute('PRAGMA foreign_key_check').fetchall()==[]
        if legacy:
            assert db.execute("SELECT data_origin,seed_batch_id,name FROM competitions WHERE id='old'").fetchone()==('regular',None,'Existing cup')
            assert db.execute("SELECT name FROM registrations WHERE id='team'").fetchone()[0]=='Existing team'
            assert db.execute('SELECT COUNT(*) FROM roster_snapshots').fetchone()[0]==1
