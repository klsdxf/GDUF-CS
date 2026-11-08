"""Create disposable acceptance data only when explicitly enabled."""
import os
from datetime import timedelta
from fastapi.testclient import TestClient
from app.db import Base, engine, Session, Admin, now
from app.main import app,ph
from .test_platform import setup_competition,call

if os.getenv('E2E')!='1' or 'acceptance' not in str(engine.url):
    raise SystemExit('仅允许 E2E=1 且数据库路径含 acceptance 的独立验收库')
Base.metadata.create_all(engine)
with Session.begin() as db:
    if db.get(Admin,1):raise SystemExit('验收库已经存在，请使用新的验收数据库文件')
    db.add(Admin(id=1,username='test-admin',password_hash=ph.hash(os.environ['E2E_PASSWORD'])))
with TestClient(app) as client:
    client.headers['origin']='http://localhost:5173'
    response=client.post('/api/v1/admin/auth/login',json={'username':'test-admin','password':os.environ['E2E_PASSWORD']})
    client.headers['x-csrf-token']=response.json()['data']['csrf']
    c,ids,s=setup_competition(client,16,'group_single',{'best_of':1,'groups':4,'qualify':2})
    ms=call(client,'/admin/competitions/'+c['id']+'/matches')
    for i,m in enumerate(ms):
        if m['a'] and m['b']:call(client,'/admin/matches/'+m['id'],'patch',{'scheduled_at':(now()+timedelta(hours=i*2)).isoformat(),'status':'scheduled'})
    call(client,'/admin/announcements','post',{'competition_id':c['id'],'title':'验收赛事公告','body':'这是独立验收数据库中的合成内容。','published':True})
print('Acceptance dataset ready')
