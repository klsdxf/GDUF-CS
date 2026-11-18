"""Rankings published from official match sources are invalidated in the write transaction."""
from sqlalchemy import event, inspect, select
from sqlalchemy.orm import Session as ORMSession

from ..db import Advancement, Competition, Match, Registration, ResultPage, ResultRelease, Stage, now
from .roster_service import audit


@event.listens_for(ORMSession,'before_flush')
def invalidate_releases(db,context,instances):
    official=set();all_kinds=set()
    for obj in list(db.new)+list(db.dirty)+list(db.deleted):
        if isinstance(obj,Match):
            if obj in db.new or obj in db.deleted or any(inspect(obj).attrs[k].history.has_changes() for k in ('result','winner','a','b','confirmed','published','status','rosters')):official.add(obj.competition_id)
        elif isinstance(obj,Stage):official.add(obj.competition_id)
        elif isinstance(obj,Competition):
            state=inspect(obj)
            if state.attrs.published.history.has_changes() or state.attrs.data_origin.history.has_changes() or (state.attrs.status.history.has_changes() and obj.status not in ('ongoing','completed','archived')):all_kinds.add(obj.id)
            if state.attrs.config.history.has_changes() or (state.attrs.status.history.has_changes() and obj.status not in ('completed','archived')):official.add(obj.id)
        elif isinstance(obj,Registration):
            if obj in db.new or obj in db.deleted or inspect(obj).attrs.active.history.has_changes():all_kinds.add(obj.competition_id)
        elif isinstance(obj,Advancement):
            m=db.get(Match,obj.source)
            if m:official.add(m.competition_id)
    for cid in sorted(official | all_kinds):
        invalidate_current(db, cid, include_test=cid in all_kinds)


def invalidate_current(db, competition_id, *, include_test=False):
    page = db.scalar(select(ResultPage).where(ResultPage.competition_id == competition_id))
    if not page or not page.current_release_id:
        return
    release = db.get(ResultRelease, page.current_release_id)
    if include_test or release.result_kind == 'official':
        release.status = 'invalidated'
        release.invalidated_at = now()
        release.invalidation_reason = '来源或有效参赛集合变更'
        page.current_release_id = None
        audit(db, 'final_results.invalidate', release.id, {'reason': release.invalidation_reason})
