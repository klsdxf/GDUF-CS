import math

from itertools import combinations

from ..security import fail

def seed_order(size):
    order=[1,2]
    while len(order)<size:
        total=len(order)*2+1
        order=[v for seed in order for v in (seed,total-seed)]
    return order

def generate_graph(entries,kind,config):
    nodes,edges=[],[]
    bo=int(config.get('best_of',1))
    if bo not in (1,3,5): fail('BO','BO仅允许1、3、5')
    def game(a,b,bracket,rnd,group=''):
        if a is None: return b,None
        if b is None: return a,None
        code=f'{bracket.upper()}{rnd}-{sum(n["bracket"]==bracket and n["round"]==rnd for n in nodes)+1}'
        node={'code':code,'a':None,'b':None,'source_a':'','source_b':'','round':rnd,'bracket':bracket,'group':group,'best_of':bo}
        for slot,ref in [('a',a),('b',b)]:
            if isinstance(ref,tuple):
                node['source_'+slot]=f'{ref[0]}:{ref[1]}'
                edges.append({'source':ref[0],'outcome':ref[1],'target':code,'slot':slot})
            elif isinstance(ref,str) and ref.startswith('group:'):
                node['source_'+slot]=ref
            else: node[slot]=ref
        nodes.append(node)
        return (code,'winner'),(code,'loser')
    def knockout(values,bracket='upper'):
        size=2**math.ceil(math.log2(max(2,len(values))))
        current=[values[s-1] if s<=len(values) else None for s in seed_order(size)]
        rounds=[]
        for rnd in range(1,int(math.log2(size))+1):
            winners,losers=[],[]
            for i in range(0,len(current),2):
                w,l=game(current[i],current[i+1],bracket,rnd)
                winners.append(w);losers.append(l)
            rounds.append(losers);current=winners
        return current[0],rounds
    if kind=='group_single':
        count=int(config.get('groups',4)); qualify=int(config.get('qualify',2))
        if count<1 or count>len(entries)//2 or qualify<1 or qualify>len(entries)//count:
            fail('GROUPS','分组数、晋级数不适用于当前参赛数量')
        groups=[entries[i::count] for i in range(count)]
        manual=config.get('manual_groups')
        if manual is not None:
            if (not isinstance(manual,list) or len(manual)!=count
                or any(not isinstance(g,list) or len(g)<max(2,qualify)
                       or any(not isinstance(t,str) for t in g) for g in manual)):
                fail('GROUPS','手动分组须符合组数，每组至少两队且能填满晋级位')
            if sorted(x for g in manual for x in g)!=sorted(entries): fail('GROUPS','手动分组须包含全部队伍且不得重复')
            groups=manual;count=len(groups)
        for idx,group in enumerate(groups):
            label=chr(65+idx)
            for rnd in range(1,3 if config.get('double_round') else 2):
                for a,b in combinations(group,2):
                    game(a,b,'group'+label,rnd,label)
        qualifiers=[f'group:{chr(65+g)}:{rank}' for rank in range(1,qualify+1) for g in range(count)]
        if config.get('qualifier_order'):
            if set(config['qualifier_order'])!=set(qualifiers) or len(config['qualifier_order'])!=len(qualifiers):fail('QUALIFIERS','跨组种子必须完整且不重复')
            qualifiers=config['qualifier_order']
        _,playoff_rounds=knockout(qualifiers,'playoff')
        if config.get('third_place') and len(playoff_rounds)>=2:game(*playoff_rounds[-2],'third',1)
    else:
        upper,rounds=knockout(entries)
        if config.get('third_place') and len(rounds)>=2:
            game(*rounds[-2], 'third',1)
        if kind=='double':
            if 'grand_final_reset' not in config: fail('RESET_RULE','双败总决赛必须明确是否重置')
            lower=rounds[0]
            lr=1
            lower=[game(lower[i],lower[i+1],'lower',lr)[0] for i in range(0,len(lower),2)] if len(lower)>1 else lower
            for drops in rounds[1:]:
                lr+=1
                drops=list(reversed(drops))
                lower=[game(lower[i],drops[i],'lower',lr)[0] for i in range(len(drops))]
                if len(lower)>1:
                    lr+=1
                    lower=[game(lower[i],lower[i+1],'lower',lr)[0] for i in range(0,len(lower),2)]
            final,_=game(upper,lower[0],'final',1)
            if config['grand_final_reset']:
                game((final[0],'winner'),(final[0],'loser'),'reset',1)
    return nodes,edges
