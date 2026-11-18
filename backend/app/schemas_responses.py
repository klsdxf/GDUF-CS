from datetime import datetime
from typing import Any

from pydantic import BaseModel

from .schemas_public import PublicAnnouncement, PublicStream


class CompetitionRecord(BaseModel):
    id: str
    slug: str
    name: str
    season: str
    organizer: str
    description: str
    rules: str
    map_pool: list[str]
    config: dict[str, Any]
    status: str
    published: bool
    is_default: bool
    team_limit: int
    revision: int
    version: int
    focus_match_id: str | None
    data_origin: str
    seed_batch_id: str | None


class StageRecord(BaseModel):
    id: str
    competition_id: str
    name: str
    type: str
    config: dict[str, Any]
    entries: list[str]
    status: str
    generation_key: str | None
    version: int


class MatchRecord(BaseModel):
    id: str
    competition_id: str
    stage_id: str
    code: str
    round: int
    group: str
    bracket: str
    a: str | None
    b: str | None
    source_a: str
    source_b: str
    best_of: int
    scheduled_at: datetime | None
    status: str
    published: bool
    result: dict[str, Any]
    draft_result: dict[str, Any]
    winner: str | None
    confirmed: bool
    version: int
    rosters: dict[str, int]


class SchedulePreview(BaseModel):
    id: str
    matches: list[MatchRecord]


class AnnouncementRecord(PublicAnnouncement):
    version: int


class StreamRecord(PublicStream):
    version: int


class SessionData(BaseModel):
    username: str
    csrf: str


class ApiError(BaseModel):
    code: str
    message: str
    details: dict[str, Any] | list[Any]
    request_id: str


class ErrorEnvelope(BaseModel):
    error: ApiError
