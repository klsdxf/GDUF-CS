from sqlalchemy import select, func
from .db import Session, Registration, Match, Advancement
with Session() as db:
    for model in (Registration, Match, Advancement):
        print(model.__tablename__, db.scalar(select(func.count()).select_from(model)))
    for edge in db.scalars(select(Advancement)):
        assert db.get(Match,edge.source) and db.get(Match,edge.target)
print('关系核验完成；请对照备份前数量，并抽查公开页面和图片。')
