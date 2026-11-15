import os
from datetime import datetime, timezone
from uuid import uuid4
from sqlalchemy import create_engine, event, String, DateTime, JSON, ForeignKey, UniqueConstraint, CheckConstraint
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

class Registration(Base):
    __tablename__ = 'registrations'
    id: Mapped[str] = mapped_column(primary_key=True, default=uid)
    competition_id: Mapped[str] = mapped_column(ForeignKey('competitions.id'), index=True)
    code: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(default='')
    contact: Mapped[str] = mapped_column(String(200))
    logo: Mapped[str] = mapped_column(default='')
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
