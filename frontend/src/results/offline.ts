/** Serialized into the offline HTML; intentionally has no application dependencies. */
export function offlineRuntime(views:string[],info:Record<string,{title:string;body:string}>){
 const main=document.querySelector('main')!,dialog=document.querySelector('dialog')! as HTMLDialogElement
 let opener:HTMLElement|null=null
 document.addEventListener('click',ev=>{
  const b=(ev.target as HTMLElement).closest<HTMLElement>('button');if(!b)return
  if(b.dataset.award!==undefined){main.innerHTML=views[Number(b.dataset.award)]!;main.querySelector<HTMLElement>('#award-tab-'+b.dataset.award)?.focus();return}
  if(b.hasAttribute('data-close')){dialog.close();return}
  const key=b.dataset.match?'match:'+b.dataset.match:b.dataset.prize?'prize:'+b.dataset.prize:b.dataset.dialog||''
  const d=info[key];if(d){opener=b;dialog.querySelector('[data-title]')!.textContent=d.title;dialog.querySelector('[data-body]')!.innerHTML=d.body;dialog.showModal()}
 })
 document.addEventListener('input',ev=>{const input=ev.target as HTMLInputElement;if(input.id!=='search')return;let n=0;main.querySelectorAll<HTMLElement>('[data-team]').forEach(r=>{r.hidden=!r.dataset.team!.toLowerCase().includes(input.value.toLowerCase());if(!r.hidden)n++});main.querySelector('#team-count')!.textContent='找到 '+n+' 支队伍';main.querySelector<HTMLElement>('#empty')!.hidden=n>0})
 document.addEventListener('keydown',ev=>{const t=ev.target as HTMLElement;if(!t.matches('[data-award]'))return;const tabs=Array.from(main.querySelectorAll<HTMLElement>('[data-award]'));let i=tabs.indexOf(t);if(ev.key==='Home')i=0;else if(ev.key==='End')i=tabs.length-1;else if(ev.key==='ArrowLeft')i=(i+tabs.length-1)%tabs.length;else if(ev.key==='ArrowRight')i=(i+1)%tabs.length;else return;ev.preventDefault();tabs[i]?.click()})
 dialog.addEventListener('close',()=>opener?.focus())
 dialog.addEventListener('click',ev=>{if(ev.target===dialog){const r=dialog.getBoundingClientRect();if(ev.clientX<r.left||ev.clientX>r.right||ev.clientY<r.top||ev.clientY>r.bottom)dialog.close()}})
}
