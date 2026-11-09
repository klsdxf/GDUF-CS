from sqlalchemy import select, func
from .db import Session, Registration, Match, Advancement, ResultPage, ResultPlacement, ResultPathMatch, Sponsor, CompetitionPartner, Prize, PrizeAllocation, ResultRelease
with Session() as db:
    for model in (Registration, Match, Advancement, ResultPage, ResultPlacement, ResultPathMatch, Sponsor, CompetitionPartner, Prize, PrizeAllocation, ResultRelease):
        print(model.__tablename__, db.scalar(select(func.count()).select_from(model)))
    for edge in db.scalars(select(Advancement)):
        assert db.get(Match,edge.source) and db.get(Match,edge.target)
    for p in db.scalars(select(ResultPage)):
        if p.current_release_id:
            r=db.get(ResultRelease,p.current_release_id)
            assert r.result_page_id==p.id and r.status=='published'
print('关系核验完成；请对照备份前数量，并抽查公开页面和图片。')
