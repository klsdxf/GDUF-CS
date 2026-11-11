import os
from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import create_engine, event, String, DateTime, JSON, ForeignKey, UniqueConstraint, CheckConstraint, ForeignKeyConstraint, Index
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker

def now():
    return datetime.now(timezone.utc)

def uid():
    return str(uuid4())

class Base(DeclarativeBase):
    pass

engine = create_engine(os.getenv('DATABASE_URL', 'sqlite:///./dev.db'), pool_pre_ping=True)
if engine.dialect.name == 'sqlite':
    @event.listens_for(engine, 'connect')
    def sqlite_fk(conn, record):
        conn.execute('PRAGMA foreign_keys=ON')
Session = sessionmaker(engine, expire_on_commit=False)

class Admin(Base):
    __tablename__ = 'admins'
    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    username: Mapped[str] = mapped_column(String(80), unique=True)
    password_hash: Mapped[str]
    __table_args__ = (CheckConstraint('id = 1'),)

class AdminSession(Base):
    __tablename__ = 'admin_sessions'
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    csrf: Mapped[str]
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

class Competition(Base):
    __tablename__ = 'competitions'
    id: Mapped[str] = mapped_column(primary_key=True, default=uid)
    slug: Mapped[str] = mapped_column(String(100), unique=True)
    name: Mapped[str]
    season: Mapped[str] = mapped_column(default='')
    organizer: Mapped[str] = mapped_column(default='学生社团赛事')
    description: Mapped[str] = mapped_column(default='')
    rules: Mapped[str] = mapped_column(default='')
    map_pool: Mapped[list] = mapped_column(JSON, default=list)
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(default='draft')
    published: Mapped[bool] = mapped_column(default=False)
    is_default: Mapped[bool] = mapped_column(default=False)
    team_limit: Mapped[int] = mapped_column(default=32)
    revision: Mapped[int] = mapped_column(default=0)
    focus_match_id: Mapped[str | None]
    data_origin: Mapped[str] = mapped_column(String(16), default='regular', server_default='regular')
    seed_batch_id: Mapped[str | None] = mapped_column(ForeignKey('seed_batches.id'))

class Registration(Base):
    __tablename__ = 'registrations'
    id: Mapped[str] = mapped_column(primary_key=True, default=uid)
    competition_id: Mapped[str] = mapped_column(ForeignKey('competitions.id'), index=True)
    code: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(default='')
    contact: Mapped[str] = mapped_column(String(200))
    logo: Mapped[str] = mapped_column(default='')
    english_name: Mapped[str] = mapped_column(String(120), default='')
    emblem_text: Mapped[str] = mapped_column(String(12), default='')
    poster_title_lines: Mapped[list] = mapped_column(JSON, default=list)
    active: Mapped[bool] = mapped_column(default=True)
    version: Mapped[int] = mapped_column(default=1)
    __table_args__ = (UniqueConstraint('competition_id', 'code'),)

class Member(Base):
    __tablename__ = 'registration_members'
    id: Mapped[str] = mapped_column(primary_key=True, default=uid)
    registration_id: Mapped[str] = mapped_column(ForeignKey('registrations.id'), index=True)
    version: Mapped[int]
    steam_id: Mapped[str] = mapped_column(String(17))
    nickname: Mapped[str] = mapped_column(String(100))
    role: Mapped[str]
    captain: Mapped[bool]
    __table_args__ = (UniqueConstraint('registration_id', 'version', 'steam_id'),)

class RosterSnapshot(Base):
    __tablename__ = 'roster_snapshots'
    registration_id: Mapped[str] = mapped_column(ForeignKey('registrations.id'), primary_key=True)
    version: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    description: Mapped[str]
    logo: Mapped[str]
    english_name: Mapped[str] = mapped_column(String(120), default='')
    emblem_text: Mapped[str] = mapped_column(String(12), default='')
    poster_title_lines: Mapped[list] = mapped_column(JSON, default=list)

class Claim(Base):
    __tablename__ = 'active_member_claims'
    competition_id: Mapped[str] = mapped_column(ForeignKey('competitions.id'), primary_key=True)
    steam_id: Mapped[str] = mapped_column(String(17), primary_key=True)
    registration_id: Mapped[str] = mapped_column(ForeignKey('registrations.id'))

class ImportBatch(Base):
    __tablename__ = 'import_batches'
    id: Mapped[str] = mapped_column(primary_key=True, default=uid)
    competition_id: Mapped[str] = mapped_column(ForeignKey('competitions.id'), index=True)
    revision: Mapped[int]
    mode: Mapped[str]
    filename: Mapped[str]
    file_hash: Mapped[str]
    payload: Mapped[dict] = mapped_column(JSON)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(default='preview')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

class Stage(Base):
    __tablename__ = 'stages'
    id: Mapped[str] = mapped_column(primary_key=True, default=uid)
    competition_id: Mapped[str] = mapped_column(ForeignKey('competitions.id'), index=True)
    name: Mapped[str]
    type: Mapped[str]
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    entries: Mapped[list] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(default='draft')
    generation_key: Mapped[str | None]

class Match(Base):
    __tablename__ = 'matches'
    id: Mapped[str] = mapped_column(primary_key=True, default=uid)
    competition_id: Mapped[str] = mapped_column(ForeignKey('competitions.id'), index=True)
    stage_id: Mapped[str] = mapped_column(ForeignKey('stages.id'), index=True)
    code: Mapped[str]
    round: Mapped[int]
    group: Mapped[str] = mapped_column(default='')
    bracket: Mapped[str] = mapped_column(default='upper')
    a: Mapped[str | None] = mapped_column(ForeignKey('registrations.id'))
    b: Mapped[str | None] = mapped_column(ForeignKey('registrations.id'))
    source_a: Mapped[str] = mapped_column(default='')
    source_b: Mapped[str] = mapped_column(default='')
    best_of: Mapped[int] = mapped_column(default=1)
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    status: Mapped[str] = mapped_column(default='unscheduled')
    published: Mapped[bool] = mapped_column(default=False)
    result: Mapped[dict] = mapped_column(JSON, default=dict)
    draft_result: Mapped[dict] = mapped_column(JSON, default=dict)
    winner: Mapped[str | None] = mapped_column(ForeignKey('registrations.id'))
    confirmed: Mapped[bool] = mapped_column(default=False)
    version: Mapped[int] = mapped_column(default=0)
    rosters: Mapped[dict] = mapped_column(JSON, default=dict)
    __table_args__ = (UniqueConstraint('stage_id', 'code'), CheckConstraint('best_of IN (1,3,5)'), CheckConstraint('a IS NULL OR b IS NULL OR a <> b'))

class Advancement(Base):
    __tablename__ = 'match_advancements'
    id: Mapped[str] = mapped_column(primary_key=True, default=uid)
    source: Mapped[str] = mapped_column(ForeignKey('matches.id'))
    outcome: Mapped[str]
    target: Mapped[str] = mapped_column(ForeignKey('matches.id'))
    slot: Mapped[str]
    __table_args__ = (UniqueConstraint('target', 'slot'),)

class Announcement(Base):
    __tablename__ = 'announcements'
    id: Mapped[str] = mapped_column(primary_key=True, default=uid)
    competition_id: Mapped[str] = mapped_column(ForeignKey('competitions.id'), index=True)
    title: Mapped[str]
    body: Mapped[str]
    published: Mapped[bool] = mapped_column(default=False)
    pinned: Mapped[bool] = mapped_column(default=False)
    publish_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    category_label: Mapped[str] = mapped_column(String(100), default='', server_default='')
    display_order: Mapped[int] = mapped_column(default=0, server_default='0')

class LiveStream(Base):
    __tablename__ = 'live_streams'
    id: Mapped[str] = mapped_column(primary_key=True, default=uid)
    competition_id: Mapped[str] = mapped_column(ForeignKey('competitions.id'), index=True)
    match_id: Mapped[str | None] = mapped_column(ForeignKey('matches.id'))
    room_url: Mapped[str]
    replay_url: Mapped[str] = mapped_column(default='')
    status: Mapped[str] = mapped_column(default='offline')

class Audit(Base):
    __tablename__ = 'audit_logs'
    id: Mapped[str] = mapped_column(primary_key=True, default=uid)
    action: Mapped[str]
    entity_id: Mapped[str]
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)

def db_session():
    with Session.begin() as session:
        yield session


class ResultPage(Base):
    __tablename__ = 'competition_result_pages'
    id: Mapped[str] = mapped_column(primary_key=True, default=uid)
    competition_id: Mapped[str] = mapped_column(ForeignKey('competitions.id'), unique=True)
    version: Mapped[int] = mapped_column(default=1)
    config: Mapped[dict] = mapped_column(JSON, default=dict)
    result_kind: Mapped[str] = mapped_column(String(16), default='official', server_default='official')
    current_release_id: Mapped[str | None] = mapped_column(ForeignKey('result_releases.id', use_alter=True, name='fk_current_release'))

class ResultPlacement(Base):
    __tablename__ = 'result_placements'
    competition_id: Mapped[str] = mapped_column(ForeignKey('competitions.id'))
    id: Mapped[str] = mapped_column(primary_key=True, default=uid)
    result_page_id: Mapped[str] = mapped_column(ForeignKey('competition_result_pages.id'))
    registration_id: Mapped[str] = mapped_column(ForeignKey('registrations.id'))
    team_display_version: Mapped[int]
    rank_from: Mapped[int]
    rank_to: Mapped[int]
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    __table_args__ = (UniqueConstraint('result_page_id','registration_id'), CheckConstraint('rank_from >= 1 AND rank_to >= rank_from AND rank_to <= 32'),)

class ResultPathMatch(Base):
    __tablename__ = 'result_path_matches'
    competition_id: Mapped[str] = mapped_column(ForeignKey('competitions.id'))
    id: Mapped[str] = mapped_column(primary_key=True, default=uid)
    result_page_id: Mapped[str] = mapped_column(ForeignKey('competition_result_pages.id'))
    match_id: Mapped[str] = mapped_column(ForeignKey('matches.id'))
    display_order: Mapped[int]
    stage_label: Mapped[str] = mapped_column(default='')
    __table_args__ = (UniqueConstraint('result_page_id','match_id'), UniqueConstraint('result_page_id','display_order'))

class Sponsor(Base):
    __tablename__ = 'sponsors'
    id: Mapped[str] = mapped_column(primary_key=True, default=uid)
    name: Mapped[str]
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    active: Mapped[bool] = mapped_column(default=True)
    version: Mapped[int] = mapped_column(default=1)
    data_origin: Mapped[str] = mapped_column(String(16), default='regular', server_default='regular')
    seed_batch_id: Mapped[str | None] = mapped_column(ForeignKey('seed_batches.id'))

class CompetitionPartner(Base):
    __tablename__ = 'competition_partners'
    id: Mapped[str] = mapped_column(primary_key=True, default=uid)
    competition_id: Mapped[str] = mapped_column(ForeignKey('competitions.id'))
    sponsor_id: Mapped[str] = mapped_column(ForeignKey('sponsors.id'))
    tier: Mapped[str] = mapped_column(default='official')
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    published: Mapped[bool] = mapped_column(default=False)
    version: Mapped[int] = mapped_column(default=1)
    __table_args__ = (UniqueConstraint('competition_id','sponsor_id'),)

class Prize(Base):
    __tablename__ = 'prizes'
    id: Mapped[str] = mapped_column(primary_key=True, default=uid)
    competition_id: Mapped[str] = mapped_column(ForeignKey('competitions.id'))
    provider_partner_id: Mapped[str | None] = mapped_column(ForeignKey('competition_partners.id'))
    name: Mapped[str]
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    active: Mapped[bool] = mapped_column(default=True)
    version: Mapped[int] = mapped_column(default=1)

class PrizeAllocation(Base):
    __tablename__ = 'prize_allocations'
    competition_id: Mapped[str] = mapped_column(ForeignKey('competitions.id'))
    id: Mapped[str] = mapped_column(primary_key=True, default=uid)
    placement_id: Mapped[str] = mapped_column(ForeignKey('result_placements.id'))
    prize_id: Mapped[str] = mapped_column(ForeignKey('prizes.id'))
    quantity: Mapped[int]
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    __table_args__ = (UniqueConstraint('placement_id','prize_id'), CheckConstraint('quantity > 0'))

class ResultRelease(Base):
    __tablename__ = 'result_releases'
    id: Mapped[str] = mapped_column(primary_key=True, default=uid)
    result_page_id: Mapped[str] = mapped_column(ForeignKey('competition_result_pages.id'))
    competition_id: Mapped[str] = mapped_column(ForeignKey('competitions.id'))
    release_number: Mapped[int]
    status: Mapped[str] = mapped_column(default='published')
    source_fingerprint: Mapped[str]
    source_dependencies: Mapped[dict] = mapped_column(JSON)
    public_snapshot: Mapped[dict] = mapped_column(JSON)
    content_sha256: Mapped[str]
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    reason: Mapped[str]
    idempotency_key: Mapped[str | None]
    result_kind: Mapped[str] = mapped_column(String(16), default='official', server_default='official')
    data_origin: Mapped[str] = mapped_column(String(16), default='regular', server_default='regular')
    invalidated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    invalidation_reason: Mapped[str] = mapped_column(default='')
    __table_args__ = (UniqueConstraint('result_page_id','release_number'), UniqueConstraint('result_page_id','idempotency_key'))

# Enforce same-edition links in the database as well as the publishing service.
for cls in (Registration,Stage,Match,ResultPage,ResultPlacement,CompetitionPartner,Prize,ResultRelease):
    cls.__table__.append_constraint(UniqueConstraint('id','competition_id'))
for cls, local, target in (
    (ResultPlacement,'result_page_id','competition_result_pages'),
    (ResultPlacement,'registration_id','registrations'),
    (ResultPathMatch,'result_page_id','competition_result_pages'),
    (ResultPathMatch,'match_id','matches'),
    (Prize,'provider_partner_id','competition_partners'),
    (PrizeAllocation,'placement_id','result_placements'),
    (PrizeAllocation,'prize_id','prizes'),
    (ResultRelease,'result_page_id','competition_result_pages')):
    cls.__table__.append_constraint(ForeignKeyConstraint([local,'competition_id'],[target+'.id',target+'.competition_id']))
ResultPlacement.__table__.append_constraint(ForeignKeyConstraint(['registration_id','team_display_version'],['roster_snapshots.registration_id','roster_snapshots.version']))

ResultRelease.__table__.append_constraint(UniqueConstraint('id','result_page_id'))
ResultPage.__table__.append_constraint(ForeignKeyConstraint(['current_release_id','id'],['result_releases.id','result_releases.result_page_id'],name='fk_release_belongs_to_page',use_alter=True))

Index('uq_presenting_partner',CompetitionPartner.competition_id,unique=True,sqlite_where=CompetitionPartner.tier=='presenting',postgresql_where=CompetitionPartner.tier=='presenting')


class SeedBatch(Base):
    __tablename__ = 'seed_batches'
    id: Mapped[str] = mapped_column(primary_key=True, default=uid)
    package_key: Mapped[str]
    package_version: Mapped[str]
    content_sha256: Mapped[str]
    idempotency_key: Mapped[str] = mapped_column(unique=True)
    manifest: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    __table_args__ = (UniqueConstraint('package_key','package_version'),)


class SeedEntity(Base):
    __tablename__ = 'seed_entities'
    id: Mapped[str] = mapped_column(primary_key=True, default=uid)
    batch_id: Mapped[str] = mapped_column(ForeignKey('seed_batches.id'), index=True)
    entity_type: Mapped[str]
    source_key: Mapped[str]
    entity_id: Mapped[str]
    imported_fingerprint: Mapped[str]
    __table_args__ = (UniqueConstraint('batch_id','entity_type','source_key'),)


class SeedPreview(Base):
    __tablename__ = 'seed_previews'
    id: Mapped[str] = mapped_column(primary_key=True, default=uid)
    package_key: Mapped[str]
    package_version: Mapped[str]
    content_sha256: Mapped[str]
    state_fingerprint: Mapped[str]
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class ResultTestMatch(Base):
    __tablename__ = 'result_test_matches'
    id: Mapped[str] = mapped_column(primary_key=True, default=lambda:'rtm-'+uid())
    competition_id: Mapped[str] = mapped_column(ForeignKey('competitions.id'), index=True)
    result_page_id: Mapped[str] = mapped_column(ForeignKey('competition_result_pages.id'), index=True)
    source_key: Mapped[str]
    a_registration_id: Mapped[str] = mapped_column(ForeignKey('registrations.id'))
    b_registration_id: Mapped[str] = mapped_column(ForeignKey('registrations.id'))
    winner_registration_id: Mapped[str] = mapped_column(ForeignKey('registrations.id'))
    a_display_version: Mapped[int]
    b_display_version: Mapped[int]
    match_kind: Mapped[str]
    label: Mapped[str]
    best_of: Mapped[int]
    wins_a: Mapped[int]
    wins_b: Mapped[int]
    maps: Mapped[list | None] = mapped_column(JSON, nullable=True)
    maps_status: Mapped[str] = mapped_column(default='not_provided')
    champion_path_order: Mapped[int | None]
    version: Mapped[int] = mapped_column(default=1)
    __table_args__ = (
        UniqueConstraint('result_page_id','source_key'),
        UniqueConstraint('result_page_id','champion_path_order'),
        CheckConstraint('best_of IN (1,3,5)'),
        CheckConstraint('a_registration_id <> b_registration_id'),
        CheckConstraint('winner_registration_id IN (a_registration_id,b_registration_id)'),
        CheckConstraint('wins_a >= 0 AND wins_b >= 0'),
        ForeignKeyConstraint(['result_page_id','competition_id'],['competition_result_pages.id','competition_result_pages.competition_id']),
    )

for field in ('a_registration_id','b_registration_id','winner_registration_id'):
    ResultTestMatch.__table__.append_constraint(ForeignKeyConstraint([field,'competition_id'],['registrations.id','registrations.competition_id']))
for side in ('a','b'):
    ResultTestMatch.__table__.append_constraint(ForeignKeyConstraint([side+'_registration_id',side+'_display_version'],['roster_snapshots.registration_id','roster_snapshots.version']))
Index('uq_test_final',ResultTestMatch.result_page_id,unique=True,sqlite_where=ResultTestMatch.match_kind=='final',postgresql_where=ResultTestMatch.match_kind=='final')
