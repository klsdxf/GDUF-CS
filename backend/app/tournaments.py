from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session

from .schemas_public import Data
from .schemas_responses import MatchRecord, SchedulePreview, StageRecord
from .db import db_transaction
from .security import authenticated


from .services import schedule_service as service


from .schemas_admin import MatchArrangement, OptionalCommand, StageCreate, StageEntries, StagePatch


from .domain.brackets import generate_graph, seed_order


router = APIRouter(prefix='/api/v1/admin', dependencies=[Depends(authenticated)])


@router.get('/competitions/{key}/stages', response_model=Data[list[StageRecord]])
def stages(key:str,db:Session=db_transaction):
    return service.stages(key, db)


@router.post('/stages', response_model=Data[StageRecord])
def create_stage(payload:StageCreate,db:Session=db_transaction):
    return service.create_stage(payload.model_dump(mode='json', exclude_unset=True), db)


@router.patch('/stages/{key}', response_model=Data[StageRecord])
def edit_stage(key:str,payload:StagePatch,db:Session=db_transaction):
    return service.edit_stage(key, payload.model_dump(mode='json', exclude_unset=True), db)


@router.put('/stages/{key}/entries', response_model=Data[StageRecord])
def entries(key:str,payload:StageEntries,db:Session=db_transaction):
    return service.entries(key, payload.model_dump(mode='json', exclude_unset=True), db)


@router.post('/stages/{key}/generate', response_model=Data[SchedulePreview])
def generate(key:str,payload:OptionalCommand,db:Session=db_transaction):
    return service.generate_schedule(db, key, payload.model_dump(exclude_unset=True))


@router.post('/stages/{key}/discard', response_model=Data[bool])
def discard(key:str,db:Session=db_transaction):
    return service.discard(key, db)


@router.post('/schedule-generations/{key}/publish', response_model=Data[StageRecord])
def publish(key:str,payload:OptionalCommand|None=None,idempotency_key:str|None=Header(default=None),db:Session=db_transaction):
    return service.publish_schedule(db, key, payload.model_dump(exclude_unset=True) if payload else {}, idempotency_key)


@router.get('/competitions/{key}/matches', response_model=Data[list[MatchRecord]])
def matches(key:str,db:Session=db_transaction):
    return service.matches(key, db)


@router.patch('/matches/{key}', response_model=Data[MatchRecord])
def arrange(key:str,payload:MatchArrangement,db:Session=db_transaction):
    return service.arrange(key, payload.model_dump(mode='json', exclude_unset=True), db)


@router.get('/matches/{key}', response_model=Data[MatchRecord])
def get_match(key:str,db:Session=db_transaction):
    return service.get_match(key, db)
