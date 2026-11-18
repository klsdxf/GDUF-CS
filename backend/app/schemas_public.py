from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel


class Data[T](BaseModel):
    data: T


class PublicMember(BaseModel):
    nickname: str
    role: str
    captain: bool


class PublicTeam(BaseModel):
    id: str
    competition_id: str
    code: str
    name: str
    english_name: str
    emblem_text: str
    poster_title_lines: list[str]
    description: str
    logo: str
    members: list[PublicMember]


class PublicMatch(BaseModel):
    id: str
    competition_id: str
    stage_id: str
    code: str
    round: int
    group: str
    bracket: str
    source_a: str
    source_b: str
    best_of: int
    scheduled_at: datetime | None
    status: str
    confirmed: bool
    version: int
    label: str | None = None
    result: dict[str, Any]
    teams: list[PublicTeam | None]


class PublicTeamDetail(PublicTeam):
    matches: list[PublicMatch]


class PublicCompetition(BaseModel):
    id: str
    slug: str
    name: str
    season: str
    organizer: str
    description: str
    rules: str
    map_pool: list[str]
    status: str
    team_limit: int
    is_default: bool
    presentation: dict[str, Any]
    competition_format: str | None = None


class PublicCompetitionCount(PublicCompetition):
    team_count: int


class PublicAnnouncement(BaseModel):
    id: str
    competition_id: str
    title: str
    body: str
    published: bool
    pinned: bool
    publish_at: datetime
    category_label: str
    display_order: int


class PublicStream(BaseModel):
    id: str
    competition_id: str
    match_id: str | None
    room_url: str
    replay_url: str
    status: str


class PublicStage(BaseModel):
    id: str
    name: str
    type: str
    config: dict[str, Any]


class Standing(BaseModel):
    team_id: str
    name: str
    wins: int
    losses: int
    points: int
    map_diff: int
    round_diff: int
    head: int
    rank: int
    unresolved: bool
    group: str


class StageSummary(BaseModel):
    id: str
    name: str


class PublicHome(BaseModel):
    competition: PublicCompetition
    team_count: int
    focus: PublicMatch | None
    matches: list[PublicMatch]
    standings: list[Standing]
    stages: list[StageSummary]


class BracketEdge(BaseModel):
    id: str
    source: str
    target: str
    outcome: str
    slot: str


class ByeSource(BaseModel):
    name: str | None
    source: str


class PublicBracket(BaseModel):
    matches: list[PublicMatch]
    edges: list[BracketEdge]
    bye_sources: list[ByeSource]


class ResultEdition(PublicCompetition):
    release_id: str
    published_at: datetime


class PendingRanking(BaseModel):
    pending: Literal[True]
    competition: PublicCompetition
    partners: list[dict[str, Any]]
    prizes: list[dict[str, Any]] | None = None
    award_plan: dict[str, list[str]] | None = None
    hide_award_quantities: bool | None = None
    award_eligibility_text: str | None = None
    has_third_place: bool | None = None


class PublishedRanking(BaseModel):
    schema_version: str
    competition: PublicCompetition
    display: dict[str, Any]
    champion: dict[str, Any] | None
    placements: list[dict[str, Any]]
    final_match: dict[str, Any] | None
    champion_path: list[dict[str, Any]]
    prizes: list[dict[str, Any]]
    allocations: list[dict[str, Any]]
    partners: list[dict[str, Any]] | None = None
    presenting_partner: dict[str, Any] | None = None
    official_partners: list[dict[str, Any]] | None = None
    support_totals: dict[str, int]
    release: dict[str, Any] | None = None
    award_plan: dict[str, list[str]] | None = None
    hide_award_quantities: bool | None = None
    award_eligibility_text: str | None = None
    has_third_place: bool | None = None
