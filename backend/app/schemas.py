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
