"""Apply only the accepted Poppin'Party branding, in one DB transaction."""
import argparse
import hashlib
import json
import os
from copy import deepcopy
from pathlib import Path
from sqlalchemy import select
from app.db import Session, Admin, Registration, RosterSnapshot, ResultRelease
from app import final_results as fr
from app.schemas import ResultPublishWrite

parser=argparse.ArgumentParser()
parser.add_argument('--apply',action='store_true')
parser.add_argument('--asset',required=True,help='Basename of the copied WebP in MEDIA_DIR')
parser.add_argument('--sha256',required=True)
args=parser.parse_args()
if Path(args.asset).name!=args.asset or not args.asset.endswith('.webp'):
    raise SystemExit('Expected a WebP basename')
asset=Path(os.getenv('MEDIA_DIR','storage/media'))/args.asset
if hashlib.sha256(asset.read_bytes()).hexdigest()!=args.sha256:
    raise SystemExit('Logo checksum mismatch')
url='/media/'+args.asset

with Session.begin() as db:
    admin=db.get(Admin,1)
    if not admin or admin.username in {'review-admin','dataset-admin','results-admin','test-admin'}:
        raise SystemExit('A confirmed production administrator is required')
    c,p=fr.page(db,'autumn')
    if c.data_origin!='test' or p.result_kind!='test' or not p.current_release_id:
        raise SystemExit('Expected the published autumn test result')
    team=db.scalar(select(Registration).where(Registration.competition_id==c.id,Registration.name=="Poppin'Party").with_for_update())
    if not team:raise SystemExit('Poppin\'Party not found')
    release=db.get(ResultRelease,p.current_release_id)
    before=deepcopy(release.public_snapshot)
    def normalize(value):
        if isinstance(value,list):return [normalize(x) for x in value]
        if isinstance(value,dict):
            out={k:normalize(v) for k,v in value.items() if k!='release'}
            if out.get('team_id')==team.id:
                out.pop('logo_url',None);out.pop('seal_mode',None)
            return out
        return value
    if normalize(fr.preview(db,c,p))!=normalize(before):
        raise SystemExit('Unpublished draft changes exist; reconcile them before this logo-only update')
    print(json.dumps({'team':team.name,'logo':url,'apply':args.apply},ensure_ascii=True))
    already=(team.logo==url and before['champion'].get('logo_url')==url and before['champion'].get('seal_mode')=='team_logo')
    if already:print('Logo is already applied; no changes required')
    if args.apply and not already:
        team.logo=url
        for snapshot in db.scalars(select(RosterSnapshot).where(RosterSnapshot.registration_id==team.id)):
            snapshot.logo=url
        p.config={**p.config,'seal_mode':'team_logo'}
        fr.bump(db,p,p.version)
        after=fr.preview(db,c,p)
        if normalize(after)!=normalize(before):
            raise SystemExit('Unexpected non-logo changes; transaction rolled back')
        check=fr.validate(db,c,p)
        if check['blocking_errors']:raise SystemExit(json.dumps(check['blocking_errors'],ensure_ascii=True))
        result=fr.publish(c.id,ResultPublishWrite(expected_version=p.version,expected_source_fingerprint=check['source_fingerprint'],reason='Apply the user-approved Poppin\'Party logo only'),'aliyun-logo-'+args.sha256,db)['data']
        fr.audit(db,'team.logo',team.id,{'logo':url,'reason':'User-approved logo only'})
        print(json.dumps({'release_id':result['id'],'applied':True},ensure_ascii=True))
