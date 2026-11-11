"""Disposable real-API browser fixture; never accesses the production database."""
import os
from pathlib import Path
from tempfile import TemporaryDirectory
fixture=TemporaryDirectory(prefix='results-acceptance-')
path=Path(fixture.name)/'results.db'
os.environ['DATABASE_URL']='sqlite:///'+path.as_posix()
api_port=int(os.getenv('RESULTS_API_PORT','5186'))
web_port=int(os.getenv('RESULTS_WEB_PORT','5187'))
os.environ['PUBLIC_ORIGIN']=f'http://localhost:{web_port}'
os.environ['MEDIA_DIR']=str(path.parent/'media')
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
    add_awards(client,c,b,p,tier='official')
try:uvicorn.run(app,host='127.0.0.1',port=api_port)
finally:
    engine.dispose()
    fixture.cleanup()
