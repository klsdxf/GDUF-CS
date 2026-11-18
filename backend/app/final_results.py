from fastapi import APIRouter, Depends, Header
from sqlalchemy.orm import Session

from .db import db_transaction
from .security import authenticated
from .schemas import (
    ResultDraftWrite, ResultPlacementsWrite, ResultPathWrite, ResultAllocationsWrite, ResultPublishWrite,
)
from .schemas_admin import (
    ExpectedVersion, PartnerCreate, PartnerPatch, PrizeCreate, PrizePatch,
    SponsorCreate, SponsorPatch, WithdrawResult,
)
from . import test_rankings
from .services import final_result_service as service
from .services.final_result_service import visible
from .schemas_public import Data, PendingRanking, PublishedRanking, ResultEdition

router = APIRouter(prefix='/api/v1')
admin = APIRouter(prefix='/admin', dependencies=[Depends(authenticated)])


@admin.get('/competitions/{key}/final-results/draft')
def get_draft(key:str,db:Session=db_transaction):
    return service.get_draft(key, db)


@admin.put('/competitions/{key}/final-results/draft')
def save_draft(key:str,payload:ResultDraftWrite,db:Session=db_transaction):
    return service.save_draft(key, payload, db)


@admin.post('/competitions/{key}/final-results/calculate')
def calculate_rankings(key:str,payload: ExpectedVersion,db:Session=db_transaction):
    return service.calculate_rankings(key, payload, db)


@admin.put('/competitions/{key}/final-results/placements')
def save_placements(key:str,payload:ResultPlacementsWrite,db:Session=db_transaction):
    return service.save_placements(key, payload, db)


@admin.put('/competitions/{key}/final-results/path')
def save_path(key:str,payload:ResultPathWrite,db:Session=db_transaction):
    return service.save_path(key, payload, db)


@admin.get('/competitions/{key}/final-results/preview')
def get_preview(key:str,db:Session=db_transaction):
    return service.get_preview(key, db)


@admin.post('/competitions/{key}/final-results/validate')
def check(key:str,payload: ExpectedVersion,db:Session=db_transaction):
    return service.check(key, payload, db)


@admin.post('/competitions/{key}/final-results/publish')
def publish(key:str,payload:ResultPublishWrite,idempotency_key:str=Header(),db:Session=db_transaction):
    return service.publish(key, payload, idempotency_key, db)


@admin.post('/competitions/{key}/final-results/withdraw')
def withdraw(key:str,payload: WithdrawResult,idempotency_key:str|None=Header(default=None),db:Session=db_transaction):
    return service.withdraw(key, payload, idempotency_key, db)


@admin.get('/competitions/{key}/final-results/releases')
def releases(key:str,db:Session=db_transaction):
    return service.releases(key, db)


@admin.get('/sponsors')
def sponsors(db:Session=db_transaction):
    return service.sponsors(db)


@admin.post('/sponsors')
def create_sponsor(payload: SponsorCreate,db:Session=db_transaction):
    return service.create_sponsor(payload, db)


@admin.patch('/sponsors/{key}')
def edit_sponsor(key:str,payload: SponsorPatch,db:Session=db_transaction):
    return service.edit_sponsor(key, payload, db)


@admin.get('/competitions/{key}/partners')
def partners(key:str,db:Session=db_transaction):
    return service.partners(key, db)


@admin.get('/competitions/{key}/prizes')
def prizes(key:str,db:Session=db_transaction):
    return service.prizes(key, db)


@admin.post('/competitions/{key}/partners')
def add_partner(key:str,payload: PartnerCreate,db:Session=db_transaction):
    return service.add_partner(key, payload, db)


@admin.post('/competitions/{key}/prizes')
def add_prize(key:str,payload: PrizeCreate,db:Session=db_transaction):
    return service.add_prize(key, payload, db)


@admin.patch('/competition-partners/{key}')
def edit_partner(key:str,payload: PartnerPatch,db:Session=db_transaction):
    return service.edit_partner(key, payload, db)


@admin.patch('/prizes/{key}')
def edit_prize(key:str,payload: PrizePatch,db:Session=db_transaction):
    return service.edit_prize(key, payload, db)


@admin.put('/competitions/{key}/final-results/allocations')
def save_allocations(key:str,payload:ResultAllocationsWrite,db:Session=db_transaction):
    return service.save_allocations(key, payload, db)


@router.get('/results/latest', response_model=Data[PublishedRanking | PendingRanking | None],
            response_model_exclude_unset=True)
def latest(db:Session=db_transaction):
    return service.latest(db)


@router.get('/results/editions', response_model=Data[list[ResultEdition]], response_model_exclude_unset=True)
def editions(db:Session=db_transaction):
    return service.editions(db)


@router.get('/competitions/{key}/results', response_model=Data[PublishedRanking | PendingRanking],
            response_model_exclude_unset=True)
def public_result(key:str,db:Session=db_transaction):
    return service.public_result(key, db)


@admin.get('/competitions/{key}/final-results/test-matches')
def get_test_matches(key:str,db:Session=db_transaction):
    return service.get_test_matches(key, db)


@admin.put('/competitions/{key}/final-results/test-matches')
def put_test_matches(key:str,payload:test_rankings.ScenarioWrite,db:Session=db_transaction):
    return service.put_test_matches(key, payload, db)


router.include_router(admin)
