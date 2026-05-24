(function(){
  const LS_URL='sheets_webapp_url';
  let panelOpen=false,lastRows=[],lastMode='current';
  function $(id){return document.getElementById(id)}
  function esc(s){return String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
  function num(v){const n=Number(v);return Number.isFinite(n)?n:0}
  function fmt(n){return Number.isFinite(Number(n))?String(Math.round(Number(n))):'--'}
  function riskText(r){r=num(r);return r>=80?'Crítico':r>=60?'Alto':r>=35?'Moderado':r>=1?'Baixo':'Sem risco'}
  function dt(v){const d=new Date(v||0);return Number.isFinite(d.getTime())?d:null}
  function dateKey(v){const d=dt(v);return d?d.toISOString().slice(0,10):'sem data'}
  function dayLabel(k){if(k==='sem data')return '--';const [y,m,d]=k.split('-');return `${d}/${m}`}
  function eventDate(r){return r.snapshot_at||r.updated_at||r.updatedAt||r.createdAt||r.time||r.last_seen_at||r.expires_at||r.expiresAt||''}
  function regionOfRow(r){
    if(r.region)return String(r.region);
    const state=String(r.state||'').toUpperCase();
    const map={AC:'Norte',AM:'Norte',AP:'Norte',PA:'Norte',RO:'Norte',RR:'Norte',TO:'Norte',AL:'Nordeste',BA:'Nordeste',CE:'Nordeste',MA:'Nordeste',PB:'Nordeste',PE:'Nordeste',PI:'Nordeste',RN:'Nordeste',SE:'Nordeste',DF:'Centro-Oeste',GO:'Centro-Oeste',MT:'Centro-Oeste',MS:'Centro-Oeste',ES:'Sudeste',MG:'Sudeste',RJ:'Sudeste',SP:'Sudeste',PR:'Sul',RS:'Sul',SC:'Sul'};
    if(map[state])return map[state];
    const lat=num(r.lat),lon=num(r.lon);if(lat<=-24)return'Sul';if(lon>-45&&lat>-18)return'Nordeste';if(lon>-52&&lat<-14)return'Sudeste';if(lon<-45&&lat>-12)return'Norte';return'Centro-Oeste';
  }
  function sourceType(r){return String(r.source_type||r.type||'').toLowerCase()}
  function category(r){return r.category||r.event_type||r.eventType||r.name||'Evento'}
  function roadName(r){return r.road||r.corridor||r.name||'Rodovia sem nome'}
  function normalizeCurrent(){
    let rows=[];
    try{
      const all=[...(state?.climate||[]),...(state?.roadEvents||[]),...(state?.operationalEvents||[])];
      rows=all.map(e=>({
        snapshot_at:e.createdAt||e.updatedAt||e.time||new Date().toISOString(),
        updated_at:e.updatedAt||e.createdAt||e.time||'',
        source_type:e.type||'',category:e.category||'',event_type:e.eventType||'',name:e.name||'',risk:num(e.risk),severity:riskText(e.risk),lat:e.lat,lon:e.lon,city:e.city||e.name||'',state:e.state||'',region:e.region||'',road:e.road||e.corridor||'',description:e.description||(Array.isArray(e.reasons)?e.reasons.join('; '):''),source:e.source||'',source_url:e.sourceUrl||'',raw:e
      }));
    }catch(e){rows=[]}
    return rows;
  }
  function jsonp(url){return new Promise((resolve,reject)=>{const cb='analytics_cb_'+Math.random().toString(36).slice(2);const script=document.createElement('script');const timer=setTimeout(()=>{cleanup();reject(new Error('tempo esgotado ao consultar Sheets'))},20000);function cleanup(){clearTimeout(timer);delete window[cb];script.remove()}window[cb]=data=>{cleanup();resolve(data)};script.onerror=()=>{cleanup();reject(new Error('falha ao carregar endpoint do Sheets'))};script.src=url+(url.includes('?')?'&':'?')+'callback='+cb;document.body.appendChild(script)})}
  async function loadRows(){
    const mode=$('analyticsSource').value,days=$('analyticsDays').value;
    if(mode==='current')return {rows:normalizeCurrent(),mode:'current',note:'Usando apenas eventos atualmente carregados no mapa.'};
    const endpoint=($('analyticsEndpoint').value||localStorage.getItem(LS_URL)||'').trim();
    if(!endpoint)throw new Error('Cole a URL /exec do Apps Script ou use “dados atuais”.');
    localStorage.setItem(LS_URL,endpoint);
    const params=new URLSearchParams({action:'query',days,limit:'2000',sort:'recent'});
    const data=await jsonp(endpoint+'?'+params.toString());
    if(!data.ok)throw new Error(data.error||'resposta inválida do Sheets');
    return {rows:data.rows||[],mode:'sheets',note:`Histórico do Sheets: ${data.total??(data.rows||[]).length} registro(s) encontrados; exibindo até 2.000.`};
  }
  function aggBy(rows,keyFn){const m=new Map();rows.forEach(r=>{const k=keyFn(r)||'Sem classificação';const item=m.get(k)||{count:0,sumRisk:0,maxRisk:0,items:[]};item.count++;item.sumRisk+=num(r.risk);item.maxRisk=Math.max(item.maxRisk,num(r.risk));item.items.push(r);m.set(k,item)});return [...m.entries()].map(([key,v])=>({key,...v,avgRisk:v.count?Math.round(v.sumRisk/v.count):0})).sort((a,b)=>b.count-a.count||b.avgRisk-a.avgRisk)}
  function buildStats(rows){
    const risks=rows.map(r=>num(r.risk));const climate=rows.filter(r=>sourceType(r)==='climate');const road=rows.filter(r=>sourceType(r)==='road');const op=rows.filter(r=>sourceType(r)==='operational');
    const precip=climate.map(r=>num(r.precipitation||r.raw?.current?.precipitation||r.raw?.precipitation)).filter(v=>Number.isFinite(v));
    const rainy=climate.filter(r=>num(r.precipitation||r.raw?.current?.precipitation||r.raw?.precipitation)>0||/chuva|garoa|precipita/i.test(String(r.description||r.event_type||r.name||''))).length;
    const avg=riskAvg(rows),max=risks.length?Math.max(...risks):0;
    return {total:rows.length,avgRisk:avg,maxRisk:max,climate:climate.length,road:road.length,operational:op.length,rainChance:climate.length?Math.round(rainy/climate.length*100):0,avgPrecip:precip.length?(precip.reduce((a,b)=>a+b,0)/precip.length):0};
  }
  function riskAvg(rows){return rows.length?Math.round(rows.reduce((s,r)=>s+num(r.risk),0)/rows.length):0}
  function roadDurations(rows){
    const road=rows.filter(r=>sourceType(r)==='road');const groups=new Map();
    road.forEach(r=>{const key=[roadName(r),r.event_type||'',Math.round(num(r.lat)*100)/100,Math.round(num(r.lon)*100)/100].join('|');const d=dt(eventDate(r));if(!d)return;const g=groups.get(key)||{road:roadName(r),count:0,min:d,max:d,maxRisk:0};g.count++;g.min=d<g.min?d:g.min;g.max=d>g.max?d:g.max;g.maxRisk=Math.max(g.maxRisk,num(r.risk));groups.set(key,g)});
    return [...groups.values()].map(g=>({...g,hours:Math.max(0,Math.round((g.max-g.min)/36e5*10)/10)})).sort((a,b)=>b.hours-a.hours||b.maxRisk-a.maxRisk).slice(0,6);
  }
  function dailyRisk(rows){const by=aggBy(rows,r=>dateKey(eventDate(r))).sort((a,b)=>a.key.localeCompare(b.key));return by.map(x=>({label:dayLabel(x.key),value:x.avgRisk,count:x.count}))}
  function topList(title,items,fmtFn){return `<div class="analytics-card wide"><h3>${esc(title)}</h3><div class="analytics-list">${items.length?items.map((it,i)=>fmtFn(it,i)).join(''):'<p class="analytics-muted">Sem dados suficientes.</p>'}</div></div>`}
  function bars(items,valueKey='count',label='eventos'){const max=Math.max(1,...items.map(i=>num(i[valueKey])));return items.slice(0,8).map(i=>`<div class="ana-bar-row"><span>${esc(i.key)}</span><div><i style="width:${Math.max(3,Math.round(num(i[valueKey])/max*100))}%"></i></div><b>${esc(i[valueKey])}</b></div>`).join('')||'<p class="analytics-muted">Sem dados.</p>'}
  function lineChart(points){const w=560,h=180,p=22;if(!points.length)return '<p class="analytics-muted">Sem pontos para desenhar.</p>';const max=Math.max(100,...points.map(p=>num(p.value))),min=0;const xs=points.map((_,i)=>p+(points.length===1?w/2-p:i*(w-2*p)/(points.length-1)));const ys=points.map(pt=>h-p-(num(pt.value)-min)/(max-min)*(h-2*p));const d=points.map((pt,i)=>`${i?'L':'M'}${xs[i].toFixed(1)} ${ys[i].toFixed(1)}`).join(' ');return `<svg class="ana-line" viewBox="0 0 ${w} ${h}" role="img"><path d="M${p} ${h-p}H${w-p}" class="gridline"/><path d="M${p} ${p}V${h-p}" class="gridline"/><path d="${d}" class="linepath"/>${points.map((pt,i)=>`<circle cx="${xs[i].toFixed(1)}" cy="${ys[i].toFixed(1)}" r="4"><title>${esc(pt.label)}: risco ${esc(pt.value)} (${esc(pt.count)} evento(s))</title></circle>`).join('')}${points.map((pt,i)=>i%Math.ceil(points.length/6||1)===0?`<text x="${xs[i].toFixed(1)}" y="${h-4}" text-anchor="middle">${esc(pt.label)}</text>`:'').join('')}</svg>`}
  function insight(rows,stats,regions,types,roads){
    const bits=[];
    if(stats.total)bits.push(`Risco médio ${stats.avgRisk}/100 (${riskText(stats.avgRisk)}), com pico ${stats.maxRisk}/100.`);
    if(regions[0])bits.push(`Região mais carregada: ${regions[0].key}, com ${regions[0].count} evento(s).`);
    if(types[0])bits.push(`Tipo dominante: ${typeLabelSafe(types[0].key)}, ${types[0].count} registro(s).`);
    if(stats.climate)bits.push(`Chuva detectada em aproximadamente ${stats.rainChance}% dos pontos climáticos analisados.`);
    if(roads[0]&&roads[0].hours>0)bits.push(`Maior persistência rodoviária estimada: ${roads[0].road}, cerca de ${roads[0].hours}h no histórico consultado.`);
    if(!bits.length)bits.push('Ainda não há volume suficiente para gerar uma leitura confiável.');
    return bits;
  }
  function typeLabelSafe(t){return t==='road'?'Rodovias':t==='operational'?'Operacionais':t==='climate'?'Clima':t||'Sem tipo'}
  function renderAnalytics(rows,note){
    lastRows=rows;const stats=buildStats(rows),regions=aggBy(rows,regionOfRow),types=aggBy(rows,sourceType),sev=aggBy(rows,r=>r.severity||riskText(r.risk)),roads=roadDurations(rows),daily=dailyRisk(rows).slice(-30);
    $('analyticsStatus').innerHTML=`<span>${esc(note)}</span>`;
    $('analyticsCards').innerHTML=`<div class="analytics-kpi"><b>${stats.total}</b><span>eventos analisados</span></div><div class="analytics-kpi"><b>${stats.avgRisk}</b><span>risco médio</span></div><div class="analytics-kpi"><b>${stats.maxRisk}</b><span>maior risco</span></div><div class="analytics-kpi"><b>${stats.rainChance}%</b><span>chance chuva detectada</span></div><div class="analytics-kpi"><b>${stats.road}</b><span>eventos rodoviários</span></div><div class="analytics-kpi"><b>${stats.operational}</b><span>alertas operacionais</span></div>`;
    $('analyticsBody').innerHTML=`
      <div class="analytics-card wide"><h3>Variação da nota de risco</h3>${lineChart(daily)}<p class="analytics-muted">Linha por dia com risco médio dos eventos consultados.</p></div>
      <div class="analytics-card"><h3>Regiões com mais eventos</h3>${bars(regions)}</div>
      <div class="analytics-card"><h3>Tipos de evento</h3>${bars(types.map(t=>({...t,key:typeLabelSafe(t.key)})))}</div>
      <div class="analytics-card"><h3>Severidade</h3>${bars(sev)}</div>
      <div class="analytics-card"><h3>Clima e chuva</h3><div class="ana-rain"><b>${stats.rainChance}%</b><span>dos eventos climáticos indicam chuva/precipitação</span></div><p class="analytics-muted">Precipitação média lida: ${stats.avgPrecip.toFixed(2)} mm.</p></div>
      ${topList('Rodovias com maior tempo/paralisação estimada',roads,r=>`<div class="ana-list-row"><span>${esc(r.road)}</span><b>${esc(r.hours)}h</b><small>${esc(r.count)} registro(s), risco máx. ${esc(r.maxRisk)}</small></div>`)}
      <div class="analytics-card wide"><h3>Leitura automática</h3><ul class="analytics-insights">${insight(rows,stats,regions,types,roads).map(x=>`<li>${esc(x)}</li>`).join('')}</ul></div>`;
  }
  async function refreshAnalytics(){
    $('analyticsStatus').textContent='Carregando análises...';
    try{const {rows,mode,note}=await loadRows();lastMode=mode;renderAnalytics(rows,note)}catch(e){$('analyticsStatus').innerHTML=`<span class="ana-error">${esc(e.message||e)}</span>`;renderAnalytics(normalizeCurrent(),'Fallback: usando dados atuais do mapa. Configure o endpoint do Sheets para histórico.')}
  }
  function injectCss(){const st=document.createElement('style');st.textContent=`
    .analytics-fab{position:fixed;right:18px;top:72px;z-index:1200;border:1px solid #334155;background:#0f172a;color:#e5e7eb;border-radius:14px;padding:11px 14px;font-weight:950;box-shadow:0 14px 34px rgba(0,0,0,.32);cursor:pointer}.analytics-fab:hover{border-color:#60a5fa;background:#13233d}.analytics-modal{position:fixed;inset:0;z-index:1400;background:rgba(2,6,23,.56);display:none;align-items:center;justify-content:center;padding:22px}.analytics-modal.open{display:flex}.analytics-panel{width:min(1120px,calc(100vw - 44px));max-height:calc(100vh - 44px);overflow:hidden;background:#0f172a;border:1px solid #334155;box-shadow:0 28px 70px rgba(0,0,0,.5);display:flex;flex-direction:column}.analytics-head{padding:16px 18px;border-bottom:1px solid #26344d;display:flex;justify-content:space-between;gap:12px;align-items:flex-start;background:linear-gradient(180deg,#172136,#0f172a)}.analytics-head h2{margin:0;font-size:22px}.analytics-head p{margin:4px 0 0;color:#94a3b8;font-size:13px}.analytics-close{border:1px solid #334155;background:#0b1220;color:#e5e7eb;border-radius:10px;padding:8px 10px;cursor:pointer;font-weight:900}.analytics-controls{display:grid;grid-template-columns:1.2fr 130px 120px 120px;gap:10px;padding:12px 18px;border-bottom:1px solid #26344d;background:#0b1220}.analytics-controls label{font-size:12px;color:#94a3b8;display:grid;gap:5px}.analytics-controls input,.analytics-controls select,.analytics-controls button{border:1px solid #26344d;background:#0f172a;color:#e5e7eb;border-radius:10px;padding:9px 10px}.analytics-controls button{font-weight:900;cursor:pointer;background:#0b2538}.analytics-status{font-size:12px;color:#93c5fd;padding:0 18px 10px;background:#0b1220}.analytics-content{overflow:auto;padding:16px 18px;display:grid;gap:14px}.analytics-cards{display:grid;grid-template-columns:repeat(6,1fr);gap:10px}.analytics-kpi{border:1px solid #26344d;background:#0b1220;padding:12px;border-radius:14px}.analytics-kpi b{display:block;font-size:24px}.analytics-kpi span{font-size:11px;color:#94a3b8}.analytics-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}.analytics-card{border:1px solid #26344d;background:#0b1220;padding:14px;border-radius:16px}.analytics-card.wide{grid-column:1/-1}.analytics-card h3{margin:0 0 10px;font-size:15px}.analytics-muted{color:#94a3b8;font-size:12px;line-height:1.4}.ana-error{color:#fecaca}.ana-bar-row{display:grid;grid-template-columns:120px 1fr 42px;gap:8px;align-items:center;margin:8px 0;font-size:12px}.ana-bar-row div{height:9px;background:#172238;border-radius:999px;overflow:hidden}.ana-bar-row i{display:block;height:100%;background:#3b82f6;border-radius:999px}.ana-line{width:100%;height:210px;background:#08111f;border:1px solid #1f2a44;border-radius:12px}.ana-line .gridline{stroke:#334155;stroke-width:1}.ana-line .linepath{fill:none;stroke:#38bdf8;stroke-width:3}.ana-line circle{fill:#f97316;stroke:#fff;stroke-width:2}.ana-line text{fill:#94a3b8;font-size:11px}.ana-rain b{font-size:38px}.ana-rain span{display:block;color:#94a3b8}.ana-list-row{display:grid;grid-template-columns:1fr auto;gap:6px;border-bottom:1px solid #1f2a44;padding:8px 0}.ana-list-row small{grid-column:1/-1;color:#94a3b8}.analytics-insights{margin:0;padding-left:18px;color:#dbeafe;font-size:13px;line-height:1.55}@media(max-width:900px){.analytics-controls,.analytics-cards,.analytics-grid{grid-template-columns:1fr 1fr}.analytics-fab{top:auto;bottom:80px}}@media(max-width:560px){.analytics-controls,.analytics-cards,.analytics-grid{grid-template-columns:1fr}.analytics-panel{width:100vw;height:100vh;max-height:none}.analytics-modal{padding:0}.analytics-fab{right:10px}}`;document.head.appendChild(st)}
  function injectHtml(){const btn=document.createElement('button');btn.className='analytics-fab';btn.id='analyticsOpen';btn.type='button';btn.textContent='Análises';document.body.appendChild(btn);const modal=document.createElement('div');modal.className='analytics-modal';modal.id='analyticsModal';modal.innerHTML=`<section class="analytics-panel"><header class="analytics-head"><div><h2>Análises dos eventos</h2><p>Consulta dados atuais do mapa ou o histórico salvo no Google Sheets.</p></div><button class="analytics-close" id="analyticsClose" type="button">Fechar</button></header><div class="analytics-controls"><label>Endpoint do Sheets<input id="analyticsEndpoint" placeholder="URL /exec do Apps Script"></label><label>Fonte<select id="analyticsSource"><option value="sheets">Histórico Sheets</option><option value="current">Dados atuais</option></select></label><label>Período<select id="analyticsDays"><option value="7">7 dias</option><option value="30" selected>30 dias</option><option value="90">90 dias</option><option value="0">Tudo</option></select></label><label>&nbsp;<button id="analyticsRefresh" type="button">Atualizar</button></label></div><div id="analyticsStatus" class="analytics-status">Pronto para consultar.</div><div class="analytics-content"><div id="analyticsCards" class="analytics-cards"></div><div id="analyticsBody" class="analytics-grid"></div></div></section>`;document.body.appendChild(modal);$('analyticsEndpoint').value=localStorage.getItem(LS_URL)||'';btn.onclick=()=>{panelOpen=true;modal.classList.add('open');refreshAnalytics()};$('analyticsClose').onclick=()=>modal.classList.remove('open');modal.addEventListener('click',e=>{if(e.target===modal)modal.classList.remove('open')});$('analyticsRefresh').onclick=refreshAnalytics;$('analyticsEndpoint').addEventListener('change',()=>localStorage.setItem(LS_URL,$('analyticsEndpoint').value.trim()))}
  function init(){if($('analyticsOpen'))return;injectCss();injectHtml()}
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
})();
