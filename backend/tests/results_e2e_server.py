"""Disposable real-API browser fixture; never accesses the production database."""
import os
from pathlib import Path
from uuid import uuid4
path=Path.cwd()/('results-acceptance-'+uuid4().hex+'.db')
os.environ['DATABASE_URL']='sqlite:///'+path.as_posix()
os.environ['PUBLIC_ORIGIN']='http://localhost:5187'
from fastapi.testclient import TestClient
from app.db import Base,engine,Session,Admin
from app.main import app,ph
from tests.test_final_results import prepare,add_awards
import uvicorn
Base.metadata.create_all(engine)
with Session.begin() as db:db.add(Admin(id=1,username='results-admin',password_hash=ph.hash('results-acceptance-only!')))
with TestClient(app) as client:
    client.headers['origin']=os.environ['PUBLIC_ORIGIN']
    login=client.post('/api/v1/admin/auth/login',json={'username':'results-admin','password':'results-acceptance-only!'})
    client.headers['x-csrf-token']=login.json()['data']['csrf']
    c,ids,s,b,p=prepare(client)
    add_awards(client,c,b,p)
try:uvicorn.run(app,host='127.0.0.1',port=5186)
finally:
    engine.dispose()
    path.unlink(missing_ok=True)
