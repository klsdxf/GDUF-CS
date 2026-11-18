from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session

from .schemas_public import Data
from .schemas_responses import MatchRecord
from .db import db_transaction
from .security import authenticated


from .services import result_service as service


from .schemas_admin import ExpectedVersion, OptionalCommand, RankingResolution, ScoreInput, ScoreRevision, ScoreWrite


from .services.result_service import standings


router = APIRouter(prefix='/api/v1/admin', dependencies=[Depends(authenticated)])


@router.put('/matches/{key}/result', response_model=Data[MatchRecord])
def save_result(key:str,payload:ScoreWrite,db:Session=db_transaction):
    return service.save_result(key, payload.model_dump(mode='json', exclude_unset=True), db)


@router.post('/matches/{key}/result/confirm', response_model=Data[MatchRecord])
def confirm(key:str,payload:ExpectedVersion,idempotency_key:str|None=Header(default=None),db:Session=db_transaction):
    return service.confirm_result(db, key, payload.model_dump(), idempotency_key)


@router.post('/matches/{key}/result/revise-preview')
def revise_preview(key:str,payload:ScoreInput,db:Session=db_transaction):
    return service.revise_preview(key, payload.model_dump(mode='json', exclude_unset=True), db)


@router.post('/matches/{key}/result/revise', response_model=Data[MatchRecord])
def revise(key:str,payload:ScoreRevision,db:Session=db_transaction):
    return service.revise(key, payload.model_dump(mode='json', exclude_unset=True), db)


@router.put('/stages/{key}/ranking-resolution')
def resolve_ranking(key:str,payload:RankingResolution,db:Session=db_transaction):
    return service.resolve_ranking(key, payload.model_dump(mode='json', exclude_unset=True), db)


@router.post('/stages/{key}/qualifications/confirm', response_model=Data[bool])
def qualify(key:str,payload:OptionalCommand|None=None,idempotency_key:str|None=Header(default=None),db:Session=db_transaction):
    return service.confirm_qualification(db, key, payload.model_dump(exclude_unset=True) if payload else {}, idempotency_key)
