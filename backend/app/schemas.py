from pydantic import BaseModel, Field

class Login(BaseModel):
    username:str=Field(min_length=1,max_length=80)
    password:str=Field(min_length=1,max_length=256)

class PasswordChange(BaseModel):
    current_password:str=Field(min_length=1,max_length=256)
    password:str=Field(min_length=12,max_length=256)

class CompetitionCreate(BaseModel):
    name:str=Field(min_length=1,max_length=200)
    slug:str=Field(pattern=r'^[a-z0-9-]{1,100}$')
    season:str=Field(default='',max_length=80)
    organizer:str=Field(default='学生社团赛事',max_length=200)
    description:str=Field(default='',max_length=10000)
    rules:str=Field(default='',max_length=50000)
    map_pool:list[str]=Field(default_factory=list,max_length=20)
    team_limit:int=Field(default=32,ge=2,le=32)
    config:dict=Field(default_factory=dict)

from typing import Literal

class ResultVersion(BaseModel):
    expected_version:int=Field(ge=1)

class ResultDisplay(BaseModel):
    edition_label:str=Field(default='',max_length=120)
    season_label:str=Field(default='',max_length=80)
    seal_edition_label:str=Field(default='',max_length=80)
    seal_serial:str=Field(default='',max_length=20)

class ResultDraftWrite(ResultVersion):
    final_stage_id:str|None=None
    final_match_id:str|None=None
    third_place_match_id:str|None=None
    ranking_method:Literal['single','group_single','double','manual']='manual'
    rules_version:str=Field(default='',max_length=40)
    display_meta:ResultDisplay=Field(default_factory=ResultDisplay)
    seal_mode:Literal['monogram','team_logo']='monogram'

class ResultPlacementWrite(BaseModel):
    registration_id:str
    team_display_version:int=Field(ge=1)
    rank_from:int=Field(ge=1,le=32)
    rank_to:int=Field(ge=1,le=32)
    source_method:Literal['calculated','ruling']='ruling'
    ruling_reason:str=Field(default='',max_length=2000)
    display_version_reason:str=Field(default='',max_length=2000)
    eligibility_policy:Literal['starters_only','full_roster','explicit_count']='starters_only'
    recipient_count:int=Field(ge=0)

class ResultPlacementsWrite(ResultVersion):
    items:list[ResultPlacementWrite]=Field(max_length=32)

class ResultPathItem(BaseModel):
    match_id:str
    stage_label:str=Field(default='',max_length=120)

class ResultPathWrite(ResultVersion):
    items:list[ResultPathItem]

class ResultAllocationItem(BaseModel):
    placement_id:str
    prize_id:str
    quantity:int=Field(gt=0)
    distribution:Literal['per_team','per_recipient']
    per_recipient_quantity:int|None=Field(default=None,gt=0)
    display_order:int=0

class ResultAllocationsWrite(ResultVersion):
    items:list[ResultAllocationItem]

class ResultPublishWrite(ResultVersion):
    expected_source_fingerprint:str
    reason:str=Field(min_length=1,max_length=2000)
