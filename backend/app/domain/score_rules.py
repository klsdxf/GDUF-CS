from ..security import fail


def calculate(m, payload, c):
    if not m.a or not m.b:fail('TBD','双方未确定，不能录分')
    result_type=payload.get('result_type','normal')
    if result_type not in ('normal','forfeit','technical'):fail('RESULT_TYPE','无效结果类型')
    maps=payload.get('maps',[])
    if result_type!='normal':
        if payload.get('winner') not in (m.a,m.b) or not payload.get('reason'):fail('RESULT','异常结果需选择胜者并填写原因')
        if maps:fail('MAPS','弃权或技术判负不可伪造地图比分')
        return {'result_type':result_type,'maps':[],'winner':payload['winner'],'reason':payload['reason'],'wins_a':0,'wins_b':0,'complete':True}
    a=b=0;needed=m.best_of//2+1
    seen=set()
    for item in maps:
        if a==needed or b==needed:fail('MAPS','系列赛结束后不能继续追加地图')
        name=item.get('map_name')
        if name not in c.map_pool or name in seen:fail('MAP_POOL','地图不在赛事地图池中或重复')
        seen.add(name)
        x,y=item.get('score_a'),item.get('score_b')
        if type(x)!=int or type(y)!=int or min(x,y)<0 or x==y:fail('SCORE','回合数必须为非负整数且不能平局')
        if max(x,y)>13 and not item.get('overtime'):fail('OVERTIME','超过13回合请标记加时')
        if x>y:a+=1
        else:b+=1
    return {'result_type':'normal','maps':maps,'wins_a':a,'wins_b':b,'winner':m.a if a==needed else m.b if b==needed else None,'complete':a==needed or b==needed}
