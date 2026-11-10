"""Run inside the API container; preview by default, --apply to commit."""
import argparse
import json
from sqlalchemy import select
from app.db import Session, Admin
from app.test_data import preview, commit, PreviewInput, CommitInput

args=argparse.ArgumentParser()
args.add_argument('--apply',action='store_true')
options=args.parse_args()
with Session.begin() as db:
    admin=db.scalar(select(Admin).where(Admin.id==1).with_for_update())
    if not admin or admin.username in {'review-admin','dataset-admin','results-admin','test-admin'}:
        raise SystemExit('A confirmed production administrator is required; do not copy the local review database.')
    result=preview(PreviewInput(),db)['data']
    print(json.dumps(result,ensure_ascii=True,default=str))
    if result['conflicts']:
        raise SystemExit('Existing data conflicts; no business data was imported.')
    if options.apply:
        batch=commit(result['id'],CommitInput(content_sha256=result['content_sha256']),'aliyun-public-test-v1',db)['data']
        print(json.dumps({'batch_id':batch['id'],'applied':True},ensure_ascii=True))
