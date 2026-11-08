"""100 concurrent visitors with one-second think time; default duration 600s."""
import argparse
import asyncio
import json
import math
import time
import httpx

parser=argparse.ArgumentParser()
parser.add_argument('--url',default='http://127.0.0.1:8000')
parser.add_argument('--duration',type=int,default=600)
parser.add_argument('--users',type=int,default=100)
parser.add_argument('--output',default='load-report.json')
args=parser.parse_args()

async def main():
    times=[];errors=[];counts={};start=time.perf_counter()
    async with httpx.AsyncClient(base_url=args.url,limits=httpx.Limits(max_connections=args.users+5),timeout=10) as client:
        comps=(await client.get('/api/v1/competitions')).json()['data']
        if not comps:raise SystemExit('需要独立验收赛事数据')
        key=comps[0]['slug'];prefix='/api/v1/competitions/'+key
        matches=(await client.get(prefix+'/matches')).json()['data']
        paths=[prefix+'/home',prefix,prefix+'/teams',prefix+'/matches','/api/v1/matches/'+matches[0]['id']]
        async def visitor(index):
            cursor=index
            while time.perf_counter()-start<args.duration:
                path=paths[cursor%len(paths)];cursor+=1;t=time.perf_counter()
                try:
                    response=await client.get(path);times.append(time.perf_counter()-t)
                    counts[response.status_code]=counts.get(response.status_code,0)+1
                    if response.status_code>=500:errors.append(response.status_code)
                except httpx.HTTPError as e:errors.append(type(e).__name__)
                await asyncio.sleep(1)
        await asyncio.gather(*(visitor(i) for i in range(args.users)))
    times.sort();report={'environment':'local acceptance dataset; SQLite unless DATABASE_URL configured','duration_seconds':round(time.perf_counter()-start,2),'users':args.users,'think_time_seconds':1,'samples':len(times),'status_counts':counts,'errors':len(errors),'p95_ms':round(times[min(len(times)-1,math.ceil(len(times)*.95)-1)]*1000,2),'max_ms':round(max(times)*1000,2)}
    report['passed']=report['p95_ms']<=2000 and report['errors']/max(len(times),1)<.01
    with open(args.output,'w',encoding='utf-8') as f:json.dump(report,f,ensure_ascii=False,indent=2)
    print(json.dumps(report,ensure_ascii=False))
asyncio.run(main())
