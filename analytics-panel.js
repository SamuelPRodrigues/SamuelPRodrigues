(function(){
  var LS_URL = 'sheets_webapp_url';
  function el(id){ return document.getElementById(id); }
  function esc(v){ return String(v == null ? '' : v).replace(/[&<>"']/g, function(c){ return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]; }); }
  function num(v){ var n = Number(v); return isFinite(n) ? n : 0; }
  function riskText(r){ r = num(r); if(r>=80)return 'Crítico'; if(r>=60)return 'Alto'; if(r>=35)return 'Moderado'; if(r>=1)return 'Baixo'; return 'Sem risco'; }
  function typeLabel(t){ if(t==='road')return 'Rodovias'; if(t==='operational')return 'Operacional'; if(t==='climate')return 'Clima'; return t || 'Sem tipo'; }
  function eventDate(r){ return r.snapshot_at || r.updated_at || r.updatedAt || r.createdAt || r.time || r.last_seen_at || ''; }
  function dateObj(v){ var d = new Date(v || 0); return isFinite(d.getTime()) ? d : null; }
  function dayKey(v){ var d = dateObj(v); return d ? d.toISOString().slice(0,10) : 'sem data'; }
  function dayLabel(k){ if(k==='sem data') return '--'; var p=k.split('-'); return p.length===3 ? p[2]+'/'+p[1] : k; }
  function regionOf(r){
    if(r.region) return String(r.region);
    var uf = String(r.state || '').toUpperCase();
    var map = {AC:'Norte',AM:'Norte',AP:'Norte',PA:'Norte',RO:'Norte',RR:'Norte',TO:'Norte',AL:'Nordeste',BA:'Nordeste',CE:'Nordeste',MA:'Nordeste',PB:'Nordeste',PE:'Nordeste',PI:'Nordeste',RN:'Nordeste',SE:'Nordeste',DF:'Centro-Oeste',GO:'Centro-Oeste',MT:'Centro-Oeste',MS:'Centro-Oeste',ES:'Sudeste',MG:'Sudeste',RJ:'Sudeste',SP:'Sudeste',PR:'Sul',RS:'Sul',SC:'Sul'};
    if(map[uf]) return map[uf];
    var lat=num(r.lat), lon=num(r.lon);
    if(lat<=-24) return 'Sul';
    if(lon>-45 && lat>-18) return 'Nordeste';
    if(lon>-52 && lat<-14) return 'Sudeste';
    if(lon<-45 && lat>-12) return 'Norte';
    return 'Centro-Oeste';
  }
  function sourceType(r){ return String(r.source_type || r.type || '').toLowerCase(); }
  function normalizeEvent(type, ev){
    ev = ev || {};
    var risk = num(ev.risk);
    return {
      source_type: type,
      name: ev.name || ev.road || ev.eventType || ev.category || type,
      event_type: ev.eventType || ev.event_type || ev.category || '',
      risk: risk,
      severity: riskText(risk),
      lat: ev.lat,
      lon: ev.lon,
      city: ev.city || ev.name || '',
      state: ev.state || '',
      region: ev.region || '',
      road: ev.road || ev.corridor || '',
      description: ev.description || (Array.isArray(ev.reasons) ? ev.reasons.join('; ') : ''),
      source: ev.source || '',
      source_url: ev.sourceUrl || ev.source_url || '',
      snapshot_at: ev.createdAt || ev.updatedAt || ev.time || new Date().toISOString(),
      updated_at: ev.updatedAt || ev.time || '',
      precipitation: ev.precipitation || (ev.current && ev.current.precipitation) || 0,
      raw: ev
    };
  }
  async function getJson(path){
    var urls = [path, 'https://raw.githubusercontent.com/SamuelPRodrigues/SamuelPRodrigues/main/' + path];
    for(var i=0;i<urls.length;i++){
      try{
        var sep = urls[i].indexOf('?') >= 0 ? '&' : '?';
        var r = await fetch(urls[i] + sep + 'v=' + Date.now(), {cache:'no-store'});
        if(r.ok) return await r.json();
      }catch(e){}
    }
    return [];
  }
  async function loadCurrent(){
    var packs = await Promise.all([getJson('data/climate_events.json'), getJson('data/road_events.json'), getJson('data/operational_alerts.json')]);
    var rows=[];
    [['climate',packs[0]],['road',packs[1]],['operational',packs[2]]].forEach(function(pair){
      var type=pair[0], list=Array.isArray(pair[1]) ? pair[1] : [];
      list.forEach(function(ev){ if(ev && ev.active !== false) rows.push(normalizeEvent(type, ev)); });
    });
    return rows;
  }
  function jsonp(url){
    return new Promise(function(resolve,reject){
      var cb = 'analytics_cb_' + Math.random().toString(36).slice(2);
      var script = document.createElement('script');
      var timer = setTimeout(function(){ cleanup(); reject(new Error('tempo esgotado ao consultar Sheets')); }, 20000);
      function cleanup(){ clearTimeout(timer); try{ delete window[cb]; }catch(e){} if(script.parentNode) script.parentNode.removeChild(script); }
      window[cb] = function(data){ cleanup(); resolve(data); };
      script.onerror = function(){ cleanup(); reject(new Error('falha ao carregar endpoint do Sheets')); };
      script.src = url + (url.indexOf('?')>=0 ? '&' : '?') + 'callback=' + cb;
      document.body.appendChild(script);
    });
  }
  async function loadSheets(){
    var endpoint = (el('analyticsEndpoint').value || localStorage.getItem(LS_URL) || '').trim();
    if(!endpoint) throw new Error('Cole a URL /exec do Apps Script ou mude a fonte para Dados atuais.');
    localStorage.setItem(LS_URL, endpoint);
    var params = new URLSearchParams({action:'query',days:el('analyticsDays').value,limit:'2000',sort:'recent'});
    var data = await jsonp(endpoint + '?' + params.toString());
    if(!data || !data.ok) throw new Error((data && data.error) || 'resposta inválida do Sheets');
    return data.rows || [];
  }
  function aggregate(rows, fn){
    var out = {};
    rows.forEach(function(r){
      var k = fn(r) || 'Sem classificação';
      if(!out[k]) out[k] = {key:k,count:0,sumRisk:0,maxRisk:0};
      out[k].count += 1; out[k].sumRisk += num(r.risk); out[k].maxRisk = Math.max(out[k].maxRisk, num(r.risk));
    });
    return Object.keys(out).map(function(k){ var x=out[k]; x.avgRisk = x.count ? Math.round(x.sumRisk/x.count) : 0; return x; }).sort(function(a,b){ return b.count-a.count || b.avgRisk-a.avgRisk; });
  }
  function stats(rows){
    var risks=rows.map(function(r){return num(r.risk);});
    var climate=rows.filter(function(r){return sourceType(r)==='climate';});
    var road=rows.filter(function(r){return sourceType(r)==='road';});
    var op=rows.filter(function(r){return sourceType(r)==='operational';});
    var rainy=climate.filter(function(r){ return num(r.precipitation)>0 || /chuva|garoa|precipita/i.test(String(r.description||r.event_type||r.name||'')); }).length;
    var avg = risks.length ? Math.round(risks.reduce(function(a,b){return a+b;},0)/risks.length) : 0;
    return {total:rows.length,avgRisk:avg,maxRisk:risks.length?Math.max.apply(null,risks):0,climate:climate.length,road:road.length,operational:op.length,rainChance:climate.length?Math.round(rainy/climate.length*100):0};
  }
  function daily(rows){
    return aggregate(rows, function(r){return dayKey(eventDate(r));}).sort(function(a,b){return a.key.localeCompare(b.key);}).slice(-30).map(function(x){return {label:dayLabel(x.key), value:x.avgRisk, count:x.count};});
  }
  function roadDurations(rows){
    var road = rows.filter(function(r){return sourceType(r)==='road';});
    var g = {};
    road.forEach(function(r){
      var d = dateObj(eventDate(r)); if(!d) return;
      var key = [r.road||r.name||'Rodovia', r.event_type||'', Math.round(num(r.lat)*100)/100, Math.round(num(r.lon)*100)/100].join('|');
      if(!g[key]) g[key] = {road:r.road||r.name||'Rodovia',count:0,min:d,max:d,maxRisk:0};
      g[key].count++; if(d<g[key].min)g[key].min=d; if(d>g[key].max)g[key].max=d; g[key].maxRisk=Math.max(g[key].maxRisk,num(r.risk));
    });
    return Object.keys(g).map(function(k){var x=g[k]; x.hours=Math.max(0,Math.round((x.max-x.min)/360000)/10); return x;}).sort(function(a,b){return b.hours-a.hours || b.maxRisk-a.maxRisk;}).slice(0,6);
  }
  function bars(items){
    var max = Math.max(1, ...items.map(function(i){return num(i.count);}));
    if(!items.length) return '<p class="analytics-muted">Sem dados.</p>';
    return items.slice(0,8).map(function(i){ return '<div class="ana-bar-row"><span>'+esc(i.key)+'</span><div><i style="width:'+Math.max(3,Math.round(num(i.count)/max*100))+'%"></i></div><b>'+esc(i.count)+'</b></div>'; }).join('');
  }
  function line(points){
    if(!points.length) return '<p class="analytics-muted">Sem dados para o gráfico.</p>';
    var w=560,h=180,p=22,max=Math.max(100,...points.map(function(x){return num(x.value);}));
    var xs=points.map(function(_,i){return p+(points.length===1?w/2-p:i*(w-2*p)/(points.length-1));});
    var ys=points.map(function(pt){return h-p-(num(pt.value)/max)*(h-2*p);});
    var d=points.map(function(pt,i){return (i?'L':'M')+xs[i].toFixed(1)+' '+ys[i].toFixed(1);}).join(' ');
    return '<svg class="ana-line" viewBox="0 0 '+w+' '+h+'"><path d="M'+p+' '+(h-p)+'H'+(w-p)+'" class="gridline"/><path d="M'+p+' '+p+'V'+(h-p)+'" class="gridline"/><path d="'+d+'" class="linepath"/>'+points.map(function(pt,i){return '<circle cx="'+xs[i].toFixed(1)+'" cy="'+ys[i].toFixed(1)+'" r="4"><title>'+esc(pt.label)+': risco '+esc(pt.value)+' ('+esc(pt.count)+' eventos)</title></circle>';}).join('')+points.map(function(pt,i){return i%Math.ceil(points.length/6||1)===0?'<text x="'+xs[i].toFixed(1)+'" y="'+(h-4)+'" text-anchor="middle">'+esc(pt.label)+'</text>':'';}).join('')+'</svg>';
  }
  function insight(rows, s, regions, types, roads){
    var a=[];
    if(s.total) a.push('Risco médio '+s.avgRisk+'/100 ('+riskText(s.avgRisk)+'), com pico '+s.maxRisk+'/100.');
    if(regions[0]) a.push('Região mais carregada: '+regions[0].key+', com '+regions[0].count+' evento(s).');
    if(types[0]) a.push('Tipo dominante: '+typeLabel(types[0].key)+', '+types[0].count+' registro(s).');
    if(s.climate) a.push('Chuva detectada em aproximadamente '+s.rainChance+'% dos pontos climáticos analisados.');
    if(roads[0] && roads[0].hours>0) a.push('Maior persistência rodoviária estimada: '+roads[0].road+', cerca de '+roads[0].hours+'h no histórico consultado.');
    if(!a.length) a.push('Ainda não há volume suficiente para gerar uma leitura confiável.');
    return a;
  }
  function render(rows, note){
    var s=stats(rows), regions=aggregate(rows,regionOf), types=aggregate(rows,sourceType).map(function(x){x.key=typeLabel(x.key);return x;}), sev=aggregate(rows,function(r){return r.severity || riskText(r.risk);}), roads=roadDurations(rows), d=daily(rows);
    el('analyticsStatus').innerHTML = esc(note || '');
    el('analyticsCards').innerHTML = '<div class="analytics-kpi"><b>'+s.total+'</b><span>eventos analisados</span></div><div class="analytics-kpi"><b>'+s.avgRisk+'</b><span>risco médio</span></div><div class="analytics-kpi"><b>'+s.maxRisk+'</b><span>maior risco</span></div><div class="analytics-kpi"><b>'+s.rainChance+'%</b><span>chance chuva detectada</span></div><div class="analytics-kpi"><b>'+s.road+'</b><span>eventos rodoviários</span></div><div class="analytics-kpi"><b>'+s.operational+'</b><span>alertas operacionais</span></div>';
    el('analyticsBody').innerHTML = '<div class="analytics-card wide"><h3>Variação da nota de risco</h3>'+line(d)+'<p class="analytics-muted">Risco médio por dia no período consultado.</p></div><div class="analytics-card"><h3>Regiões com mais eventos</h3>'+bars(regions)+'</div><div class="analytics-card"><h3>Tipos de evento</h3>'+bars(types)+'</div><div class="analytics-card"><h3>Severidade</h3>'+bars(sev)+'</div><div class="analytics-card"><h3>Clima e chuva</h3><div class="ana-rain"><b>'+s.rainChance+'%</b><span>dos eventos climáticos indicam chuva/precipitação</span></div></div><div class="analytics-card wide"><h3>Rodovias com maior tempo/paralisação estimada</h3>'+(roads.length?roads.map(function(r){return '<div class="ana-list-row"><span>'+esc(r.road)+'</span><b>'+esc(r.hours)+'h</b><small>'+esc(r.count)+' registro(s), risco máx. '+esc(r.maxRisk)+'</small></div>';}).join(''):'<p class="analytics-muted">Sem dados rodoviários suficientes.</p>')+'</div><div class="analytics-card wide"><h3>Leitura automática</h3><ul class="analytics-insights">'+insight(rows,s,regions,types,roads).map(function(x){return '<li>'+esc(x)+'</li>';}).join('')+'</ul></div>';
  }
  async function refresh(){
    el('analyticsStatus').textContent='Carregando análises...';
    try{
      var rows, note;
      if(el('analyticsSource').value==='current') { rows=await loadCurrent(); note='Usando os JSONs atuais do mapa.'; }
      else { rows=await loadSheets(); note='Usando histórico do Google Sheets.'; }
      render(rows,note);
    }catch(e){
      try{ var fallback=await loadCurrent(); render(fallback,'Erro no histórico: '+(e.message||e)+' Fallback: dados atuais do mapa.'); }
      catch(_){ el('analyticsStatus').textContent = String(e.message || e); }
    }
  }
  function css(){
    var st=document.createElement('style');
    st.textContent = '.analytics-fab{position:fixed;left:50%;top:14px;transform:translateX(-50%);z-index:2500;border:1px solid #60a5fa;background:#0f172a;color:#e5e7eb;border-radius:999px;padding:11px 18px;font-weight:950;box-shadow:0 14px 34px rgba(0,0,0,.42);cursor:pointer}.analytics-fab:hover{background:#13233d}.analytics-modal{position:fixed;inset:0;z-index:2600;background:rgba(2,6,23,.58);display:none;align-items:center;justify-content:center;padding:22px}.analytics-modal.open{display:flex}.analytics-panel{width:min(1120px,calc(100vw - 44px));max-height:calc(100vh - 44px);overflow:hidden;background:#0f172a;color:#e5e7eb;border:1px solid #334155;box-shadow:0 28px 70px rgba(0,0,0,.5);display:flex;flex-direction:column;border-radius:18px}.analytics-head{padding:16px 18px;border-bottom:1px solid #26344d;display:flex;justify-content:space-between;gap:12px;background:linear-gradient(180deg,#172136,#0f172a)}.analytics-head h2{margin:0;font-size:22px}.analytics-head p{margin:4px 0 0;color:#94a3b8;font-size:13px}.analytics-close{border:1px solid #334155;background:#0b1220;color:#e5e7eb;border-radius:10px;padding:8px 10px;cursor:pointer;font-weight:900}.analytics-controls{display:grid;grid-template-columns:1.2fr 130px 120px 120px;gap:10px;padding:12px 18px;border-bottom:1px solid #26344d;background:#0b1220}.analytics-controls label{font-size:12px;color:#94a3b8;display:grid;gap:5px}.analytics-controls input,.analytics-controls select,.analytics-controls button{border:1px solid #26344d;background:#0f172a;color:#e5e7eb;border-radius:10px;padding:9px 10px}.analytics-controls button{font-weight:900;cursor:pointer;background:#0b2538}.analytics-status{font-size:12px;color:#93c5fd;padding:0 18px 10px;background:#0b1220}.analytics-content{overflow:auto;padding:16px 18px;display:grid;gap:14px}.analytics-cards{display:grid;grid-template-columns:repeat(6,1fr);gap:10px}.analytics-kpi{border:1px solid #26344d;background:#0b1220;padding:12px;border-radius:14px}.analytics-kpi b{display:block;font-size:24px}.analytics-kpi span{font-size:11px;color:#94a3b8}.analytics-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}.analytics-card{border:1px solid #26344d;background:#0b1220;padding:14px;border-radius:16px}.analytics-card.wide{grid-column:1/-1}.analytics-card h3{margin:0 0 10px;font-size:15px}.analytics-muted{color:#94a3b8;font-size:12px}.ana-bar-row{display:grid;grid-template-columns:120px 1fr 42px;gap:8px;align-items:center;margin:8px 0;font-size:12px}.ana-bar-row div{height:9px;background:#172238;border-radius:999px;overflow:hidden}.ana-bar-row i{display:block;height:100%;background:#3b82f6;border-radius:999px}.ana-line{width:100%;height:210px;background:#08111f;border:1px solid #1f2a44;border-radius:12px}.ana-line .gridline{stroke:#334155;stroke-width:1}.ana-line .linepath{fill:none;stroke:#38bdf8;stroke-width:3}.ana-line circle{fill:#f97316;stroke:#fff;stroke-width:2}.ana-line text{fill:#94a3b8;font-size:11px}.ana-rain b{font-size:38px}.ana-rain span{display:block;color:#94a3b8}.ana-list-row{display:grid;grid-template-columns:1fr auto;gap:6px;border-bottom:1px solid #1f2a44;padding:8px 0}.ana-list-row small{grid-column:1/-1;color:#94a3b8}.analytics-insights{margin:0;padding-left:18px;color:#dbeafe;font-size:13px;line-height:1.55}@media(max-width:900px){.analytics-controls,.analytics-cards,.analytics-grid{grid-template-columns:1fr 1fr}.analytics-fab{top:62px}}@media(max-width:560px){.analytics-controls,.analytics-cards,.analytics-grid{grid-template-columns:1fr}.analytics-panel{width:100vw;height:100vh;max-height:none;border-radius:0}.analytics-modal{padding:0}.analytics-fab{left:auto;right:12px;top:62px;transform:none}}';
    document.head.appendChild(st);
  }
  function html(){
    if(el('analyticsOpen')) return;
    var btn=document.createElement('button'); btn.className='analytics-fab'; btn.id='analyticsOpen'; btn.type='button'; btn.textContent='Análises'; document.body.appendChild(btn);
    var modal=document.createElement('div'); modal.className='analytics-modal'; modal.id='analyticsModal';
    modal.innerHTML='<section class="analytics-panel"><header class="analytics-head"><div><h2>Análises dos eventos</h2><p>Dados atuais do mapa ou histórico salvo no Google Sheets.</p></div><button class="analytics-close" id="analyticsClose" type="button">Fechar</button></header><div class="analytics-controls"><label>Endpoint do Sheets<input id="analyticsEndpoint" placeholder="URL /exec do Apps Script"></label><label>Fonte<select id="analyticsSource"><option value="sheets">Histórico Sheets</option><option value="current">Dados atuais</option></select></label><label>Período<select id="analyticsDays"><option value="7">7 dias</option><option value="30" selected>30 dias</option><option value="90">90 dias</option><option value="0">Tudo</option></select></label><label>&nbsp;<button id="analyticsRefresh" type="button">Atualizar</button></label></div><div id="analyticsStatus" class="analytics-status">Pronto para consultar.</div><div class="analytics-content"><div id="analyticsCards" class="analytics-cards"></div><div id="analyticsBody" class="analytics-grid"></div></div></section>';
    document.body.appendChild(modal);
    el('analyticsEndpoint').value = localStorage.getItem(LS_URL) || '';
    btn.onclick=function(){ modal.classList.add('open'); refresh(); };
    el('analyticsClose').onclick=function(){ modal.classList.remove('open'); };
    el('analyticsRefresh').onclick=refresh;
    modal.onclick=function(e){ if(e.target===modal) modal.classList.remove('open'); };
    el('analyticsEndpoint').onchange=function(){ localStorage.setItem(LS_URL, el('analyticsEndpoint').value.trim()); };
  }
  function init(){ css(); html(); }
  if(document.readyState==='loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
