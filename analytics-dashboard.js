(()=>{
const $=s=>document.querySelector(s),$$=s=>[...document.querySelectorAll(s)];
const N=v=>Number(v)||0;
const E=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const TL=t=>({climate:'Clima',road:'Rodovias',operational:'Operacional'}[String(t||'').toLowerCase()]||'Outros');
let cache=null,days=30,type='all',min=0,region='',q='';
const dateOf=x=>new Date(x.snapshot_at||x.updated_at||x.updatedAt||x.createdAt||x.time||0);
const st=x=>String(x.source_type||x.type||'').toLowerCase();
const risk=x=>N(x.risk);
const sev=r=>(r=N(r))>=80?'Crítico':r>=60?'Alto':r>=35?'Moderado':r>=1?'Baixo':'Sem risco';
function reg(x){
  if(x.region)return String(x.region);
  const u=String(x.state||'').toUpperCase();
  const m={AC:'Norte',AM:'Norte',AP:'Norte',PA:'Norte',RO:'Norte',RR:'Norte',TO:'Norte',AL:'Nordeste',BA:'Nordeste',CE:'Nordeste',MA:'Nordeste',PB:'Nordeste',PE:'Nordeste',PI:'Nordeste',RN:'Nordeste',SE:'Nordeste',DF:'Centro-Oeste',GO:'Centro-Oeste',MT:'Centro-Oeste',MS:'Centro-Oeste',ES:'Sudeste',MG:'Sudeste',RJ:'Sudeste',SP:'Sudeste',PR:'Sul',RS:'Sul',SC:'Sul'};
  return m[u]||'Sem região';
}
async function j(p){
  for(const u of [p,'https://raw.githubusercontent.com/SamuelPRodrigues/SamuelPRodrigues/main/'+p]){
    try{const r=await fetch(u+(u.includes('?')?'&':'?')+'v='+Date.now(),{cache:'no-store'});if(r.ok)return await r.json()}catch(e){}
  }
  return null;
}
async function rows(){
  if(cache)return cache;
  const c=await j('data/analytics_cache.json');
  if(c&&Array.isArray(c.rows)){cache={src:c.source==='google_sheets'?'Histórico Sheets':'Dados atuais',updated:c.updatedAt,rows:c.rows};return cache}
  const a=await Promise.all([j('data/climate_events.json'),j('data/road_events.json'),j('data/operational_alerts.json')]);
  const out=[];
  [['climate',a[0]],['road',a[1]],['operational',a[2]]].forEach(([t,l])=>(Array.isArray(l)?l:[]).forEach(x=>{if(x&&x.active!==false)out.push({...x,source_type:t})}));
  cache={src:'Dados atuais',updated:new Date().toISOString(),rows:out};
  return cache;
}
function view(all){
  const cut=Date.now()-days*864e5;
  let arr=all.filter(x=>!days||isNaN(dateOf(x))||dateOf(x).getTime()>=cut);
  if(type!=='all')arr=arr.filter(x=>st(x)===type);
  if(min)arr=arr.filter(x=>risk(x)>=min);
  if(region)arr=arr.filter(x=>reg(x)===region);
  if(q){const s=q.toLowerCase();arr=arr.filter(x=>[x.name,x.event_type,x.eventType,x.city,x.state,reg(x),x.road,x.description,x.source].join(' ').toLowerCase().includes(s))}
  return arr;
}
function agg(arr,fn){
  const m={};
  arr.forEach(x=>{const k=fn(x)||'Sem classificação';m[k]??={key:k,count:0,sum:0,max:0};m[k].count++;m[k].sum+=risk(x);m[k].max=Math.max(m[k].max,risk(x))});
  return Object.values(m).map(x=>({...x,avg:x.count?Math.round(x.sum/x.count):0})).sort((a,b)=>b.count-a.count||b.avg-a.avg);
}
function stats(a){
  const rs=a.map(risk),cl=a.filter(x=>st(x)==='climate');
  const rain=cl.filter(x=>N(x.precipitation)>0||/chuva|garoa|precip/i.test([x.name,x.event_type,x.eventType,x.description].join(' '))).length;
  return {total:a.length,avg:rs.length?Math.round(rs.reduce((p,c)=>p+c,0)/rs.length):0,max:rs.length?Math.max(...rs):0,rain:cl.length?Math.round(rain/cl.length*100):0,road:a.filter(x=>st(x)==='road').length,op:a.filter(x=>st(x)==='operational').length};
}
function bars(items,mode){
  const max=Math.max(1,...items.map(x=>x.count));
  if(!items.length)return'<div class="db-empty">Sem dados</div>';
  return items.slice(0,6).map(x=>{
    const active=(mode==='region'&&region===x.key)||(mode==='type'&&type===x.key)||(mode==='sev'&&min===riskForSeverity(x.key));
    return `<button class="db-row ${active?'active':''}" data-mode="${mode}" data-val="${E(x.key)}" type="button"><span>${E(x.label||x.key)}</span><i><b style="width:${Math.max(5,Math.round(x.count/max*100))}%"></b></i><strong>${x.count}</strong></button>`;
  }).join('');
}
function donut(items){
  const tot=items.reduce((s,x)=>s+x.count,0)||1;
  let deg=0;
  const c={climate:'#f97316',road:'#3b82f6',operational:'#a855f7'};
  const g=items.map(x=>{const e=deg+x.count/tot*360,s=`${c[x.key]||'#94a3b8'} ${deg}deg ${e}deg`;deg=e;return s}).join(',');
  return `<div class="db-donut" style="background:conic-gradient(${g||'#334155 0 360deg'})"></div>`;
}
function trend(a){
  const d=agg(a,x=>{const z=dateOf(x);return isNaN(z)?'--':z.toISOString().slice(0,10)}).sort((a,b)=>a.key.localeCompare(b.key)).slice(-12);
  if(!d.length)return'<div class="db-empty">Sem série</div>';
  const w=520,h=140,p=16,m=Math.max(100,...d.map(x=>x.avg));
  const xs=d.map((_,i)=>p+(d.length===1?(w-2*p)/2:i*(w-2*p)/(d.length-1)));
  const ys=d.map(x=>h-p-x.avg/m*(h-2*p));
  const line=d.map((x,i)=>(i?'L':'M')+xs[i].toFixed(1)+' '+ys[i].toFixed(1)).join(' ');
  return `<svg class="db-chart" viewBox="0 0 ${w} ${h}"><path d="M${p} ${h-p}H${w-p}"/><path class="risk" d="${line}"/>${d.map((x,i)=>`<circle cx="${xs[i]}" cy="${ys[i]}" r="4"><title>${x.key}: ${x.avg}</title></circle>`).join('')}</svg>`;
}
function persist(a){
  const g={};
  a.filter(x=>st(x)==='road').forEach(x=>{const d=dateOf(x);if(isNaN(d))return;const k=x.road||x.name||'Rodovia';g[k]??={name:k,count:0,min:d,max:d,maxRisk:0};g[k].count++;if(d<g[k].min)g[k].min=d;if(d>g[k].max)g[k].max=d;g[k].maxRisk=Math.max(g[k].maxRisk,risk(x))});
  return Object.values(g).map(x=>({...x,hours:Math.max(0,Math.round((x.max-x.min)/36e5*10)/10)})).sort((a,b)=>b.hours-a.hours||b.maxRisk-a.maxRisk).slice(0,5);
}
function riskForSeverity(v){return v==='Crítico'?80:v==='Alto'?60:v==='Moderado'?35:v==='Baixo'?1:0}
function filterText(){return [type!=='all'&&TL(type),min&&`risco ${min}+`,region,q&&`busca: ${q}`].filter(Boolean).join(' • ')||'sem filtros';}
async function render(){
  const c=await rows(),a=view(c.rows),s=stats(a),types=agg(a,st).map(x=>({...x,label:TL(x.key)})),regions=agg(a,reg),sevs=agg(a,x=>x.severity||sev(risk(x))),roads=persist(a),top=a.slice().sort((x,y)=>risk(y)-risk(x)).slice(0,5);
  const upd=c.updated?new Date(c.updated).toLocaleString('pt-BR',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'}):'agora';
  $('#dbStatus').textContent=`${c.src} • ${upd}`;
  $('#dbFilter').textContent=filterText();
  $('#dbKpis').innerHTML=`<div><span>Total</span><b>${s.total}</b></div><div><span>Risco médio</span><b>${s.avg}</b></div><div><span>Maior risco</span><b>${s.max}</b></div><div><span>Chuva</span><b>${s.rain}%</b></div><div><span>Rodovias</span><b>${s.road}</b></div><div><span>Operacional</span><b>${s.op}</b></div>`;
  $('#dbExec').textContent=`Risco médio ${s.avg}/100 (${sev(s.avg)}). ${(regions[0]&&regions[0].key)||'Sem região'} concentra ${(regions[0]&&regions[0].count)||0} evento(s). ${(types[0]&&TL(types[0].key))||'Sem tipo'} é o tipo mais frequente.`;
  $('#dbTrend').innerHTML=trend(a);
  $('#dbDonut').innerHTML=donut(types);
  $('#dbTypes').innerHTML=bars(types,'type');
  $('#dbRegions').innerHTML=bars(regions,'region');
  $('#dbSev').innerHTML=bars(sevs,'sev');
  $('#dbTop').innerHTML=top.length?top.map(x=>`<div class="db-event"><b>${risk(x)} • ${E(x.name||x.event_type||x.eventType||'Evento')}</b><span>${E(TL(st(x)))} • ${E(reg(x))}${x.road?' • '+E(x.road):''}</span></div>`).join(''):'<div class="db-empty">Sem eventos</div>';
  $('#dbRoads').innerHTML=roads.length?roads.map(x=>`<div class="db-event"><b>${E(x.name)}</b><span>${x.hours}h estimadas • ${x.count} registro(s) • risco máx. ${x.maxRisk}</span></div>`).join(''):'<div class="db-empty">Sem dados rodoviários</div>';
  bindRows();
}
function bindRows(){
  $$('.db-row').forEach(b=>b.onclick=()=>{
    const m=b.dataset.mode,v=b.dataset.val;
    if(m==='region')region=region===v?'':v;
    if(m==='type'){const newType=v==='Clima'?'climate':v==='Rodovias'?'road':v==='Operacional'?'operational':v;type=type===newType?'all':newType;min=0;region='';syncChips()}
    if(m==='sev'){const r=riskForSeverity(v);min=min===r?0:r}
    render();
  });
}
function syncChips(){
  $$('.db-chip').forEach(x=>x.classList.toggle('active',(x.dataset.t==='all'&&type==='all'&&!min)||(x.dataset.t===type)||(x.dataset.t==='high'&&min===60)));
}
function resetFilters(keepPeriod=true){type='all';min=0;region='';q='';const s=$('#dbSearch');if(s)s.value='';syncChips();render()}
function killOld(){['analyticsOpen','anaModal','analyticsModal'].forEach(id=>{const e=document.getElementById(id);if(e)e.remove()});$$('.analytics-fab,.ana-modal,.analytics-modal').forEach(e=>e.remove())}
function init(){
  killOld();
  const css=document.createElement('style');
  css.textContent=`.db-open{position:fixed;top:14px;left:50%;transform:translateX(-50%);z-index:4000;background:#0f172a;color:#e5e7eb;border:1px solid #334155;border-radius:999px;padding:10px 18px;font-weight:950;box-shadow:0 14px 34px #0007;cursor:pointer}.db-open:hover{border-color:#60a5fa;background:#13233d}.db-modal{position:fixed;inset:0;background:rgba(2,6,23,.64);z-index:4100;display:none;padding:18px}.db-modal.open{display:grid;place-items:center}.db-panel{width:min(1180px,calc(100vw - 36px));height:min(790px,calc(100vh - 36px));background:#0f172a;color:#e5e7eb;border:1px solid #334155;border-radius:22px;overflow:hidden;display:grid;grid-template-columns:185px 1fr;grid-template-rows:auto 1fr;box-shadow:0 30px 80px #0009}.db-side{grid-row:1/3;background:#0b1220;color:#e5e7eb;border-right:1px solid #26344d;padding:14px;display:grid;align-content:start;gap:10px}.db-brand{text-align:center;border:1px solid #334155;border-radius:12px;padding:12px;background:#111c31;color:#bae6fd;font-weight:950;letter-spacing:.14em}.db-label{font-size:11px;text-transform:uppercase;letter-spacing:.15em;color:#94a3b8;margin-top:8px}.db-tab,.db-chip,.db-act{border:1px solid #26344d;border-radius:10px;padding:10px;background:#111c31;color:#dbeafe;font-weight:900;cursor:pointer;text-align:left}.db-tab:hover,.db-chip:hover,.db-act:hover{border-color:#60a5fa;background:#13233d}.db-tab.active,.db-chip.active{background:#1d4ed8;border-color:#60a5fa;color:#fff}.db-act{background:#0b2538;text-align:center}.db-clear{background:#3f1d2b;color:#fecaca}.db-head{background:linear-gradient(180deg,#172136,#0f172a);border-bottom:1px solid #26344d;padding:12px 18px;display:grid;grid-template-columns:1fr auto;align-items:center}.db-head h2{margin:0;text-align:center;color:#e5e7eb;font-size:21px}.db-meta{text-align:center;color:#93c5fd;font-size:12px;margin-top:3px}.db-close{border:1px solid #334155;background:#0b1220;color:#e5e7eb;border-radius:10px;padding:9px 12px;font-weight:900;cursor:pointer}.db-body{overflow:auto;padding:14px 16px;display:grid;gap:12px}.db-search{border:1px solid #26344d;border-radius:12px;padding:11px;background:#0b1220;color:#e5e7eb}.db-filter{text-align:center;color:#93c5fd;font-size:12px}.db-kpis{display:grid;grid-template-columns:repeat(6,1fr);gap:10px}.db-kpis div{background:#111c31;color:#e5e7eb;border:1px solid #26344d;border-radius:12px;padding:12px;text-align:center}.db-kpis span{display:block;color:#94a3b8;font-size:11px;text-transform:uppercase}.db-kpis b{font-size:25px}.db-exec{background:#0b2538;color:#dbeafe;border:1px solid #16405f;border-radius:12px;padding:12px 14px;line-height:1.45}.db-grid{display:grid;grid-template-columns:1.05fr .95fr;gap:12px}.db-card{background:#0b1220;border:1px solid #26344d;border-radius:14px;padding:12px;box-shadow:0 2px 6px #0004}.db-card h3{margin:0 0 9px;color:#e5e7eb;text-align:center;font-size:14px;border-bottom:1px solid #26344d;padding-bottom:7px}.wide{grid-column:1/-1}.db-chart{width:100%;height:170px;background:#08111f;border:1px solid #1f2a44;border-radius:12px}.db-chart path{stroke:#334155}.db-chart .risk{fill:none;stroke:#38bdf8;stroke-width:3}.db-chart circle{fill:#f97316;stroke:white;stroke-width:2}.db-row{width:100%;display:grid;grid-template-columns:120px 1fr 38px;gap:8px;align-items:center;background:transparent;border:1px solid transparent;border-radius:10px;padding:7px 8px;text-align:left;color:#e5e7eb;cursor:pointer}.db-row:hover,.db-row.active{background:#111c31;border-color:#60a5fa}.db-row span{overflow:hidden;text-overflow:ellipsis}.db-row i{height:10px;background:#172238;border-radius:999px;overflow:hidden}.db-row i b{display:block;height:100%;background:#3b82f6}.db-donut-wrap{display:grid;grid-template-columns:125px 1fr;gap:12px;align-items:center}.db-donut{width:115px;height:115px;border-radius:50%;position:relative}.db-donut:after{content:'';position:absolute;inset:34px;background:#0b1220;border-radius:50%;border:1px solid #26344d}.db-event{border-bottom:1px solid #1f2a44;padding:8px 0}.db-event span{display:block;color:#94a3b8;font-size:12px;margin-top:2px}.db-empty{border:1px dashed #334155;border-radius:10px;padding:12px;color:#94a3b8;text-align:center;background:#08111f}@media(max-width:960px){.db-panel{grid-template-columns:1fr}.db-side{grid-row:auto;display:flex;flex-wrap:wrap}.db-brand,.db-label{display:none}.db-kpis{grid-template-columns:repeat(3,1fr)}.db-grid{grid-template-columns:1fr}.db-tab,.db-chip,.db-act{width:auto}}@media(max-width:580px){.db-modal{padding:0}.db-panel{width:100vw;height:100vh;border-radius:0}.db-kpis{grid-template-columns:repeat(2,1fr)}.db-donut-wrap{grid-template-columns:1fr}.db-open{left:auto;right:12px;top:62px;transform:none}}`;
  document.head.appendChild(css);
  const btn=document.createElement('button');btn.className='db-open';btn.id='dbOpen';btn.type='button';btn.textContent='Dashboard';document.body.appendChild(btn);
  const m=document.createElement('div');m.className='db-modal';m.id='dbModal';m.innerHTML=`<section class="db-panel"><aside class="db-side"><div class="db-brand">OPERAÇÃO</div><div class="db-label">Período</div><button class="db-tab" data-d="7" type="button">7 dias</button><button class="db-tab active" data-d="30" type="button">30 dias</button><button class="db-tab" data-d="90" type="button">90 dias</button><div class="db-label">Tipo</div><button class="db-chip active" data-t="all" type="button">Todos</button><button class="db-chip" data-t="climate" type="button">Clima</button><button class="db-chip" data-t="road" type="button">Rodovias</button><button class="db-chip" data-t="operational" type="button">Operacional</button><button class="db-chip" data-t="high" type="button">Alto+</button><div class="db-label">Ações</div><button id="dbRefresh" class="db-act" type="button">Atualizar</button><button id="dbClear" class="db-act db-clear" type="button">Limpar filtros</button></aside><header class="db-head"><div><h2>Dashboard Operacional de Eventos</h2><div id="dbStatus" class="db-meta">Carregando...</div></div><button id="dbClose" class="db-close" type="button">Fechar</button></header><main class="db-body"><input id="dbSearch" class="db-search" placeholder="Buscar cidade, rodovia, evento ou fonte..."><div id="dbFilter" class="db-filter">sem filtros</div><section id="dbKpis" class="db-kpis"></section><section id="dbExec" class="db-exec">Carregando leitura executiva...</section><section class="db-card wide"><h3>Tendência da nota de risco</h3><div id="dbTrend"></div></section><section class="db-grid"><div class="db-card"><h3>Resumo por tipo</h3><div class="db-donut-wrap"><div id="dbDonut"></div><div id="dbTypes"></div></div></div><div class="db-card"><h3>Regiões com mais eventos</h3><div id="dbRegions"></div></div><div class="db-card"><h3>Severidade</h3><div id="dbSev"></div></div><div class="db-card"><h3>Eventos de maior atenção</h3><div id="dbTop"></div></div><div class="db-card wide"><h3>Rodovias e persistência</h3><div id="dbRoads"></div></div></section></main></section>`;document.body.appendChild(m);
  btn.onclick=()=>{m.classList.add('open');render()};
  $('#dbClose').onclick=()=>m.classList.remove('open');
  $('#dbRefresh').onclick=()=>{cache=null;render()};
  $('#dbClear').onclick=()=>resetFilters();
  $('#dbSearch').oninput=e=>{q=e.target.value.trim();render()};
  $$('.db-tab').forEach(b=>b.onclick=()=>{days=N(b.dataset.d);$$('.db-tab').forEach(x=>x.classList.remove('active'));b.classList.add('active');render()});
  $$('.db-chip').forEach(b=>b.onclick=()=>{const v=b.dataset.t;if(v==='high'){if(min===60){min=0;type='all'}else{min=60;type='all'}region=''}else if(v==='all'){type='all';min=0;region=''}else{if(type===v&&!min){type='all'}else{type=v;min=0}region=''}syncChips();render()});
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
})();
