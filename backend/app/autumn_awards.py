"""Append the 2026 autumn third-place match and publish the confirmed prize plan."""
import argparse

from sqlalchemy import select

from .services import final_result_service as final_results, roster_service as roster
from .autumn_update import refresh_announcements
from .db import Advancement, CompetitionPartner, Match, Prize, Registration, Session, Sponsor, Stage


def add_third_place(db, competition, page, stage):
    matches = final_results.rows(db, Match, competition.id)
    final = db.get(Match, page.config.get('final_match_id')) if page.config.get('final_match_id') else None
    if not final or final.stage_id != stage.id or final.round != 3 or final.bracket != 'upper':
        raise ValueError('无法确认现有总决赛')
    sources = list(db.scalars(select(Advancement).where(Advancement.target == final.id).order_by(Advancement.slot)))
    semifinals = [db.get(Match, edge.source) for edge in sources]
    if (len(semifinals) != 2 or any(edge.outcome != 'winner' for edge in sources)
            or any(m.stage_id != stage.id or m.round != 2 or m.bracket != 'upper' for m in semifinals)):
        raise ValueError('无法确认两场半决赛')

    existing = [m for m in matches if m.bracket == 'third']
    if existing:
        third, = existing
        edges = list(db.scalars(select(Advancement).where(Advancement.target == third.id).order_by(Advancement.slot)))
        if (third.stage_id != stage.id or third.best_of != 3 or not third.published
                or [(e.source, e.outcome, e.slot) for e in edges] !=
                   [(m.id, 'loser', slot) for m, slot in zip(semifinals, ('a', 'b'), strict=True)]):
            raise ValueError('已有季军赛，请核对其设置和晋级来源')
        return third

    if len(matches) != 7 or any(m.stage_id != stage.id or not m.published or m.best_of != 3 for m in matches):
        raise ValueError('现有赛程与七场已发布 BO3 赛程不符')
    third = Match(
        competition_id=competition.id, stage_id=stage.id, code='THIRD1-1',
        round=final.round, bracket='third', best_of=3, published=True,
        source_a=f'{semifinals[0].code}:loser', source_b=f'{semifinals[1].code}:loser',
    )
    db.add(third)
    db.flush()
    rosters = {}
    for semi, slot in zip(semifinals, ('a', 'b'), strict=True):
        db.add(Advancement(competition_id=competition.id, source=semi.id, target=third.id, outcome='loser', slot=slot))
        if semi.confirmed:
            loser = semi.b if semi.winner == semi.a else semi.a
            setattr(third, slot, loser)
            rosters[loser] = db.get(Registration, loser).version
    third.rosters = rosters
    stage.config = {**stage.config, 'third_place': True}
    return third


def publish_prize_plan(db, competition, page):
    partners = {}
    for link in final_results.rows(db, CompetitionPartner, competition.id):
        brand = db.get(Sponsor, link.sponsor_id)
        if link.published and brand.active:
            partners[brand.data.get('english_name')] = link.id
    if not {'Trashpad', 'PunishGear'} <= partners.keys():
        raise ValueError('缺少已公开的垃圾桶外设或东莞垫神合作资料')

    definitions = (
        ('太岁 Pro 鼠标垫', 'Trashpad', '太岁 PRO', 'taisu-mousepad', '张'),
        ('东莞垫神鼠标垫', 'PunishGear', '', 'punishgear-mousepad', '张'),
        ('鼠标防滑贴', None, '', 'grip-tape', '套'),
    )
    prizes = []
    records = final_results.rows(db, Prize, competition.id)
    for index, (name, brand, model, illustration, unit) in enumerate(definitions):
        existing = next((prize for prize in records if prize.name == name), None)
        payload = {
            'expected_version': page.version, 'name': name,
            'provider_partner_id': partners.get(brand), 'unit': unit, 'category': 'equipment',
            'model_code': model, 'builtin_illustration_key': illustration, 'display_order': index,
        }
        if existing and existing.active and existing.provider_partner_id == payload['provider_partner_id'] and all(
            existing.data.get(key) == payload[key] for key in ('unit', 'category', 'model_code', 'builtin_illustration_key', 'display_order')
        ):
            prizes.append(existing.id)
        else:
            if existing:
                payload = {**existing.data, **payload}
            prizes.append(final_results.save_entity(db, competition, page, payload, Prize, existing)['data']['id'])
    champion, runner, grip = prizes
    return {'1': [champion, grip], '2': [runner, grip], '3': [runner, grip], '4': [grip]}


def update_awards(db):
    competition, page = final_results.page(db, 'autumn')
    if (competition.season != '2026' or competition.data_origin != 'regular'
            or not competition.published or competition.status not in ('scheduling', 'ongoing')
            or not competition.config.get('show_pending_results') or page.result_kind != 'official'
            or page.current_release_id or final_results.placements(db, page)):
        raise ValueError('秋季赛不在可增补季军赛和奖品方案的阶段')
    stage = db.get(Stage, page.config.get('final_stage_id')) if page.config.get('final_stage_id') else None
    if not stage or stage.competition_id != competition.id or stage.type != 'single' or stage.status != 'published':
        raise ValueError('无法确认已发布的单败阶段')
    third = add_third_place(db, competition, page, stage)
    plan = publish_prize_plan(db, competition, page)
    config = {**page.config, 'third_place_match_id': third.id, 'award_plan': plan}
    if page.config != config:
        final_results.bump(db, page, page.version)
        page.config = config
        competition.revision += 1
        roster.audit(db, 'competition.autumn_awards', competition.id, {'third_place_match_id': third.id})
    rule = '两支半决赛落败队进行 BO3 季军赛，胜者为第三名，负者为第四名。'
    if rule not in competition.rules:
        competition.rules = competition.rules.replace('\n\n03　地图池', rule + '\n\n03　地图池', 1) if '\n\n03　地图池' in competition.rules else competition.rules + '\n\n' + rule
    refresh_announcements(db, competition)
    db.flush()
    return third.id


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true', help='保存更新，默认预演并回滚')
    args = parser.parse_args()
    try:
        with Session() as db:
            update_awards(db)
            db.commit() if args.apply else db.rollback()
    except ValueError as exc:
        parser.exit(1, f'{exc}\n')
    print(f'{"已保存" if args.apply else "预演通过"}：8 场 BO3，已增补季军赛及四强奖品方案')


if __name__ == '__main__':
    main()
