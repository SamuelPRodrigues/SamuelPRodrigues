(()=>{
const $=s=>document.querySelector(s);
const N=v=>Number(v)||0;
const E=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const TL=t=>({climate:'Clima',road:'Rodovias',operational:'Operacional'}[String(t||'').toLowerCase()]||'Outros');
const st=x=>String(x.source_type||x.type||'').toLowerCase();
const risk=x=>N(x.risk);
const dateOf=x=>new Date(x.snapshot_at||x.updated_at||x.updatedAt||x.createdAt||x.time||0);
const eventTime=x=>x.snapshot_at||x.updated_at||x.updatedAt||x.createdAt||x.time||'';
const fmt=v=>{const d=new Date(v||0);return isNaN(d)?'sem horário':d.toLocaleString('pt-BR',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'})};
const bucket=x=>x.snapshot_bucket||x.snapshotBucket||(isNaN(dateOf(x))?'sem-bucket':dateOf(x).toISOString().slice(0,16));
const dur=h=>{const m=Math.max(0,Math.round(N(h)*60));const hh=Math.floor(m/60),mm=m%60;return hh?`${hh}h${String(mm).padStart(2,'0')}`:`${mm}min`};
function reg(x){if(x.region)return String(x.region);const u=String(x.state||'').toUpperCase();const m={AC:'Norte',AM:'Norte',AP:'Norte',PA:'Norte',RO:'Norte',RR:'Norte',TO:'Norte',AL:'Nordeste',BA:'Nordeste',CE:'Nordeste',MA:'Nordeste',PB:'Nordeste',PE:'Nordeste',PI:'Nordeste',RN:'Nordeste',SE:'Nordeste',DF:'Centro-Oeste',GO:'Centro-Oeste',MT:'Centro-Oeste',MS:'Centro-Oeste',ES:'Sudeste',MG:'Sudeste',RJ:'Sudeste',SP:'Sudeste',PR:'Sul',RS:'Sul',SC:'Sul'};return m[u]||'Sem região'}
async function j(p){for(const u of [p,'https://raw.githubusercontent.com/SamuelPRodrigues/SamuelPRodrigues/main/'+p])try{const r=await fetch(u+(u.includes('?')?'&':'?')+'hotfix='+Date.now(),{cache:'no-store'});if(r.ok)return await r.json()}catch(e){}return null}
async function rows(){const c=await j('data/analytics_cache.json');if(c&&Array.isArray(c.rows))return c.rows;return []}
function activeRows(all){
  const d=N($('.db-tab.active')?.dataset?.d||30),cut=Date.now()-d*864e5;
  let out=all.filter(x=>!d||isNaN(dateOf(x))||dateOf(x).getTime()>=cut);
  const chip=$('.db-chip.active')?.dataset?.t||'all';
  if(chip==='high')out=out.filter(x=>risk(x)>=60);else if(chip!=='all')out=out.filter(x=>st(x)===chip);
  const q=($('#dbSearch')?.value||'').trim().toLowerCase();
  if(q)out=out.filter(x=>[x.name,x.event_type,x.eventType,x.city,x.state,reg(x),x.road,x.description,x.source].join(' ').toLowerCase().includes(q));
  return out;
}
function persistence(a){
  const g={};
  a.filter(x=>st(x)==='road').forEach(x=>{const d=dateOf(x);if(isNaN(d))return;const k=x.stable_event_id||x.road||x.name||'Rodovia';g[k]??={name:x.road||x.name||'Rodovia',count:0,buckets:new Set(),first:d,last:d,maxRisk:0};g[k].count++;g[k].buckets.add(bucket(x));if(d<g[k].first)g[k].first=d;if(d>g[k].last)g[k].last=d;g[k].maxRisk=Math.max(g[k].maxRisk,risk(x))});
  return Object.values(g).map(x=>{const snapshots=Math.max(1,x.buckets.size);return {...x,snapshots,hours:Math.round(snapshots*0.25*10)/10}}).sort((a,b)=>b.hours-a.hours||b.maxRisk-a.maxRisk).slice(0,5);
}
async function apply(){
  const modal=$('#dbModal');if(!modal||!modal.classList.contains('open'))return;
  const data=activeRows(await rows());
  const top=data.slice().sort((a,b)=>risk(b)-risk(a)).slice(0,5);
  const topEl=$('#dbTop');
  if(topEl)topEl.innerHTML=top.length?top.map(x=>`<div class="db-event"><b>${risk(x)} • ${E(x.name||x.event_type||x.eventType||'Evento')}</b><span>${E(TL(st(x)))} • ${E(reg(x))}${x.road?' • '+E(x.road):''}</span><span>Adicionado: ${E(fmt(eventTime(x)))}</span></div>`).join(''):'<div class="db-empty">Sem eventos</div>';
  const roads=persistence(data),roadEl=$('#dbRoads');
  if(roadEl)roadEl.innerHTML=roads.length?roads.map(x=>`<div class="db-event"><b>${E(x.name)}</b><span>${dur(x.hours)} estimados • ${x.snapshots} snapshot(s) de 15min • ${x.count} registro(s) • risco máx. ${x.maxRisk}</span><span>Primeiro: ${fmt(x.first)} • último: ${fmt(x.last)}</span></div>`).join(''):'<div class="db-empty">Sem dados rodoviários</div>';
}
setInterval(apply,1200);
document.addEventListener('click',()=>setTimeout(apply,350));
})();
