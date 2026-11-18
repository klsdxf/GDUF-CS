"""Load the 2026 autumn bracket from the organizer's private signup workbook."""
import argparse
import hashlib
import io
import json
import os
import sys
from datetime import timezone
from pathlib import Path
from zipfile import BadZipFile, ZipFile
from zoneinfo import ZoneInfo

from openpyxl import load_workbook
from PIL import Image
from sqlalchemy import delete, or_, select

from . import content
from .services import final_result_service as final_results, roster_service as roster
from .infrastructure.outbox import mark_public_change
from .services import schedule_service as tournaments
from .domain.brackets import seed_order
from .db import (
    Advancement, Announcement, CompetitionPartner, LiveStream, Match,
    Prize, Registration, ResultPage, ResultPathMatch,
    ResultTestMatch, RosterSnapshot, SeedBatch, SeedEntity,
    Session, Sponsor, Stage,
)


QUARTERFINALS = (
    (7, 2, '2026-11-21T14:00:00+08:00'),
    (4, 1, '2026-11-21T19:00:00+08:00'),
    (9, 6, '2026-11-22T14:00:00+08:00'),
    (3, 5, '2026-11-22T19:00:00+08:00'),
)
CONFIRMED_PARTNERS = (
    ('PunishGear', '东莞垫神'),
    ('Trashpad', '垃圾桶外设'),
)
TEAM_NUMBERS = {number for pair in QUARTERFINALS for number in pair[:2]}
MAX_PACKAGE_BYTES = 8 * 1024 * 1024


def load_teams(workbook):
    sheet = load_workbook(workbook, data_only=True).worksheets[0]
    starts = [row for row in range(1, sheet.max_row + 1)
              if sheet.cell(row, 4).value == '队长']
    teams = {}
    used_logos = set()
    for number, row in enumerate(starts, 1):
        # Column E indicates whether this signup block is filled. It is never imported.
        if not sheet.cell(row, 5).value:
            continue
        name = str(sheet.cell(row, 2).value or '').strip()
        if not name or len(name) > 100 or any(t[0] == name for t in teams.values()):
            raise ValueError(f'报名表第 {row} 行队名为空、过长或重复')
        logos = [i for i in sheet._images
                 if i.anchor._from.col == 11 and i.anchor._from.row + 1 in (row - 1, row)]
        if len(logos) > 1:
            raise ValueError(f'报名表第 {row} 行有多个队标')
        logo = None
        if logos:
            used_logos.add(id(logos[0]))
            with Image.open(io.BytesIO(logos[0]._data())) as image:
                if max(image.size) > 4096:
                    raise ValueError(f'报名表第 {row} 行队标超过 4096 像素')
                encoded = io.BytesIO()
                image.convert('RGBA').save(encoded, format='WEBP')
                logo = encoded.getvalue()
        teams[number] = name, logo
    if set(teams) != TEAM_NUMBERS or len(used_logos) != len(sheet._images) or len(used_logos) != 3:
        raise ValueError('报名队伍编号或队标位置与确认的八队三队标不符')
    return teams


def load_public_team_package(raw):
    """Read the release archive containing only public team names and badges."""
    if len(raw) > MAX_PACKAGE_BYTES:
        raise ValueError('战队资料包超过大小限制')
    try:
        with ZipFile(io.BytesIO(raw)) as package:
            files = package.infolist()
            if len(files) != 4 or sum(f.file_size for f in files) > MAX_PACKAGE_BYTES:
                raise ValueError('战队资料包内容或大小不符')
            manifest = json.loads(package.read('teams.json'))
            if manifest.get('edition') != 'autumn-2026' or set(manifest) != {'edition', 'teams'}:
                raise ValueError('战队资料包赛事标识不符')
            teams = {}
            used = {'teams.json'}
            for entry in manifest['teams']:
                if set(entry) != {'number', 'name', 'logo'}:
                    raise ValueError('战队资料包有未识别字段')
                number, name, logo = (entry[key] for key in ('number', 'name', 'logo'))
                if type(number) is not int or number in teams or not isinstance(name, str) or not name.strip() or len(name) > 100:
                    raise ValueError('战队编号或名称无效')
                image = None
                if logo is not None:
                    if logo != f'logos/{number}.webp':
                        raise ValueError('队标文件名不符')
                    image = package.read(logo)
                    with Image.open(io.BytesIO(image)) as badge:
                        if badge.format != 'WEBP' or max(badge.size) > 4096:
                            raise ValueError('队标须为 4096 像素以内的 WebP')
                        badge.verify()
                    used.add(logo)
                teams[number] = name.strip(), image
            if set(teams) != TEAM_NUMBERS or len(used) != 4 or set(package.namelist()) != used:
                raise ValueError('战队资料包须包含确认的八队及三个队标')
            if len({name for name, _ in teams.values()}) != len(teams):
                raise ValueError('战队名称重复')
            return teams
    except (BadZipFile, KeyError, AttributeError, TypeError, OSError) as exc:
        raise ValueError('无法读取战队资料包') from exc


def retire_examples(db, competition):
    mark_public_change(db)
    groups = {}
    if competition.seed_batch_id:
        batch = db.get(SeedBatch, competition.seed_batch_id)
        if not batch or (batch.package_key, batch.package_version) != ('public-test', '1'):
            raise ValueError('秋季赛的示例批次无法识别')
        for item in db.scalars(select(SeedEntity).where(SeedEntity.batch_id == batch.id)):
            groups.setdefault(item.entity_type, set()).add(item.entity_id)

    def records(model):
        return list(db.scalars(select(model).where(model.competition_id == competition.id)))

    teams = [t for t in records(Registration) if t.active]
    stages = records(Stage)
    if any(t.id not in groups.get('team', ()) for t in teams) or any(
        s.id not in groups.get('stage', ()) for s in stages
    ):
        raise ValueError('秋季赛已有非示例战队或赛程，请先核对现有资料')

    page = db.scalar(select(ResultPage).where(ResultPage.competition_id == competition.id))
    if page and page.result_kind != 'test':
        raise ValueError('秋季赛已有正式排名工作稿，请先核对')
    if page:
        # Flush the status transition first so the release invalidation hook sees the old release.
        db.flush()
        final_results.replace_placements(db, competition, page, [])
        for model in (ResultPathMatch, ResultTestMatch):
            db.execute(delete(model).where(model.result_page_id == page.id))
        page.result_kind = 'official'
        page.version += 1

    match_ids = [m.id for m in records(Match)]
    if match_ids:
        if any(stream.match_id in match_ids for stream in records(LiveStream)):
            raise ValueError('旧赛程已有直播或回放关联，请先核对')
        db.execute(delete(Advancement).where(or_(Advancement.source.in_(match_ids),
                                                 Advancement.target.in_(match_ids))))
        db.execute(delete(Match).where(Match.id.in_(match_ids)))
    for stage in stages:
        db.delete(stage)
    for team in teams:
        roster.withdraw_registration(team.id, db)
    for item in records(Prize):
        if item.id in groups.get('prize', ()):
            item.active = False
    return page


def refresh_announcements(db, competition):
    if not competition.seed_batch_id:
        return
    records = {
        item.source_key: db.get(Announcement, item.entity_id)
        for item in db.scalars(select(SeedEntity).where(
            SeedEntity.batch_id == competition.seed_batch_id,
            SeedEntity.entity_type == 'announcement',
        ))
    }
    matches = db.scalars(select(Match).where(
        Match.competition_id == competition.id, Match.published == True, Match.round == 1,
        Match.bracket == 'upper', Match.scheduled_at.is_not(None),
    ).order_by(Match.scheduled_at))
    times = []
    for match in matches:
        kickoff = match.scheduled_at
        if kickoff.tzinfo is None:
            kickoff = kickoff.replace(tzinfo=timezone.utc)
        local = kickoff.astimezone(ZoneInfo('Asia/Shanghai'))
        a, b = (db.get(Registration, team_id).name for team_id in (match.a, match.b))
        times.append(f'{local.month} 月 {local.day} 日 {local:%H:%M}　{a} vs {b}')
    has_third_place = db.scalar(select(Match.id).where(
        Match.competition_id == competition.id, Match.published == True, Match.bracket == 'third',
    ).limit(1))
    later_rounds = '半决赛、季军赛和决赛' if has_third_place else '半决赛和决赛'
    third_place_rule = '两支半决赛落败队进行 BO3 季军赛，胜者为第三名，负者为第四名。' if has_third_place else ''
    updates = {
        'news-0': (
            '秋季赛首轮赛程安排',
            '秋季赛于 11 月 21 日至 30 日举行。首轮四场比赛安排如下（北京时间）。\n\n'
            + '\n'.join(times)
            + f'\n\n全程 BO3。{later_rounds}的开赛时间以赛程页为准。',
        ),
        'news-1': (
            '2026 秋季赛参赛名单公示',
            '本届秋季赛共有 8 支战队。参赛战队及队标已在「参赛战队」页面公布，队员名单待公布。',
        ),
        'news-2': (
            '竞赛规则与地图池说明',
            '本届采用 8 队单败淘汰制。四分之一决赛、半决赛和决赛均为 BO3，'
            '率先赢得两张地图的队伍赢得该场比赛，决赛胜者获得冠军。' + third_place_rule + '\n\n'
            '地图池为 ' + '、'.join(competition.map_pool) + '。完整规则见本届赛事规则页。',
        ),
    }
    for key, (title, body) in updates.items():
        announcement = records.get(key)
        if announcement and announcement.competition_id == competition.id:
            if (announcement.title, announcement.body, announcement.published) != (title, body, True):
                content.announcement_save(db, announcement, {'title': title, 'body': body, 'published': True})


def refresh_partners(db, competition, page):
    links = final_results.rows(db, CompetitionPartner, competition.id)
    linked = {link.sponsor_id: link for link in links}
    sponsors = list(db.scalars(select(Sponsor).order_by(Sponsor.id)))
    sponsors.sort(key=lambda sponsor: sponsor.id not in linked)
    kept = set()
    for order, (english, name) in enumerate(CONFIRMED_PARTNERS, 1):
        sponsor = next((s for s in sponsors if s.name == name
                        or str(s.data.get('english_name', '')).casefold() == english.casefold()), None)
        if not sponsor:
            data = final_results.insert_sponsor({'name': name, 'english_name': english}, db)
            sponsor = db.get(Sponsor, data['data']['id'])
        elif not sponsor.active or sponsor.name != name or sponsor.data.get('english_name') != english:
            final_results.update_sponsor(sponsor.id, {
                'expected_version': sponsor.version, 'name': name, 'english_name': english, 'active': True,
            }, db)
        link = linked.get(sponsor.id)
        if not link or not link.published or link.tier != 'official' or final_results.partner_order(link) != order:
            final_results.save_entity(db, competition, page, {
                **(link.data if link else {}), 'expected_version': page.version, 'sponsor_id': sponsor.id,
                'display_order': order, 'published': True, 'tier': 'official',
            }, CompetitionPartner, link)
        kept.add(sponsor.id)
    for link in links:
        if link.sponsor_id not in kept and link.published:
            final_results.save_entity(db, competition, page, {
                **link.data, 'expected_version': page.version, 'sponsor_id': link.sponsor_id, 'published': False,
            }, CompetitionPartner, link)


def update_autumn(db, teams):
    competition = roster.competition(db, 'autumn', True)
    if competition.season != '2026' or competition.config.get('show_pending_results'):
        raise ValueError('目标不是待更新的 2026 秋季赛，或此更新已应用')
    if not competition.published:
        raise ValueError('秋季赛尚未公开，请先核对赛事资料')
    config = {
        **competition.config,
        'show_pending_results': True,
        'competition_format': 'single',
        'require_prize_allocations': False,
    }
    config['presentation'] = {
        **config.get('presentation', {}),
        'starts_on': '2026-11-21',
        'ends_on': '2026-11-30',
        'date_label': '11.21 — 11.30',
    }
    # Retain the existing map pool and any map/result rules from the current edition.
    _, _, remaining = competition.rules.partition('03　地图池')
    rules = (
        '01　参赛名单\n每队 5 名正式成员，可设置替补。\n\n'
        '02　赛制与晋级\n8 支队伍进行单败淘汰。四分之一决赛、半决赛和决赛均为 BO3，'
        '双方先赢两张地图者获胜。胜者晋级，决赛胜者获得冠军。'
        + ('\n\n03　地图池' + remaining if remaining else '')
    )
    roster.update_competition(competition.id, {
        'config': config, 'status': 'scheduling', 'team_limit': 8,
        'focus_match_id': None, 'rules': rules, 'is_default': True,
    }, db)
    competition.data_origin = 'regular'
    page = retire_examples(db, competition)

    ids, media = {}, {}
    for number, (name, image) in teams.items():
        filename = hashlib.sha256(image).hexdigest() + '.webp' if image else ''
        if image:
            media[filename] = image
        team = Registration(
            competition_id=competition.id, code=f'AUT26-{number:02d}', name=name,
            contact='', logo=f'/media/{filename}' if filename else '',
            emblem_text='' if filename else 'G/',
        )
        db.add(team)
        db.flush()
        db.add(RosterSnapshot(
            registration_id=team.id, version=team.version, name=name,
            logo=team.logo, description=team.description, emblem_text=team.emblem_text,
        ))
        ids[number] = team.id

    stage = tournaments.create_stage({
        'competition_id': competition.id, 'name': '单败淘汰赛', 'type': 'single',
        'config': {'best_of': 3, 'third_place': False},
    }, db)['data']['id']
    entries = [None] * len(ids)
    match_order = [ids[number] for pair in QUARTERFINALS for number in pair[:2]]
    for seed, team_id in zip(seed_order(len(ids)), match_order, strict=True):
        entries[seed - 1] = team_id
    tournaments.entries(stage, {'entries': entries}, db)
    matches = tournaments.generate_schedule(db, stage, {'idempotency_key': 'autumn-2026-registration'})['data']['matches']
    first_round = [m for m in matches if m['round'] == 1]
    for match, (a, b, start) in zip(first_round, QUARTERFINALS, strict=True):
        if (match['a'], match['b']) != (ids[a], ids[b]):
            raise RuntimeError('首轮对阵和确认顺序不一致')
        tournaments.arrange(match['id'], {'scheduled_at': start, 'status': 'scheduled'}, db)
    tournaments.publish_schedule(db, stage)
    refresh_announcements(db, competition)
    final = next(m for m in matches if m['round'] == 3)
    if not page:
        _, page = final_results.page(db, competition.id, create=True)
    page.config = {
        'ranking_method': 'single', 'final_stage_id': stage, 'final_match_id': final['id'],
        'display_meta': {'edition_label': competition.name, 'seal_edition_label': 'FALL 2026'},
        'seal_mode': 'monogram',
    }
    refresh_partners(db, competition, page)
    competition.revision += 1
    roster.audit(db, 'competition.autumn_update', competition.id,
                 {'teams': len(ids), 'matches': len(matches), 'scheduled': len(first_round)})
    db.flush()
    return media


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('workbook', nargs='?', type=Path)
    parser.add_argument('--package-stdin', action='store_true', help='从标准输入读入公开战队资料包')
    parser.add_argument('--apply', action='store_true', help='保存更新，默认预演并回滚')
    args = parser.parse_args()
    if args.package_stdin == (args.workbook is not None):
        parser.error('请选择一个报名表文件或指定 --package-stdin')
    try:
        teams = load_public_team_package(sys.stdin.buffer.read(MAX_PACKAGE_BYTES + 1)) if args.package_stdin else load_teams(args.workbook)
        with Session() as db:
            media = update_autumn(db, teams)
            if args.apply:
                directory = Path(os.getenv('MEDIA_DIR', 'storage/media'))
                directory.mkdir(parents=True, exist_ok=True)
                for name, data in media.items():
                    destination = directory / name
                    if not destination.exists():
                        temporary = destination.with_suffix('.tmp')
                        temporary.write_bytes(data)
                        temporary.replace(destination)
                db.commit()
            else:
                db.rollback()
    except ValueError as exc:
        parser.exit(1, f'{exc}\n')
    print(f'{"已保存" if args.apply else "预演通过"}：8 支队伍、3 个队标、7 场 BO3（4 场已安排）')


if __name__ == '__main__':
    main()
