"""Disposable browser acceptance database, separate from dev and production data."""
import os
from pathlib import Path
from uuid import uuid4
import uvicorn

path=Path.cwd()/('backend-data-acceptance-'+uuid4().hex+'.db')
os.environ['DATABASE_URL']='sqlite:///'+path.as_posix()
os.environ['PUBLIC_ORIGIN']='http://localhost:5191'
from app.db import Base,engine,Session,Admin
from app.main import app,ph

Base.metadata.create_all(engine)
with Session.begin() as db:
    db.add(Admin(id=1,username='dataset-admin',password_hash=ph.hash('dataset-acceptance-only!')))
try:
    uvicorn.run(app,host='127.0.0.1',port=5190)
finally:
    engine.dispose()
    path.unlink(missing_ok=True)
