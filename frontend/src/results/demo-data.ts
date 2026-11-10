import fixture from './demo-v6.json'
import type {ResultDTO} from './render'
export function demoData():ResultDTO{
 const placements=fixture.placements.map(p=>({...p,registration_id:p.team_id,team:{...p}}))
 const matches=fixture.champion_path.map(m=>({...m,result_type:'normal',teams:[m.a_team_id,m.b_team_id].map(id=>({...placements.find(p=>p.team_id===id)!.team,id}))}))
 return {schema_version:'1.0',competition:fixture.competition,display:fixture.display,champion:placements[0]!.team,placements,champion_path:matches,final_match:matches.find(m=>m.id===fixture.final_match_id),prizes:fixture.prizes,allocations:fixture.allocations.map(a=>({...a,registration_id:a.team_id,placement_id:placements.find(p=>p.team_id===a.team_id)!.id})),presenting_partner:fixture.partners[0],official_partners:fixture.partners.slice(1),support_totals:fixture.support_totals}
}
