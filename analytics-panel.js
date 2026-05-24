(function(){
  function $(id){return document.getElementById(id)}
  function esc(v){return String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
  function n(v){v=Number(v);return Number.isFinite(v)?v:0}
  function riskText(r){r=n(r);return r>=80?'Crítico':r>=60?'Alto':r>=35?'Moderado':r>=1?'Baixo':'Sem risco'}
  function typeName(t){return t==='road'?'Rodovias':t==='operational'?'Operacional':t==='climate'?'Clima':t||'Sem tipo'}
  function dt(v){const d=new Date(v||0);return Number.isFinite(d.getTime())?d:null}
  function eventDate(r){return r.snapshot_at||r.updated_at||r.updatedAt||r.createdAt||r.time||r.last_seen_at||''}
  function dayKey(v){const d=dt(v);return d?d.toISOString().slice(0,10):'sem-data'}
  function dayLabel(k){if(k==='sem-data')return '--';const p=k.split('-');return p.length===3?`${p[2]}/${p[1]}`:k}
  function regionOf(r){
    if(r.region)return String(r.region);
    const uf=String(r.state||'').toUpperCase();
    const map={AC:'Norte',AM:'Norte',AP:'Norte',PA:'Norte',RO:'Norte',RR:'Norte',TO:'Norte',AL:'Nordeste',BA:'Nordeste',CE:'Nordeste',MA:'Nordeste',PB:'Nordeste',PE:'Nordeste',PI:'Nordeste',RN:'Nordeste',SE:'Nordeste',DF:'Centro-Oeste',GO:'Centro-Oeste',MT:'Centro-Oeste',MS:'Centro-Oeste',ES:'Sudeste',MG:'Minas Gerais',RJ:'Rio de Janeiro',SP:'São Paulo',PR:'Sul',RS:'Sul',SC:'Sul'};
    if(map[uf])return map[uf];
    const lat=n(r.lat),lon=n(r.lon);if(lat<=-24)return'Sul';if(lon>-45&&lat>-18)return'Nordeste';if(lon>-52&&lat<-14)return'Sudeste';if(lon<-45&&lat>-12)return'Norte';return'Centro-Oeste';
  }
  function sourceType(r){return String(r.source_type||r.type||'').toLowerCase()}
  async function getJson(path,fallback){
    const urls=[path,'https://raw.githubusercontent.com/SamuelPRodrigues/SamuelPRodrigues/main/'+path];
    for(const url of urls){try{const sep=url.includes('?')?'&':'?';const res=await fetch(url+sep+'v='+Date.now(),{cache:'no-store'});if(res.ok)return await res.json()}catch(e){}}
    return fallback;
  }
  function normalize(type,ev){
    ev=ev||{};const risk=n(ev.risk);
    return {source_type:type,name:ev.name||ev.road||ev.eventType||type,event_type:ev.eventType||ev.event_type||ev.category||'',risk,severity:ev.severity||riskText(risk),lat:ev.lat,lon:ev.lon,city:ev.city||ev.name||'',state:ev.state||'',region:ev.region||'',road:ev.road||ev.corridor||'',description:ev.description||(Array.isArray(ev.reasons)?ev.reasons.join('; '):''),source:ev.source||'',source_url:ev.sourceUrl||ev.source_url||'',snapshot_at:ev.createdAt||ev.updatedAt||ev.time||new Date().toISOString(),updated_at:ev.updatedAt||ev.time||'',precipitation:ev.precipitation||(ev.current&&ev.current.precipitation)||0};
  }
  async function loadCurrent(){
    const packs=await Promise.all([getJson('data/climate_events.json',[]),getJson('data/road_events.json',[]),getJson('data/operational_alerts.json',[])]);
    const rows=[];[['climate',packs[0]],['road',packs[1]],['operational',packs[2]]].forEach(([type,list])=>{(Array.isArray(list)?list:[]).forEach(ev=>{if(ev&&ev.active!==false)rows.push(normalize(type,ev))})});
    return {rows,source:'current_json_fallback',updatedAt:new Date().toISOString()};
  }
  async function loadCache(){
    const cache=await getJson('data/analytics_cache.json',null);
    if(cache&&Array.isArray(cache.rows))return cache;
    return await loadCurrent();
  }
  function filterDays(rows,days){
    days=Number(days);if(!days)return rows;
    const cutoff=Date.now()-days*86400000;
    return rows.filter(r=>{const d=dt(eventDate(r));return !d||d.getTime()>=cutoff});
  }
  function agg(rows,fn){
    const m=new Map();rows.forEach(r=>{const k=fn(r)||'Sem classificação';const o=m.get(k)||{key:k,count:0,sumRisk:0,maxRisk:0,items:[]};o.count++;o.sumRisk+=n(r.risk);o.maxRisk=Math.max(o.maxRisk,n(r.risk));o.items.push(r);m.set(k,o)});
    return [...m.values()].map(o=>({...o,avgRisk:o.count?Math.round(o.sumRisk/o.count):0})).sort((a,b)=>b.count-a.count||b.avgRisk-a.avgRisk);
  }
  function buildStats(rows){
    const risks=rows.map(r=>n(r.risk));const climate=rows.filter(r=>sourceType(r)==='climate'),road=rows.filter(r=>sourceType(r)==='road'),op=rows.filter(r=>sourceType(r)==='operational');
    const rainy=climate.filter(r=>n(r.precipitation)>0||/chuva|garoa|precipita/i.test(String(r.description||r.event_type||r.name||''))).length;
    return {total:rows.length,avgRisk:risks.length?Math.round(risks.reduce((a,b)=>a+b,0)/risks.length):0,maxRisk:risks.length?Math.max(...risks):0,climate:climate.length,road:road.length,operational:op.length,rainChance:climate.length?Math.round(rainy/climate.length*100):0};
  }
  function daily(rows){return agg(rows,r=>dayKey(eventDate(r))).sort((a,b)=>a.key.localeCompare(b.key)).slice(-18).map(x=>({label:dayLabel(x.key),value:x.avgRisk,count:x.count}))}
  function roadDur(rows){
    const groups=new Map();rows.filter(r=>sourceType(r)==='road').forEach(r=>{const d=dt(eventDate(r));if(!d)return;const key=[r.road||r.name||'Rodovia',r.event_type||'',Math.round(n(r.lat)*100)/100,Math.round(n(r.lon)*100)/100].join('|');const g=groups.get(key)||{road:r.road||r.name||'Rodovia',count:0,min:d,max:d,maxRisk:0};g.count++;if(d<g.min)g.min=d;if(d>g.max)g.max=d;g.maxRisk=Math.max(g.maxRisk,n(r.risk));groups.set(key,g)});
    return [...groups.values()].map(g=>({...g,hours:Math.max(0,Math.round((g.max-g.min)/360000)/10)})).sort((a,b)=>b.hours-a.hours||b.maxRisk-a.maxRisk).slice(0,5);
  }
  function bars(items,onClickKey){
    const max=Math.max(1,...items.map(i=>n(i.count)));
    if(!items.length)return '<div class="ana-empty">Sem dados</div>';
    return items.slice(0,7).map(i=>`<button class="ana-bar" data-key="${esc(i.key)}" data-filter="${onClickKey||''}"><span>${esc(i.key)}</span><i><b style="width:${Math.max(4,Math.round(n(i.count)/max*100))}%"></b></i><strong>${esc(i.count)}</strong></button>`).join('');
  }
  function line(points){
    if(!points.length)return '<div class="ana-empty">Sem série temporal</div>';
    const w=680,h=180,p=22,max=Math.max(100,...points.map(x=>n(x.value)));const xs=points.map((_,i)=>p+(points.length===1?w/2-p:i*(w-2*p)/(points.length-1)));const ys=points.map(pt=>h-p-(n(pt.value)/max)*(h-2*p));const d=points.map((pt,i)=>(i?'L':'M')+xs[i].toFixed(1)+' '+ys[i].toFixed(1)).join(' ');
    return `<svg class="ana-line" viewBox="0 0 ${w} ${h}"><path d="M${p} ${h-p}H${w-p}" class="grid"/><path d="M${p} ${p}V${h-p}" class="grid"/><path d="${d}" class="risk-line"/>${points.map((pt,i)=>`<circle cx="${xs[i].toFixed(1)}" cy="${ys[i].toFixed(1)}" r="5"><title>${esc(pt.label)} • risco ${esc(pt.value)} • ${esc(pt.count)} evento(s)</title></circle>`).join('')}${points.map((pt,i)=>i%Math.ceil(points.length/6||1)===0?`<text x="${xs[i].toFixed(1)}" y="${h-4}" text-anchor="middle">${esc(pt.label)}</text>`:'').join('')}</svg>`;
  }
  function insights(rows,st,regions,types,roads){
    const out=[];if(st.total)out.push(`Risco médio ${st.avgRisk}/100 (${riskText(st.avgRisk)}), pico ${st.maxRisk}/100.`);if(regions[0])out.push(`${regions[0].key} concentra ${regions[0].count} evento(s).`);if(types[0])out.push(`${typeName(types[0].key)} é o tipo dominante no período.`);if(st.climate)out.push(`Chuva aparece em ${st.rainChance}% dos pontos climáticos.`);if(roads[0]&&roads[0].hours>0)out.push(`Maior persistência estimada: ${roads[0].road}, ${roads[0].hours}h.`);if(!out.length)out.push('Ainda não há volume suficiente para uma leitura confiável.');return out;
  }
  function topEvents(rows){return rows.slice().sort((a,b)=>n(b.risk)-n(a.risk)).slice(0,5)}
  let rawCache=null,period=30,activeFilter=null;
  async function render(){
    $('anaStatus').textContent='Carregando...';
    rawCache=rawCache||await loadCache();
    let rows=filterDays(rawCache.rows||[],period);
    if(activeFilter){rows=rows.filter(r=>activeFilter.type==='region'?regionOf(r)===activeFilter.value:sourceType(r)===activeFilter.value)}
    const st=buildStats(rows),regions=agg(rows,regionOf),types=agg(rows,sourceType),sev=agg(rows,r=>r.severity||riskText(r.risk)),roads=roadDur(rows),events=topEvents(rows);
    $('anaStatus').textContent=`${rawCache.source==='google_sheets'?'Histórico Sheets':'Dados atuais'} • ${rows.length} evento(s) • atualizado ${rawCache.updatedAt?new Date(rawCache.updatedAt).toLocaleString('pt-BR',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'}):'agora'}`;
    $('anaKPIs').innerHTML=`<button class="kpi"><b>${st.total}</b><span>eventos</span></button><button class="kpi"><b>${st.avgRisk}</b><span>risco médio</span></button><button class="kpi"><b>${st.maxRisk}</b><span>maior risco</span></button><button class="kpi"><b>${st.rainChance}%</b><span>chuva</span></button><button class="kpi"><b>${st.road}</b><span>rodovias</span></button><button class="kpi"><b>${st.operational}</b><span>operacional</span></button>`;
    $('anaMain').innerHTML=`
      <section class="ana-card wide"><div class="ana-title"><h3>Risco ao longo do tempo</h3><span>média diária</span></div>${line(daily(rows))}</section>
      <section class="ana-card"><div class="ana-title"><h3>Regiões críticas</h3><span>clique para filtrar</span></div>${bars(regions,'region')}</section>
      <section class="ana-card"><div class="ana-title"><h3>Tipos</h3><span>clique para filtrar</span></div>${bars(types.map(x=>({...x,keyLabel:typeName(x.key)})).map(x=>({...x,key:x.keyLabel||x.key,rawKey:x.key})),'type')}</section>
      <section class="ana-card"><div class="ana-title"><h3>Severidade</h3><span>distribuição</span></div>${bars(sev)}</section>
      <section class="ana-card"><div class="ana-title"><h3>Eventos mais perigosos</h3><span>top 5</span></div>${events.length?events.map(e=>`<div class="ana-event"><b>${esc(e.risk)} • ${esc(e.name||e.event_type)}</b><span>${esc(typeName(sourceType(e)))} • ${esc(regionOf(e))}</span></div>`).join(''):'<div class="ana-empty">Sem eventos</div>'}</section>
      <section class="ana-card wide"><div class="ana-title"><h3>Rodovias e persistência</h3><span>estimativa pelo histórico</span></div>${roads.length?roads.map(r=>`<div class="ana-road"><span>${esc(r.road)}</span><b>${esc(r.hours)}h</b><small>${esc(r.count)} registro(s), risco máximo ${esc(r.maxRisk)}</small></div>`).join(''):'<div class="ana-empty">Sem dados rodoviários suficientes</div>'}</section>
      <section class="ana-card wide"><div class="ana-title"><h3>Leitura operacional automática</h3><span>resumo</span></div><ul class="ana-insights">${insights(rows,st,regions,types,roads).map(x=>`<li>${esc(x)}</li>`).join('')}</ul></section>`;
    document.querySelectorAll('.ana-bar[data-filter="region"]').forEach(btn=>btn.onclick=()=>{activeFilter={type:'region',value:btn.dataset.key};render()});
    document.querySelectorAll('.ana-bar[data-filter="type"]').forEach((btn,i)=>btn.onclick=()=>{const item=types[i];activeFilter=item?{type:'type',value:item.key}:null;render()});
    $('anaFilterChip').innerHTML=activeFilter?`Filtro: ${esc(activeFilter.value)} <button type="button">limpar</button>`:'';
    const clear=$('anaFilterChip').querySelector('button');if(clear)clear.onclick=()=>{activeFilter=null;render()};
  }
  function style(){const s=document.createElement('style');s.textContent=`
    .analytics-fab{position:fixed;left:50%;top:14px;transform:translateX(-50%);z-index:2500;border:1px solid #334155;background:#0f172a;color:#e5e7eb;border-radius:999px;padding:10px 16px;font-weight:950;box-shadow:0 14px 34px rgba(0,0,0,.36);cursor:pointer}.analytics-fab:hover{border-color:#60a5fa;background:#13233d}.ana-modal{position:fixed;inset:0;z-index:2600;background:rgba(2,6,23,.58);display:none;padding:18px}.ana-modal.open{display:grid;place-items:center}.ana-panel{width:min(1080px,100%);height:min(820px,calc(100vh - 36px));background:#0f172a;color:#e5e7eb;border:1px solid #334155;box-shadow:0 28px 70px rgba(0,0,0,.5);border-radius:22px;display:grid;grid-template-rows:auto auto auto 1fr;overflow:hidden}.ana-head{display:flex;justify-content:space-between;align-items:flex-start;gap:14px;padding:18px 20px;border-bottom:1px solid #22314d}.ana-head h2{margin:0;font-size:22px}.ana-head p{margin:5px 0 0;color:#94a3b8;font-size:13px}.ana-close{background:#0b1220;color:#e5e7eb;border:1px solid #334155;border-radius:12px;padding:9px 12px;font-weight:900;cursor:pointer}.ana-tabs{display:flex;align-items:center;gap:8px;padding:12px 20px;border-bottom:1px solid #22314d;background:#0b1220}.ana-tab{border:1px solid #26344d;background:#0f172a;color:#cbd5e1;border-radius:999px;padding:8px 12px;font-weight:850;cursor:pointer}.ana-tab.active{background:#1d4ed8;color:#fff;border-color:#60a5fa}.ana-refresh{margin-left:auto;border:1px solid #26344d;background:#0b2538;color:#dbeafe;border-radius:999px;padding:8px 12px;font-weight:900;cursor:pointer}.ana-status{padding:0 20px 12px;background:#0b1220;color:#93c5fd;font-size:12px;display:flex;gap:8px;align-items:center}.ana-chip{color:#e0f2fe}.ana-chip button{margin-left:8px;border:0;border-radius:999px;padding:4px 8px;background:#1e293b;color:#bfdbfe;cursor:pointer}.ana-body{overflow:auto;padding:18px 20px;display:grid;gap:14px}.ana-kpis{display:grid;grid-template-columns:repeat(6,1fr);gap:10px}.kpi{border:1px solid #26344d;background:#0b1220;color:#e5e7eb;border-radius:16px;padding:12px;text-align:left}.kpi b{display:block;font-size:25px}.kpi span{color:#94a3b8;font-size:12px}.ana-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}.ana-card{border:1px solid #26344d;background:#0b1220;border-radius:18px;padding:14px}.ana-card.wide{grid-column:1/-1}.ana-title{display:flex;justify-content:space-between;gap:8px;align-items:center;margin-bottom:10px}.ana-title h3{font-size:15px;margin:0}.ana-title span{color:#94a3b8;font-size:12px}.ana-line{width:100%;height:210px;background:#08111f;border:1px solid #1f2a44;border-radius:14px}.ana-line .grid{stroke:#334155;stroke-width:1}.ana-line .risk-line{fill:none;stroke:#38bdf8;stroke-width:3}.ana-line circle{fill:#f97316;stroke:#fff;stroke-width:2}.ana-line text{fill:#94a3b8;font-size:11px}.ana-bar{width:100%;display:grid;grid-template-columns:130px 1fr 42px;gap:9px;align-items:center;background:transparent;color:#e5e7eb;border:0;padding:7px 0;text-align:left;cursor:pointer}.ana-bar:hover span{text-decoration:underline}.ana-bar i{height:9px;background:#172238;border-radius:999px;overflow:hidden}.ana-bar i b{display:block;height:100%;background:#3b82f6;border-radius:999px}.ana-event,.ana-road{display:grid;gap:3px;padding:8px 0;border-bottom:1px solid #1f2a44}.ana-event span,.ana-road small{color:#94a3b8;font-size:12px}.ana-road{grid-template-columns:1fr auto}.ana-road small{grid-column:1/-1}.ana-empty{color:#94a3b8;font-size:13px;padding:12px;border:1px dashed #334155;border-radius:14px}.ana-insights{margin:0;padding-left:18px;color:#dbeafe;font-size:13px;line-height:1.6}@media(max-width:900px){.ana-kpis,.ana-grid{grid-template-columns:1fr 1fr}.analytics-fab{top:62px}}@media(max-width:560px){.ana-modal{padding:0}.ana-panel{height:100vh;border-radius:0}.ana-kpis,.ana-grid{grid-template-columns:1fr}.analytics-fab{left:auto;right:12px;top:62px;transform:none}.ana-tabs{flex-wrap:wrap}}`;document.head.appendChild(s)}
  function html(){if($('analyticsOpen'))return;const b=document.createElement('button');b.id='analyticsOpen';b.type='button';b.className='analytics-fab';b.textContent='Análises';document.body.appendChild(b);const m=document.createElement('div');m.id='anaModal';m.className='ana-modal';m.innerHTML=`<section class="ana-panel"><header class="ana-head"><div><h2>Análises dos eventos</h2><p>Resumo automático do histórico sincronizado. Sem configuração manual.</p></div><button id="anaClose" class="ana-close" type="button">Fechar</button></header><nav class="ana-tabs"><button class="ana-tab" data-days="7">7 dias</button><button class="ana-tab active" data-days="30">30 dias</button><button class="ana-tab" data-days="90">90 dias</button><button class="ana-refresh" id="anaRefresh" type="button">Atualizar</button></nav><div class="ana-status"><span id="anaStatus">Pronto</span><span id="anaFilterChip" class="ana-chip"></span></div><main class="ana-body"><div id="anaKPIs" class="ana-kpis"></div><div id="anaMain" class="ana-grid"></div></main></section>`;document.body.appendChild(m);b.onclick=()=>{m.classList.add('open');render()};$('anaClose').onclick=()=>m.classList.remove('open');$('anaRefresh').onclick=()=>{rawCache=null;render()};m.onclick=e=>{if(e.target===m)m.classList.remove('open')};document.querySelectorAll('.ana-tab').forEach(btn=>btn.onclick=()=>{period=Number(btn.dataset.days);document.querySelectorAll('.ana-tab').forEach(x=>x.classList.remove('active'));btn.classList.add('active');render()})}
  function init(){style();html()}
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
})();
