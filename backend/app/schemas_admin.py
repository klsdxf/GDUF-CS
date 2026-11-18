from datetime import datetime
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, Field, StrictBool, StrictInt, field_validator, model_validator

ID = Annotated[str, Field(min_length=1, max_length=100)]
Text = Annotated[str, Field(max_length=2000)]
Reason = Annotated[str, Field(min_length=1, max_length=2000, pattern=r'\S')]
Version = Annotated[StrictInt, Field(ge=0)]
Key = Annotated[str, Field(min_length=1, max_length=128)]
StageType = Literal['single', 'group_single', 'double']
CompetitionStatus = Literal['draft', 'roster_preparation', 'scheduling', 'ongoing', 'completed', 'archived']


class Patch(BaseModel):
    @model_validator(mode='after')
    def reject_nulls(self):
        for field in self.model_fields_set:
            if getattr(self, field) is None and field not in self.nullable_fields():
                raise ValueError(f'{field} does not accept null')
        return self

    def nullable_fields(self):
        return ()


class ExpectedVersion(BaseModel):
    expected_version: Version


class OptionalCommand(Patch):
    expected_version: Version | None = None
    idempotency_key: Key | None = None


class ScoreMap(BaseModel):
    map_name: Annotated[str, Field(min_length=1, max_length=80)]
    score_a: Annotated[StrictInt, Field(ge=0, le=1000)]
    score_b: Annotated[StrictInt, Field(ge=0, le=1000)]
    overtime: StrictBool = False


class ScoreInput(BaseModel):
    result_type: Literal['normal', 'forfeit', 'technical'] = 'normal'
    maps: list[ScoreMap] = Field(default_factory=list, max_length=5)
    winner: ID | None = None
    reason: Text = ''


class ScoreWrite(ScoreInput, ExpectedVersion):
    pass


class ScoreRevision(ScoreWrite):
    reason: Reason


class RankingResolution(BaseModel):
    expected_version: Version | None = None
    group: Annotated[str, Field(max_length=8)] = ''
    teams: list[ID] = Field(min_length=1, max_length=32)
    reason: Reason


class StageConfig(Patch):
    best_of: Literal[1, 3, 5] | None = None
    groups: Annotated[StrictInt, Field(ge=1, le=16)] | None = None
    qualify: Annotated[StrictInt, Field(ge=1, le=16)] | None = None
    draw: Literal['manual', 'random'] | None = None
    random_seed: StrictInt | None = None
    manual_groups: list[list[ID]] | None = Field(default=None, max_length=16)
    qualifier_order: list[ID] | None = Field(default=None, max_length=32)
    double_round: StrictBool | None = None
    third_place: StrictBool | None = None
    grand_final_reset: StrictBool | None = None

    def nullable_fields(self):
        return ('random_seed',)

    @model_validator(mode='before')
    @classmethod
    def check_scoring(cls, data):
        if isinstance(data, dict) and 'points' in data:
            raise ValueError('暂只支持固定积分规则')
        return data


class StageCreate(BaseModel):
    competition_id: ID
    name: Annotated[str, Field(min_length=1, max_length=200)]
    type: StageType
    config: StageConfig = Field(default_factory=StageConfig)


class StagePatch(Patch):
    expected_version: Version | None = None
    name: Annotated[str, Field(min_length=1, max_length=200)] | None = None
    config: StageConfig | None = None


class StageEntries(OptionalCommand):
    entries: list[ID] = Field(min_length=2, max_length=32)


class MatchArrangement(Patch):
    expected_version: Version | None = None
    scheduled_at: AwareDatetime | None = None
    status: Literal['unscheduled', 'scheduled', 'ongoing', 'postponed', 'cancelled'] | None = None

    @field_validator('scheduled_at', mode='before')
    @classmethod
    def empty_time(cls, value):
        return None if value == '' else value

    def nullable_fields(self):
        return ('scheduled_at',)


class MemberWrite(BaseModel):
    nickname: Annotated[str, Field(min_length=1, max_length=100)]
    steam_id: Annotated[str, Field(pattern=r'^7656119\d{10}$')]
    role: Literal['正式', '替补']
    captain: StrictBool


class RosterWrite(BaseModel):
    name: Annotated[str, Field(min_length=1, max_length=100)]
    contact: Annotated[str, Field(min_length=1, max_length=200)]
    members: list[MemberWrite] = Field(min_length=5, max_length=7)
    description: Text = ''
    logo: Text = ''
    english_name: Annotated[str, Field(max_length=120)] = ''
    emblem_text: Annotated[str, Field(max_length=12)] = ''
    poster_title_lines: list[Annotated[str, Field(max_length=120)]] = Field(default_factory=list, max_length=2)


class RosterCreate(RosterWrite):
    code: Annotated[str, Field(min_length=1, max_length=32)]


class RosterEdit(RosterWrite):
    expected_version: Version | None = None


class RosterRevision(RosterWrite, ExpectedVersion):
    reason: Reason


class ImportCommit(BaseModel):
    idempotency_key: Key


class CompetitionPatch(Patch):
    expected_version: Version | None = None
    name: Annotated[str, Field(min_length=1, max_length=200)] | None = None
    season: Annotated[str, Field(max_length=80)] | None = None
    organizer: Annotated[str, Field(max_length=200)] | None = None
    description: Annotated[str, Field(max_length=10000)] | None = None
    rules: Annotated[str, Field(max_length=50000)] | None = None
    map_pool: list[Annotated[str, Field(max_length=80)]] | None = Field(default=None, max_length=20)
    team_limit: Annotated[StrictInt, Field(ge=2, le=32)] | None = None
    config: dict | None = None
    focus_match_id: ID | None = None
    status: CompetitionStatus | None = None
    is_default: StrictBool | None = None

    def nullable_fields(self):
        return ('focus_match_id',)


class AnnouncementPatch(Patch):
    expected_version: Version | None = None
    title: Annotated[str, Field(min_length=1, max_length=200)] | None = None
    body: Annotated[str, Field(min_length=1, max_length=20000)] | None = None
    published: StrictBool | None = None
    pinned: StrictBool | None = None
    publish_at: AwareDatetime | None = None
    category_label: Annotated[str, Field(max_length=100)] | None = None
    display_order: StrictInt | None = None

    @field_validator('publish_at', mode='before')
    @classmethod
    def empty_time(cls, value):
        return None if value == '' else value

    def nullable_fields(self):
        return ('publish_at',)


class AnnouncementCreate(AnnouncementPatch):
    competition_id: ID
    title: Annotated[str, Field(min_length=1, max_length=200)]
    body: Annotated[str, Field(min_length=1, max_length=20000)]


class StreamPatch(Patch):
    expected_version: Version | None = None
    room_url: Text | None = None
    replay_url: Text | None = None
    match_id: ID | None = None
    status: Literal['offline', 'live', 'replay'] | None = None

    @field_validator('match_id', mode='before')
    @classmethod
    def empty_match(cls, value):
        return None if value == '' else value

    def nullable_fields(self):
        return ('match_id',)


class StreamCreate(StreamPatch):
    competition_id: ID


class MediaPatch(Patch):
    logo_url: Text | None = None
    english_name: Text | None = None
    category: Annotated[str, Field(max_length=100)] | None = None
    introduction: Text | None = None
    support_description: Text | None = None
    official_url: Text | None = None
    builtin_mark_key: Text | None = None
    illustration_url: Text | None = None
    builtin_illustration_key: Text | None = None
    display_code: Text | None = None
    tagline: Text | None = None

    def nullable_fields(self):
        return ('logo_url', 'official_url', 'illustration_url')


class SponsorPatch(MediaPatch, ExpectedVersion):
    name: Annotated[str, Field(min_length=1, max_length=200)] | None = None
    active: StrictBool | None = None


class SponsorCreate(MediaPatch):
    name: Annotated[str, Field(min_length=1, max_length=200)]
    active: StrictBool = True
    data_origin: Literal['regular', 'test'] = 'regular'


class PartnerPatch(MediaPatch, ExpectedVersion):
    sponsor_id: ID | None = None
    tier: Literal['presenting', 'official'] | None = None
    published: StrictBool | None = None
    display_order: StrictInt | None = None

    def nullable_fields(self):
        return super().nullable_fields() + ('display_order',)


class PartnerCreate(PartnerPatch):
    sponsor_id: ID


class PrizePatch(MediaPatch, ExpectedVersion):
    name: Annotated[str, Field(min_length=1, max_length=200)] | None = None
    provider_partner_id: ID | None = None
    active: StrictBool | None = None
    unit: Annotated[str, Field(max_length=60)] | None = None
    description: Text | None = None
    model_code: Text | None = None
    image_url: Text | None = None
    display_order: StrictInt | None = None

    def nullable_fields(self):
        return super().nullable_fields() + ('provider_partner_id', 'image_url')


class PrizeCreate(PrizePatch):
    name: Annotated[str, Field(min_length=1, max_length=200)]
    category: Literal['equipment', 'commemorative']


class WithdrawResult(ExpectedVersion):
    reason: Reason


class AuditItem(BaseModel):
    id: str
    action: str
    entity_id: str
    payload: dict
    created_at: datetime
    actor_id: int | None
    request_id: str | None
