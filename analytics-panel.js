(function(){
  const $ = id => document.getElementById(id);
  const esc = v => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const num = v => { const n = Number(v); return Number.isFinite(n) ? n : 0; };
  const typeLabel = t => ({climate:'Clima', road:'Rodovias', operational:'Operacional'}[String(t || '').toLowerCase()] || 'Sem tipo');
  const riskLabel = r => (r=num(r))>=80?'Crítico':r>=60?'Alto':r>=35?'Moderado':r>=1?'Baixo':'Sem risco';
  const eventDate = r => r.snapshot_at || r.updated_at || r.updatedAt || r.createdAt || r.time || r.last_seen_at || '';
  const toDate = v => { const d = new Date(v || 0); return Number.isFinite(d.getTime()) ? d : null; };
  const sourceType = r => String(r.source_type || r.type || '').toLowerCase();
  const dayKey = r => { const d = toDate(eventDate(r)); return d ? d.toISOString().slice(0,10) : 'sem-data'; };
  const dayLabel = k => { if(k === 'sem-data') return '--'; const p = k.split('-'); return p.length === 3 ? `${p[2]}/${p[1]}` : k; };

  let cache = null;
  let period = 30;
  let filters = { type:'all', minRisk:0, region:'', severity:'', query:'' };

  function regionOf(r){
    if(r.region) return String(r.region);
    const uf = String(r.state || '').toUpperCase();
    const map = {AC:'Norte',AM:'Norte',AP:'Norte',PA:'Norte',RO:'Norte',RR:'Norte',TO:'Norte',AL:'Nordeste',BA:'Nordeste',CE:'Nordeste',MA:'Nordeste',PB:'Nordeste',PE:'Nordeste',PI:'Nordeste',RN:'Nordeste',SE:'Nordeste',DF:'Centro-Oeste',GO:'Centro-Oeste',MT:'Centro-Oeste',MS:'Centro-Oeste',ES:'Sudeste',MG:'Sudeste',RJ:'Sudeste',SP:'Sudeste',PR:'Sul',RS:'Sul',SC:'Sul'};
    if(map[uf]) return map[uf];
    const lat = num(r.lat), lon = num(r.lon);
    if(lat <= -24) return 'Sul';
    if(lon > -45 && lat > -18) return 'Nordeste';
    if(lon > -52 && lat < -14) return 'Sudeste';
    if(lon < -45 && lat > -12) return 'Norte';
    return 'Centro-Oeste';
  }

  async function fetchJson(path, fallback){
    const urls = [path, 'https://raw.githubusercontent.com/SamuelPRodrigues/SamuelPRodrigues/main/' + path];
    for(const url of urls){
      try{
        const res = await fetch(url + (url.includes('?') ? '&' : '?') + 'v=' + Date.now(), { cache:'no-store' });
        if(res.ok) return await res.json();
      }catch(_){ }
    }
    return fallback;
  }

  function normalize(type, ev){
    ev = ev || {};
    const risk = num(ev.risk);
    return {
      source_type: type,
      name: ev.name || ev.road || ev.eventType || ev.category || typeLabel(type),
      event_type: ev.eventType || ev.event_type || ev.category || '',
      risk,
      severity: ev.severity || riskLabel(risk),
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
      precipitation: ev.precipitation || (ev.current && ev.current.precipitation) || 0
    };
  }

  async function currentRows(){
    const [climate, road, operational] = await Promise.all([
      fetchJson('data/climate_events.json', []),
      fetchJson('data/road_events.json', []),
      fetchJson('data/operational_alerts.json', [])
    ]);
    const rows = [];
    [['climate',climate], ['road',road], ['operational',operational]].forEach(([type, list]) => {
      (Array.isArray(list) ? list : []).forEach(ev => { if(ev && ev.active !== false) rows.push(normalize(type, ev)); });
    });
    return { source:'Dados atuais', updatedAt:new Date().toISOString(), rows };
  }

  async function loadData(){
    const cached = await fetchJson('data/analytics_cache.json', null);
    if(cached && Array.isArray(cached.rows)) return { source: cached.source === 'google_sheets' ? 'Histórico Sheets' : 'Dados atuais', updatedAt: cached.updatedAt, rows: cached.rows };
    return currentRows();
  }

  function inPeriod(rows){
    if(!period) return rows;
    const cutoff = Date.now() - period * 86400000;
    return rows.filter(r => { const d = toDate(eventDate(r)); return !d || d.getTime() >= cutoff; });
  }

  function applyFilters(rows){
    let out = inPeriod(rows);
    if(filters.type !== 'all') out = out.filter(r => sourceType(r) === filters.type);
    if(filters.minRisk) out = out.filter(r => num(r.risk) >= filters.minRisk);
    if(filters.region) out = out.filter(r => regionOf(r) === filters.region);
    if(filters.severity) out = out.filter(r => (r.severity || riskLabel(r.risk)) === filters.severity);
    if(filters.query){
      const q = filters.query.toLowerCase();
      out = out.filter(r => [r.name, r.event_type, r.city, r.state, regionOf(r), r.road, r.description, r.source].join(' ').toLowerCase().includes(q));
    }
    return out;
  }

  function aggregate(rows, keyFn){
    const map = new Map();
    rows.forEach(r => {
      const key = keyFn(r) || 'Sem classificação';
      const item = map.get(key) || { key, count:0, riskSum:0, maxRisk:0 };
      item.count += 1;
      item.riskSum += num(r.risk);
      item.maxRisk = Math.max(item.maxRisk, num(r.risk));
      map.set(key, item);
    });
    return [...map.values()].map(x => ({...x, avgRisk: x.count ? Math.round(x.riskSum / x.count) : 0})).sort((a,b) => b.count - a.count || b.avgRisk - a.avgRisk);
  }

  function buildStats(rows){
    const risks = rows.map(r => num(r.risk));
    const climate = rows.filter(r => sourceType(r) === 'climate');
    const rainy = climate.filter(r => num(r.precipitation) > 0 || /chuva|garoa|precipita/i.test([r.name,r.event_type,r.description].join(' '))).length;
    const critical = rows.filter(r => num(r.risk) >= 80).length;
    return {
      total: rows.length,
      avgRisk: risks.length ? Math.round(risks.reduce((a,b)=>a+b,0) / risks.length) : 0,
      maxRisk: risks.length ? Math.max(...risks) : 0,
      critical,
      rainChance: climate.length ? Math.round(rainy / climate.length * 100) : 0,
      roads: rows.filter(r => sourceType(r) === 'road').length,
      operational: rows.filter(r => sourceType(r) === 'operational').length
    };
  }

  function series(rows){
    return aggregate(rows, dayKey).sort((a,b) => a.key.localeCompare(b.key)).slice(-14).map(x => ({ label: dayLabel(x.key), value: x.avgRisk, count: x.count }));
  }

  function roadPersistence(rows){
    const groups = new Map();
    rows.filter(r => sourceType(r) === 'road').forEach(r => {
      const d = toDate(eventDate(r)); if(!d) return;
      const key = [r.road || r.name || 'Rodovia', r.event_type || '', Math.round(num(r.lat)*100)/100, Math.round(num(r.lon)*100)/100].join('|');
      const item = groups.get(key) || { name:r.road || r.name || 'Rodovia', count:0, min:d, max:d, maxRisk:0 };
      item.count += 1; if(d < item.min) item.min = d; if(d > item.max) item.max = d; item.maxRisk = Math.max(item.maxRisk, num(r.risk));
      groups.set(key, item);
    });
    return [...groups.values()].map(x => ({...x, hours: Math.max(0, Math.round((x.max - x.min) / 360000) / 10)})).sort((a,b) => b.hours - a.hours || b.maxRisk - a.maxRisk).slice(0,4);
  }

  function compactNumber(v){ return Number.isFinite(Number(v)) ? String(Math.round(Number(v))) : '--'; }

  function spark(points){
    if(!points.length) return '<div class="ana-empty">Ainda sem série temporal</div>';
    const w = 520, h = 130, pad = 16, max = Math.max(100, ...points.map(p => num(p.value)));
    const xs = points.map((_,i) => pad + (points.length === 1 ? (w-2*pad)/2 : i * (w-2*pad) / (points.length-1)));
    const ys = points.map(p => h - pad - (num(p.value) / max) * (h - 2*pad));
    const line = points.map((p,i) => (i ? 'L' : 'M') + xs[i].toFixed(1) + ' ' + ys[i].toFixed(1)).join(' ');
    return `<svg class="ana-spark" viewBox="0 0 ${w} ${h}"><path d="M${pad} ${h-pad}H${w-pad}"/><path class="risk" d="${line}"/>${points.map((p,i)=>`<circle cx="${xs[i].toFixed(1)}" cy="${ys[i].toFixed(1)}" r="4"><title>${esc(p.label)}: risco ${esc(p.value)} (${esc(p.count)} eventos)</title></circle>`).join('')}${points.map((p,i)=>i%Math.ceil(points.length/5||1)===0?`<text x="${xs[i].toFixed(1)}" y="${h-2}" text-anchor="middle">${esc(p.label)}</text>`:'').join('')}</svg>`;
  }

  function bars(items, filterType){
    const max = Math.max(1, ...items.map(i => num(i.count)));
    if(!items.length) return '<div class="ana-empty">Sem dados no filtro atual</div>';
    return items.slice(0,6).map(item => `<button class="ana-row" data-filter="${esc(filterType || '')}" data-value="${esc(item.key)}"><span>${esc(item.label || item.key)}</span><i><b style="width:${Math.max(5, Math.round(item.count / max * 100))}%"></b></i><strong>${esc(item.count)}</strong></button>`).join('');
  }

  function insightText(stats, regions, types, roads){
    const parts = [];
    if(stats.total) parts.push(`Risco médio ${stats.avgRisk}/100 (${riskLabel(stats.avgRisk)}).`);
    if(regions[0]) parts.push(`${regions[0].key} lidera com ${regions[0].count} evento(s).`);
    if(types[0]) parts.push(`${typeLabel(types[0].key)} é o principal tipo.`);
    if(stats.critical) parts.push(`${stats.critical} evento(s) crítico(s) exigem atenção.`);
    if(stats.rainChance) parts.push(`Chuva aparece em ${stats.rainChance}% dos registros climáticos.`);
    if(roads[0] && roads[0].hours > 0) parts.push(`Maior persistência rodoviária estimada: ${roads[0].name}, ${roads[0].hours}h.`);
    return parts.length ? parts.join(' ') : 'Ainda não há volume suficiente para uma leitura confiável.';
  }

  function topEvents(rows){
    return rows.slice().sort((a,b) => num(b.risk) - num(a.risk)).slice(0,6);
  }

  function activeFilterText(){
    const bits = [];
    if(filters.type !== 'all') bits.push(typeLabel(filters.type));
    if(filters.minRisk) bits.push(`risco ${filters.minRisk}+`);
    if(filters.region) bits.push(filters.region);
    if(filters.severity) bits.push(filters.severity);
    if(filters.query) bits.push(`busca: ${filters.query}`);
    return bits;
  }

  async function render(){
    $('anaStatus').textContent = 'Carregando...';
    try{
      cache = cache || await loadData();
      const rows = applyFilters(cache.rows || []);
      const stats = buildStats(rows);
      const regions = aggregate(rows, regionOf);
      const types = aggregate(rows, sourceType).map(x => ({...x, label:typeLabel(x.key)}));
      const severities = aggregate(rows, r => r.severity || riskLabel(r.risk));
      const roads = roadPersistence(rows);
      const top = topEvents(rows);
      const updated = cache.updatedAt ? new Date(cache.updatedAt).toLocaleString('pt-BR', {day:'2-digit', month:'2-digit', hour:'2-digit', minute:'2-digit'}) : 'agora';
      $('anaStatus').textContent = `${cache.source || 'Dados'} • ${updated}`;
      $('anaFilterNote').innerHTML = activeFilterText().length ? activeFilterText().map(x => `<span>${esc(x)}</span>`).join('') + '<button id="anaClearInline" type="button">limpar</button>' : '<span>sem filtros adicionais</span>';
      const clearInline = $('anaClearInline'); if(clearInline) clearInline.onclick = clearFilters;
      $('anaKPIs').innerHTML = `
        <div class="ana-kpi"><b>${stats.total}</b><span>eventos</span></div>
        <div class="ana-kpi"><b>${stats.avgRisk}</b><span>risco médio</span></div>
        <div class="ana-kpi"><b>${stats.critical}</b><span>críticos</span></div>
        <div class="ana-kpi"><b>${stats.rainChance}%</b><span>chuva</span></div>`;
      $('anaInsight').textContent = insightText(stats, regions, types, roads);
      $('anaTrend').innerHTML = spark(series(rows));
      $('anaRegions').innerHTML = bars(regions, 'region');
      $('anaTypes').innerHTML = bars(types, 'type');
      $('anaSeverity').innerHTML = bars(severities, 'severity');
      $('anaTop').innerHTML = top.length ? top.map(e => `<button class="ana-event" type="button" title="${esc(e.description || '')}"><b>${esc(e.risk)} • ${esc(e.name || e.event_type || 'Evento')}</b><span>${esc(typeLabel(sourceType(e)))} • ${esc(regionOf(e))}${e.road ? ' • ' + esc(e.road) : ''}</span></button>`).join('') : '<div class="ana-empty">Nenhum evento no filtro atual</div>';
      $('anaRoads').innerHTML = roads.length ? roads.map(r => `<div class="ana-road"><b>${esc(r.name)}</b><span>${esc(r.hours)}h estimadas • ${esc(r.count)} registro(s) • risco máx. ${esc(r.maxRisk)}</span></div>`).join('') : '<div class="ana-empty">Sem dados rodoviários suficientes</div>';
      bindRows();
    }catch(err){
      $('anaStatus').textContent = 'Erro ao carregar análise';
      $('anaInsight').textContent = String(err && err.message ? err.message : err);
    }
  }

  function bindRows(){
    document.querySelectorAll('.ana-row[data-filter="region"]').forEach(btn => btn.onclick = () => { filters.region = btn.dataset.value || ''; render(); });
    document.querySelectorAll('.ana-row[data-filter="type"]').forEach(btn => btn.onclick = () => { const label = btn.dataset.value || ''; const reverse = {Clima:'climate', Rodovias:'road', Operacional:'operational'}; filters.type = reverse[label] || label || 'all'; render(); });
    document.querySelectorAll('.ana-row[data-filter="severity"]').forEach(btn => btn.onclick = () => { filters.severity = btn.dataset.value || ''; render(); });
  }

  function clearFilters(){
    filters = { type:'all', minRisk:0, region:'', severity:'', query:'' };
    $('anaSearch').value = '';
    document.querySelectorAll('.ana-chip').forEach(x => x.classList.toggle('active', x.dataset.type === 'all'));
    render();
  }

  function injectStyle(){
    const style = document.createElement('style');
    style.textContent = `
      .analytics-fab{position:fixed;left:50%;top:14px;transform:translateX(-50%);z-index:2500;border:1px solid #334155;background:#0f172a;color:#e5e7eb;border-radius:999px;padding:10px 16px;font-weight:950;box-shadow:0 14px 34px rgba(0,0,0,.36);cursor:pointer}.analytics-fab:hover{border-color:#60a5fa;background:#13233d}.ana-modal{position:fixed;inset:0;z-index:2600;background:rgba(2,6,23,.58);display:none;padding:18px}.ana-modal.open{display:grid;place-items:center}.ana-panel{width:min(980px,100%);height:min(760px,calc(100vh - 36px));background:#0f172a;color:#e5e7eb;border:1px solid #334155;box-shadow:0 28px 70px rgba(0,0,0,.5);border-radius:22px;display:grid;grid-template-rows:auto auto auto 1fr;overflow:hidden}.ana-head{display:flex;justify-content:space-between;gap:12px;padding:16px 18px;border-bottom:1px solid #22314d}.ana-head h2{margin:0;font-size:22px}.ana-head p{margin:4px 0 0;color:#94a3b8;font-size:13px}.ana-close{background:#0b1220;color:#e5e7eb;border:1px solid #334155;border-radius:12px;padding:8px 11px;font-weight:900;cursor:pointer}.ana-controls{display:grid;grid-template-columns:auto auto 1fr auto;gap:10px;align-items:center;padding:12px 18px;border-bottom:1px solid #22314d;background:#0b1220}.ana-tabs,.ana-chips{display:flex;gap:7px;align-items:center;flex-wrap:wrap}.ana-tab,.ana-chip,.ana-refresh,.ana-clear{border:1px solid #26344d;background:#0f172a;color:#cbd5e1;border-radius:999px;padding:8px 11px;font-weight:850;cursor:pointer}.ana-tab.active,.ana-chip.active{background:#2563eb;color:#fff;border-color:#60a5fa}.ana-search{min-width:180px;border:1px solid #26344d;background:#0f172a;color:#e5e7eb;border-radius:999px;padding:9px 12px}.ana-refresh{background:#0b2538;color:#dbeafe}.ana-clear{background:#111827}.ana-status{display:flex;justify-content:space-between;gap:10px;padding:9px 18px;background:#0b1220;color:#93c5fd;font-size:12px;border-bottom:1px solid #172238}.ana-filter-note{display:flex;gap:6px;flex-wrap:wrap;justify-content:flex-end}.ana-filter-note span,.ana-filter-note button{border:0;border-radius:999px;background:#1e293b;color:#bfdbfe;padding:3px 8px;font-size:12px}.ana-filter-note button{cursor:pointer}.ana-body{overflow:auto;padding:16px 18px;display:grid;gap:14px}.ana-kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}.ana-kpi{border:1px solid #26344d;background:#0b1220;border-radius:16px;padding:13px}.ana-kpi b{display:block;font-size:28px}.ana-kpi span{color:#94a3b8;font-size:12px}.ana-insight{background:linear-gradient(180deg,#0b2538,#0b1220);border:1px solid #1e3a5f;border-radius:16px;padding:14px;color:#dbeafe;line-height:1.45}.ana-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}.ana-card{border:1px solid #26344d;background:#0b1220;border-radius:18px;padding:14px}.ana-card.wide{grid-column:1/-1}.ana-card h3{margin:0 0 10px;font-size:15px}.ana-card h3 span{float:right;color:#94a3b8;font-size:12px;font-weight:500}.ana-spark{width:100%;height:150px;background:#08111f;border:1px solid #1f2a44;border-radius:14px}.ana-spark path{stroke:#334155;stroke-width:1}.ana-spark .risk{fill:none;stroke:#38bdf8;stroke-width:3}.ana-spark circle{fill:#f97316;stroke:#fff;stroke-width:2}.ana-spark text{fill:#94a3b8;font-size:11px}.ana-row{width:100%;display:grid;grid-template-columns:126px 1fr 38px;gap:8px;align-items:center;background:transparent;color:#e5e7eb;border:0;padding:7px 0;text-align:left;cursor:pointer}.ana-row:hover span{text-decoration:underline}.ana-row i{height:9px;background:#172238;border-radius:999px;overflow:hidden}.ana-row i b{display:block;height:100%;background:#3b82f6;border-radius:999px}.ana-event{width:100%;text-align:left;border:0;background:#0f172a;color:#e5e7eb;border-radius:12px;padding:10px;margin:6px 0;cursor:pointer}.ana-event:hover{background:#13233d}.ana-event b{display:block}.ana-event span,.ana-road span{display:block;color:#94a3b8;font-size:12px;margin-top:3px}.ana-road{border-bottom:1px solid #1f2a44;padding:9px 0}.ana-empty{color:#94a3b8;font-size:13px;padding:12px;border:1px dashed #334155;border-radius:14px}.ana-details{border:1px solid #26344d;background:#0b1220;border-radius:18px;padding:0}.ana-details summary{cursor:pointer;padding:14px;font-weight:900}.ana-details>div{padding:0 14px 14px}@media(max-width:900px){.ana-controls{grid-template-columns:1fr}.ana-kpis,.ana-grid{grid-template-columns:1fr 1fr}.analytics-fab{top:62px}}@media(max-width:560px){.ana-modal{padding:0}.ana-panel{height:100vh;border-radius:0}.ana-kpis,.ana-grid{grid-template-columns:1fr}.analytics-fab{left:auto;right:12px;top:62px;transform:none}}`;
    document.head.appendChild(style);
  }

  function injectHtml(){
    if($('analyticsOpen')) return;
    const button = document.createElement('button');
    button.id = 'analyticsOpen';
    button.className = 'analytics-fab';
    button.type = 'button';
    button.textContent = 'Análises';
    document.body.appendChild(button);

    const modal = document.createElement('div');
    modal.id = 'anaModal';
    modal.className = 'ana-modal';
    modal.innerHTML = `
      <section class="ana-panel">
        <header class="ana-head">
          <div><h2>Análises</h2><p>Painel automático, sem URL ou configuração manual.</p></div>
          <button id="anaClose" class="ana-close" type="button">Fechar</button>
        </header>
        <div class="ana-controls">
          <div class="ana-tabs">
            <button class="ana-tab" data-days="7" type="button">7 dias</button>
            <button class="ana-tab active" data-days="30" type="button">30 dias</button>
            <button class="ana-tab" data-days="90" type="button">90 dias</button>
          </div>
          <div class="ana-chips">
            <button class="ana-chip active" data-type="all" type="button">Todos</button>
            <button class="ana-chip" data-type="climate" type="button">Clima</button>
            <button class="ana-chip" data-type="road" type="button">Rodovias</button>
            <button class="ana-chip" data-type="operational" type="button">Operacional</button>
            <button class="ana-chip" data-type="high" type="button">Alto+</button>
          </div>
          <input id="anaSearch" class="ana-search" placeholder="Buscar local, rodovia, tipo...">
          <button id="anaRefresh" class="ana-refresh" type="button">Atualizar</button>
        </div>
        <div class="ana-status"><span id="anaStatus">Pronto</span><span id="anaFilterNote" class="ana-filter-note"><span>sem filtros</span></span></div>
        <main class="ana-body">
          <div id="anaKPIs" class="ana-kpis"></div>
          <div id="anaInsight" class="ana-insight">Carregando leitura...</div>
          <section class="ana-card wide"><h3>Tendência de risco <span>média diária</span></h3><div id="anaTrend"></div></section>
          <div class="ana-grid">
            <section class="ana-card"><h3>Regiões <span>clique para filtrar</span></h3><div id="anaRegions"></div></section>
            <section class="ana-card"><h3>Tipos <span>clique para filtrar</span></h3><div id="anaTypes"></div></section>
            <section class="ana-card"><h3>Severidade <span>clique para filtrar</span></h3><div id="anaSeverity"></div></section>
            <section class="ana-card"><h3>Eventos críticos</h3><div id="anaTop"></div></section>
          </div>
          <details class="ana-details"><summary>Rodovias e persistência</summary><div id="anaRoads"></div></details>
        </main>
      </section>`;
    document.body.appendChild(modal);

    button.onclick = () => { modal.classList.add('open'); render(); };
    $('anaClose').onclick = () => modal.classList.remove('open');
    $('anaRefresh').onclick = () => { cache = null; render(); };
    modal.onclick = e => { if(e.target === modal) modal.classList.remove('open'); };
    $('anaSearch').addEventListener('input', () => { filters.query = $('anaSearch').value.trim(); render(); });
    document.querySelectorAll('.ana-tab').forEach(tab => tab.onclick = () => { period = Number(tab.dataset.days); document.querySelectorAll('.ana-tab').forEach(x => x.classList.remove('active')); tab.classList.add('active'); render(); });
    document.querySelectorAll('.ana-chip').forEach(chip => chip.onclick = () => {
      document.querySelectorAll('.ana-chip').forEach(x => x.classList.remove('active'));
      chip.classList.add('active');
      const value = chip.dataset.type;
      filters.type = value === 'high' ? 'all' : value;
      filters.minRisk = value === 'high' ? 60 : 0;
      filters.region = '';
      filters.severity = '';
      render();
    });
  }

  function init(){ injectStyle(); injectHtml(); }
  if(document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
