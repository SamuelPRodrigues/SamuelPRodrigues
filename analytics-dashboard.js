(() => {
  const state = {
    rows: [],
    page: 'charts',
    filters: { type: 'all', severity: 'all', region: 'all', query: '', sort: 'recent' },
    detailId: '',
  };

  const $ = (id) => document.getElementById(id);
  const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const num = (value) => Number(value) || 0;
  const colors = ['#3b82f6', '#f97316', '#a855f7', '#22c55e', '#f59e0b', '#ef4444', '#06b6d4', '#84cc16'];
  const typeColors = { climate: '#f97316', road: '#3b82f6', operational: '#a855f7', manual: '#22c55e' };
  const severityColors = { Crítico: '#ef4444', Critico: '#ef4444', Alto: '#f59e0b', Moderado: '#3b82f6', Baixo: '#22c55e', critical: '#ef4444', high: '#f59e0b', moderate: '#3b82f6', low: '#22c55e' };

  function injectCss() {
    if ($('dashboardPanelStyles')) return;
    const css = document.createElement('style');
    css.id = 'dashboardPanelStyles';
    css.textContent = `
      .dashboard-panel{position:fixed;z-index:966;left:var(--dock-collapsed);top:0;bottom:0;width:min(760px,calc(100vw - var(--dock-collapsed)));background:rgba(7,17,32,.98);border:1px solid rgba(96,165,250,.24);border-left:0;border-radius:0;color:var(--text);box-shadow:18px 0 70px rgba(0,0,0,.34);backdrop-filter:blur(16px);padding:16px;overflow:auto;opacity:0;pointer-events:none;transform:translateX(-100%);transition:opacity .18s ease,transform .18s ease,left .22s ease,width .22s ease;scrollbar-width:thin;scrollbar-color:rgba(147,197,253,.42) rgba(7,17,32,.32)}
      .dock.expanded ~ .dashboard-panel{left:var(--dock-expanded);width:min(760px,calc(100vw - var(--dock-expanded)))}
      body.dashboard-panel-open .dashboard-panel{opacity:1;pointer-events:auto;transform:translateX(0)}
      .dashboard-panel::-webkit-scrollbar{width:10px}.dashboard-panel::-webkit-scrollbar-track{background:rgba(7,17,32,.28);border-left:1px solid rgba(96,165,250,.10)}.dashboard-panel::-webkit-scrollbar-thumb{background:linear-gradient(180deg,rgba(147,197,253,.55),rgba(37,99,235,.38));border:2px solid rgba(7,17,32,.95);border-radius:999px}.dashboard-panel::-webkit-scrollbar-thumb:hover{background:linear-gradient(180deg,rgba(191,219,254,.75),rgba(96,165,250,.55))}
      .dash-tabs{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin:12px 0}.dash-tab{border:1px solid rgba(96,165,250,.24);background:rgba(15,35,64,.58);color:#dbeafe;border-radius:14px;padding:10px 12px;font-size:12px;font-weight:950;cursor:pointer}.dash-tab.active,.dash-tab:hover{background:rgba(37,99,235,.26);border-color:rgba(147,197,253,.55)}
      .dash-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:10px;margin-bottom:12px}.dash-kpi{border:1px solid rgba(96,165,250,.16);background:rgba(16,32,57,.52);border-radius:18px;padding:12px}.dash-kpi span{display:block;font-size:10px;color:#93c5fd;font-weight:900;text-transform:uppercase;letter-spacing:.06em}.dash-kpi b{display:block;font-size:24px;line-height:1.1;margin-top:6px}.dash-kpi small{display:block;color:#9db2d4;font-size:11px;margin-top:5px;line-height:1.25}
      .dash-chart-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}.dash-card{border:1px solid rgba(96,165,250,.16);background:rgba(11,22,40,.84);border-radius:18px;padding:12px;min-height:190px}.dash-wide{grid-column:1/-1}.dash-card-head{display:flex;justify-content:space-between;gap:8px;align-items:flex-start;margin-bottom:10px}.dash-card-title{font-size:13px;font-weight:950}.dash-card-note{font-size:10px;color:#9db2d4;text-align:right;line-height:1.25}.dash-donut-wrap{display:grid;grid-template-columns:150px 1fr;gap:12px;align-items:center}.dash-donut-center{font-size:11px;fill:#dbeafe;font-weight:950}.dash-legend-list{display:grid;gap:7px}.dash-legend{display:grid;grid-template-columns:10px 1fr auto;gap:7px;align-items:center;border:0;background:transparent;color:#dbeafe;padding:0;text-align:left;font-size:11px;cursor:pointer}.dash-legend i{width:10px;height:10px;border-radius:999px}.dash-legend span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.dash-legend b{color:#93c5fd}.dash-legend:hover span{color:#fff;font-weight:900}
      .dash-bar-list{display:grid;gap:9px}.dash-bar-row{display:grid;grid-template-columns:110px 1fr 38px;gap:8px;align-items:center;color:#dbeafe;font-size:11px;cursor:pointer}.dash-bar-row span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.dash-bar-track{height:10px;border-radius:999px;background:rgba(96,165,250,.12);overflow:hidden}.dash-bar-fill{height:100%;border-radius:999px;background:linear-gradient(90deg,#2563eb,#93c5fd)}.dash-bar-row b{text-align:right;color:#93c5fd}
      .dash-line{width:100%;height:230px}.dash-line text{fill:#9db2d4;font-size:10px}.dash-gridline{stroke:rgba(148,163,184,.18);stroke-width:1}.dash-line-path{fill:none;stroke:#93c5fd;stroke-width:3;stroke-linecap:round;stroke-linejoin:round}.dash-line-area{fill:rgba(37,99,235,.12)}.dash-line-point{fill:#bfdbfe;stroke:#081426;stroke-width:2}.dash-empty{min-height:130px;display:grid;place-items:center;text-align:center;color:#9db2d4;font-size:12px;line-height:1.4}
      .dash-tools{border:1px solid rgba(96,165,250,.16);background:rgba(16,32,57,.52);border-radius:18px;padding:12px;margin-bottom:12px}.dash-search{width:100%;border-radius:12px;border:1px solid rgba(96,165,250,.22);background:#081426;color:#eaf2ff;padding:11px 12px;outline:none;margin-bottom:10px}.dash-search:focus,.dash-select:focus{border-color:#93c5fd}.dash-filter-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:10px}.dash-select{width:100%;border-radius:12px;border:1px solid rgba(96,165,250,.22);background:#081426;color:#eaf2ff;padding:9px 10px;outline:none}.dash-actions{display:flex;align-items:center;justify-content:space-between;margin-top:10px;gap:8px}.dash-count{font-size:11px;color:#9db2d4;line-height:1.35}
      .dash-event-list{display:grid;gap:10px}.dash-event-card{border:1px solid rgba(96,165,250,.16);background:rgba(11,22,40,.84);border-radius:16px;padding:12px;cursor:pointer;transition:border-color .14s ease,background .14s ease}.dash-event-card:hover{border-color:rgba(147,197,253,.45);background:rgba(16,32,57,.9)}.dash-event-title{font-size:13px;font-weight:950;line-height:1.25}.dash-event-meta{display:flex;flex-wrap:wrap;gap:6px;margin-top:7px}.dash-pill{border:1px solid rgba(96,165,250,.16);background:rgba(15,35,64,.6);border-radius:999px;padding:3px 7px;font-size:10px;color:#bfdbfe;font-weight:850}.dash-event-desc{font-size:11px;color:#cbd5e1;line-height:1.38;margin-top:8px}.dash-detail{margin-top:10px;border-top:1px solid rgba(96,165,250,.14);padding-top:9px;display:grid;grid-template-columns:112px 1fr;gap:5px 10px;font-size:11px}.dash-detail span{color:#9db2d4}.dash-detail b{color:#eaf2ff;word-break:break-word}
      @media(max-width:900px){.dashboard-panel,.dock.expanded ~ .dashboard-panel{left:var(--dock-collapsed);right:0;top:0;bottom:0;width:auto}.dash-grid{grid-template-columns:1fr}.dash-chart-grid{grid-template-columns:1fr}.dash-filter-grid{grid-template-columns:1fr 1fr}.dash-donut-wrap{grid-template-columns:130px 1fr}}
      @media(max-width:520px){.dash-filter-grid{grid-template-columns:1fr}.dash-donut-wrap{grid-template-columns:1fr}.dash-grid{gap:8px}}
    `;
    document.head.appendChild(css);
  }

  function injectPanel() {
    if ($('dashboardPanel')) return;
    const panel = document.createElement('section');
    panel.id = 'dashboardPanel';
    panel.className = 'dashboard-panel';
    panel.setAttribute('aria-label', 'Dashboard de eventos');
    panel.setAttribute('aria-hidden', 'true');
    panel.innerHTML = `
      <header class="panel-head">
        <div>
          <div class="panel-eyebrow">Dashboard</div>
          <div class="panel-title">Análises internas</div>
          <div class="panel-subtitle">Gráficos e leitura histórica dos eventos registrados no site. Estes filtros não alteram o mapa.</div>
        </div>
        <button id="dashboardPanelClose" class="panel-close" type="button" aria-label="Fechar dashboard">×</button>
      </header>
      <div class="dash-tabs" role="tablist" aria-label="Páginas do dashboard">
        <button id="dashChartsTab" class="dash-tab active" type="button" data-dash-page="charts">Análises</button>
        <button id="dashEventsTab" class="dash-tab" type="button" data-dash-page="events">Eventos registrados</button>
      </div>
      <section id="dashChartsPage">
        <div id="dashKpis" class="dash-grid"></div>
        <div class="dash-chart-grid">
          <article class="dash-card"><div class="dash-card-head"><div class="dash-card-title">Eventos por tipo</div><div class="dash-card-note">Clique para filtrar a lista</div></div><div id="dashTypeDonut" class="dash-donut-wrap"></div></article>
          <article class="dash-card"><div class="dash-card-head"><div class="dash-card-title">Eventos por severidade</div><div class="dash-card-note">Distribuição histórica</div></div><div id="dashSeverityDonut" class="dash-donut-wrap"></div></article>
          <article class="dash-card"><div class="dash-card-head"><div class="dash-card-title">Regiões com mais eventos</div><div class="dash-card-note">Ranking</div></div><div id="dashRegionBars" class="dash-bar-list"></div></article>
          <article class="dash-card"><div class="dash-card-head"><div class="dash-card-title">Fontes principais</div><div class="dash-card-note">Origem dos registros</div></div><div id="dashSourceBars" class="dash-bar-list"></div></article>
          <article class="dash-card dash-wide"><div class="dash-card-head"><div class="dash-card-title">Evolução diária</div><div class="dash-card-note">Quantidade de eventos por dia</div></div><div id="dashDailyLine"></div></article>
        </div>
      </section>
      <section id="dashEventsPage" hidden>
        <section class="dash-tools" aria-label="Filtros do histórico">
          <input id="dashSearch" class="dash-search" type="search" placeholder="Pesquisar por evento, rodovia, cidade, fonte, descrição..." autocomplete="off">
          <div class="dash-filter-grid">
            <select id="dashType" class="dash-select"><option value="all">Todos os tipos</option></select>
            <select id="dashSeverity" class="dash-select"><option value="all">Todas as severidades</option></select>
            <select id="dashRegion" class="dash-select"><option value="all">Todas as regiões</option></select>
            <select id="dashSort" class="dash-select"><option value="recent">Mais recentes</option><option value="risk">Maior risco</option><option value="type">Tipo</option><option value="region">Região</option></select>
          </div>
          <div class="dash-actions"><div id="dashCount" class="dash-count">Carregando histórico...</div><button id="dashClear" class="filter-chip" type="button">Limpar</button></div>
        </section>
        <section id="dashEventList" class="dash-event-list" aria-label="Eventos registrados"></section>
      </section>
    `;
    const legend = document.querySelector('.legend');
    if (legend) legend.before(panel); else document.body.appendChild(panel);
  }

  function typeLabel(type) {
    return ({ climate: 'Clima', road: 'Rodovia', operational: 'Operacional', manual: 'Manual' })[type] || (type ? String(type) : 'Sem tipo');
  }

  function severityLabel(row) {
    const raw = String(row.severity || '').trim();
    if (raw) return raw;
    const risk = num(row.risk);
    if (risk >= 80) return 'Crítico';
    if (risk >= 60) return 'Alto';
    if (risk >= 35) return 'Moderado';
    if (risk > 0) return 'Baixo';
    return 'Sem risco';
  }

  function normalizeType(value) {
    const text = String(value || '').trim().toLowerCase();
    if (text === 'climate' || text === 'clima') return 'climate';
    if (text === 'road' || text === 'rodovia') return 'road';
    if (text === 'operational' || text === 'operacional') return 'operational';
    if (text === 'manual') return 'manual';
    return text || 'unknown';
  }

  function parseDate(value) {
    if (!value) return null;
    const date = new Date(String(value).replace(' ', 'T'));
    return Number.isNaN(date.getTime()) ? null : date;
  }

  function fmtDate(value) {
    const date = parseDate(value);
    return date ? date.toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', year: '2-digit', hour: '2-digit', minute: '2-digit' }) : String(value || '');
  }

  function normalizeRow(raw, index) {
    const type = normalizeType(raw.source_type || raw.type || raw.category);
    const date = raw.snapshot_at || raw.last_seen_at || raw.updated_at || raw.createdAt || raw.time || raw.newsDate || '';
    return {
      id: String(raw.stable_event_id || raw.event_id || raw.hash || `hist-${index}`),
      type,
      typeLabel: typeLabel(type),
      severity: severityLabel(raw),
      region: String(raw.region || raw.state || raw.uf || 'Sem região').trim() || 'Sem região',
      risk: Math.max(0, Math.min(100, num(raw.risk))),
      name: String(raw.name || raw.road || raw.event_type || raw.eventType || raw.headline || 'Evento registrado'),
      eventType: String(raw.event_type || raw.eventType || raw.category || typeLabel(type)),
      city: String(raw.city || raw.cidade || ''),
      state: String(raw.state || raw.uf || ''),
      road: String(raw.road || raw.corridor || ''),
      source: String(raw.source || raw.sourceProvider || raw.provider || ''),
      sourceUrl: String(raw.source_url || raw.sourceUrl || ''),
      description: String(raw.description || raw.summary || raw.headline || ''),
      date,
      dateObj: parseDate(date),
      lat: raw.lat,
      lon: raw.lon,
      raw,
    };
  }

  async function getJson(path) {
    try {
      const response = await fetch(`${path}?dashboard=${Date.now()}`, { cache: 'no-store' });
      return response.ok ? await response.json() : null;
    } catch (_) {
      return null;
    }
  }

  async function loadRows() {
    const cache = await getJson('data/analytics_cache.json');
    let rows = Array.isArray(cache?.rows) ? cache.rows : [];
    if (!rows.length) {
      const [climate, road, operational] = await Promise.all([
        getJson('data/climate_events.json'), getJson('data/road_events.json'), getJson('data/operational_alerts.json'),
      ]);
      rows = [];
      [['climate', climate], ['road', road], ['operational', operational]].forEach(([type, list]) => {
        (Array.isArray(list) ? list : []).forEach((item) => rows.push({ ...item, source_type: type, snapshot_at: item.updatedAt || item.time || new Date().toISOString() }));
      });
    }
    state.rows = rows.map(normalizeRow).filter((row) => row.name || row.description);
    populateFilters();
    renderAll();
  }

  function grouped(rows, keyFn) {
    const map = new Map();
    rows.forEach((row) => {
      const key = keyFn(row) || 'Sem classificação';
      map.set(key, (map.get(key) || 0) + 1);
    });
    return [...map.entries()].map(([label, count]) => ({ label, count })).sort((a, b) => b.count - a.count || a.label.localeCompare(b.label, 'pt-BR'));
  }

  function avg(values) {
    return values.length ? Math.round(values.reduce((a, b) => a + b, 0) / values.length) : 0;
  }

  function renderKpis() {
    const rows = state.rows;
    const risks = rows.map((r) => r.risk).filter((v) => Number.isFinite(v));
    const critical = rows.filter((r) => r.risk >= 80 || /cr[ií]tico/i.test(r.severity)).length;
    const lastDate = rows.map((r) => r.dateObj).filter(Boolean).sort((a, b) => b - a)[0];
    $('dashKpis').innerHTML = `
      <div class="dash-kpi"><span>Total registrado</span><b>${rows.length}</b><small>Eventos no histórico publicado</small></div>
      <div class="dash-kpi"><span>Risco médio</span><b>${avg(risks)}</b><small>Escala 0–100</small></div>
      <div class="dash-kpi"><span>Críticos</span><b>${critical}</b><small>${rows.length ? Math.round(critical / rows.length * 100) : 0}% dos registros</small></div>
      <div class="dash-kpi"><span>Regiões</span><b>${grouped(rows, r => r.region).length}</b><small>Regiões com eventos</small></div>
      <div class="dash-kpi"><span>Tipos</span><b>${grouped(rows, r => r.typeLabel).length}</b><small>Classes de eventos</small></div>
      <div class="dash-kpi"><span>Último registro</span><b>${lastDate ? lastDate.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit' }) : '—'}</b><small>${lastDate ? lastDate.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' }) : 'Sem data'}</small></div>
    `;
  }

  function donutPath(cx, cy, r0, r1, start, end) {
    const large = end - start > Math.PI ? 1 : 0;
    const a0 = start - Math.PI / 2;
    const a1 = end - Math.PI / 2;
    const p1 = [cx + r1 * Math.cos(a0), cy + r1 * Math.sin(a0)];
    const p2 = [cx + r1 * Math.cos(a1), cy + r1 * Math.sin(a1)];
    const p3 = [cx + r0 * Math.cos(a1), cy + r0 * Math.sin(a1)];
    const p4 = [cx + r0 * Math.cos(a0), cy + r0 * Math.sin(a0)];
    return `M ${p1[0]} ${p1[1]} A ${r1} ${r1} 0 ${large} 1 ${p2[0]} ${p2[1]} L ${p3[0]} ${p3[1]} A ${r0} ${r0} 0 ${large} 0 ${p4[0]} ${p4[1]} Z`;
  }

  function renderDonut(id, rows, colorFn, filterField) {
    const el = $(id);
    const total = rows.reduce((sum, row) => sum + row.count, 0);
    if (!total) { el.innerHTML = '<div class="dash-empty">Sem dados para exibir.</div>'; return; }
    let start = 0;
    const slices = rows.map((row, i) => {
      const angle = row.count / total * Math.PI * 2;
      const end = start + angle;
      const path = donutPath(75, 75, 42, 66, start, end - (Math.abs(angle - Math.PI * 2) < 0.00001 ? 0.0001 : 0));
      start = end;
      return `<path class="dash-slice" data-dash-filter="${filterField}" data-value="${esc(row.label)}" d="${path}" fill="${colorFn(row, i)}" style="cursor:pointer"></path>`;
    }).join('');
    const legend = rows.map((row, i) => `<button class="dash-legend" type="button" data-dash-filter="${filterField}" data-value="${esc(row.label)}"><i style="background:${colorFn(row, i)}"></i><span>${esc(row.label)}</span><b>${row.count}</b></button>`).join('');
    el.innerHTML = `<svg width="150" height="150" viewBox="0 0 150 150" aria-hidden="true">${slices}<text class="dash-donut-center" x="75" y="72" text-anchor="middle">${total}</text><text class="dash-donut-center" x="75" y="88" text-anchor="middle">eventos</text></svg><div class="dash-legend-list">${legend}</div>`;
  }

  function renderBars(id, rows, filterField) {
    const el = $(id);
    const top = rows.slice(0, 8);
    const max = Math.max(1, ...top.map((r) => r.count));
    if (!top.length) { el.innerHTML = '<div class="dash-empty">Sem dados para exibir.</div>'; return; }
    el.innerHTML = top.map((row) => `<div class="dash-bar-row" role="button" tabindex="0" data-dash-filter="${filterField}" data-value="${esc(row.label)}"><span>${esc(row.label)}</span><div class="dash-bar-track"><div class="dash-bar-fill" style="width:${Math.max(8, row.count / max * 100)}%"></div></div><b>${row.count}</b></div>`).join('');
  }

  function renderLine(rows) {
    const el = $('dashDailyLine');
    const byDay = grouped(rows.filter((r) => r.dateObj), (r) => r.dateObj.toISOString().slice(0, 10)).sort((a, b) => a.label.localeCompare(b.label)).slice(-30);
    if (!byDay.length) { el.innerHTML = '<div class="dash-empty">Sem datas suficientes para montar a evolução diária.</div>'; return; }
    const w = 690, h = 220, pad = 34;
    const max = Math.max(1, ...byDay.map((r) => r.count));
    const step = byDay.length > 1 ? (w - pad * 2) / (byDay.length - 1) : 0;
    const pts = byDay.map((row, i) => ({ ...row, x: byDay.length > 1 ? pad + i * step : w / 2, y: h - pad - (row.count / max) * (h - pad * 2) }));
    const line = pts.map((p) => `${p.x},${p.y}`).join(' ');
    const area = `M ${pts[0].x} ${h - pad} ` + pts.map((p) => `L ${p.x} ${p.y}`).join(' ') + ` L ${pts[pts.length - 1].x} ${h - pad} Z`;
    el.innerHTML = `<svg class="dash-line" viewBox="0 0 ${w} ${h}" role="img" aria-label="Evolução diária dos eventos">${[25, 50, 75, 100].map((pct) => { const y = h - pad - (pct / 100) * (h - pad * 2); return `<line class="dash-gridline" x1="${pad}" x2="${w - pad}" y1="${y}" y2="${y}"></line>`; }).join('')}<path class="dash-line-area" d="${area}"></path><polyline class="dash-line-path" points="${line}"></polyline>${pts.map((p) => `<circle class="dash-line-point" cx="${p.x}" cy="${p.y}" r="5"><title>${esc(p.label)}: ${p.count}</title></circle>`).join('')}${pts.filter((_, i) => i === 0 || i === pts.length - 1 || i % Math.ceil(pts.length / 6) === 0).map((p) => `<text x="${p.x}" y="${h - 8}" text-anchor="middle">${esc(p.label.slice(5))}</text>`).join('')}</svg>`;
  }

  function renderCharts() {
    renderKpis();
    renderDonut('dashTypeDonut', grouped(state.rows, (r) => r.typeLabel), (r) => typeColors[normalizeType(r.label)] || colors[0], 'typeLabel');
    renderDonut('dashSeverityDonut', grouped(state.rows, (r) => r.severity), (r, i) => severityColors[r.label] || colors[i % colors.length], 'severity');
    renderBars('dashRegionBars', grouped(state.rows, (r) => r.region), 'region');
    renderBars('dashSourceBars', grouped(state.rows, (r) => r.source || 'Sem fonte'), 'source');
    renderLine(state.rows);
  }

  function populateFilters() {
    const fill = (id, values, first) => {
      const select = $(id);
      if (!select) return;
      const current = select.value || 'all';
      select.innerHTML = `<option value="all">${first}</option>` + values.map((v) => `<option value="${esc(v)}">${esc(v)}</option>`).join('');
      select.value = values.includes(current) ? current : 'all';
    };
    fill('dashType', grouped(state.rows, (r) => r.typeLabel).map((r) => r.label), 'Todos os tipos');
    fill('dashSeverity', grouped(state.rows, (r) => r.severity).map((r) => r.label), 'Todas as severidades');
    fill('dashRegion', grouped(state.rows, (r) => r.region).map((r) => r.label), 'Todas as regiões');
  }

  function dashRows() {
    const f = state.filters;
    const query = f.query.toLowerCase();
    const textOf = (r) => [r.name, r.eventType, r.typeLabel, r.severity, r.region, r.city, r.state, r.road, r.source, r.description].join(' ').toLowerCase();
    let rows = state.rows.filter((r) =>
      (f.type === 'all' || r.typeLabel === f.type) &&
      (f.severity === 'all' || r.severity === f.severity) &&
      (f.region === 'all' || r.region === f.region) &&
      (!query || textOf(r).includes(query))
    );
    rows = [...rows];
    rows.sort((a, b) => f.sort === 'risk' ? b.risk - a.risk : f.sort === 'type' ? a.typeLabel.localeCompare(b.typeLabel, 'pt-BR') || b.risk - a.risk : f.sort === 'region' ? a.region.localeCompare(b.region, 'pt-BR') || b.risk - a.risk : (b.dateObj?.getTime?.() || 0) - (a.dateObj?.getTime?.() || 0));
    return rows;
  }

  function renderEventList() {
    const rows = dashRows();
    const list = $('dashEventList');
    $('dashCount').textContent = `${rows.length} de ${state.rows.length} registro(s)`;
    if (!rows.length) { list.innerHTML = '<div class="dash-empty">Nenhum evento encontrado para os filtros atuais.</div>'; return; }
    list.innerHTML = rows.slice(0, 300).map((row) => {
      const expanded = state.detailId === row.id;
      return `<article class="dash-event-card" tabindex="0" role="button" data-dash-event-id="${esc(row.id)}"><div class="dash-event-title">${esc(row.name)}</div><div class="dash-event-meta"><span class="dash-pill">${esc(row.typeLabel)}</span><span class="dash-pill">${esc(row.severity)}</span><span class="dash-pill">${esc(row.region)}</span><span class="dash-pill">Risco ${row.risk}</span>${row.road ? `<span class="dash-pill">${esc(row.road)}</span>` : ''}</div>${row.description ? `<div class="dash-event-desc">${esc(row.description).slice(0, 260)}</div>` : ''}${expanded ? detailHtml(row) : ''}</article>`;
    }).join('') + (rows.length > 300 ? '<div class="dash-empty">Mostrando os primeiros 300 registros. Refine a busca para ver menos eventos.</div>' : '');
  }

  function detailHtml(row) {
    const entries = [
      ['ID', row.id], ['Tipo', row.typeLabel], ['Evento', row.eventType], ['Severidade', row.severity], ['Risco', `${row.risk}/100`], ['Região', row.region], ['Cidade/UF', [row.city, row.state].filter(Boolean).join(' / ')], ['Rodovia', row.road], ['Fonte', row.source], ['Data', fmtDate(row.date)], ['Coordenadas', row.lat && row.lon ? `${row.lat}, ${row.lon}` : ''], ['URL', row.sourceUrl],
    ];
    return `<div class="dash-detail">${entries.filter(([, v]) => String(v || '').trim()).map(([k, v]) => `<span>${esc(k)}</span><b>${esc(v)}</b>`).join('')}</div>`;
  }

  function syncFilterInputs() {
    if ($('dashSearch')) $('dashSearch').value = state.filters.query;
    if ($('dashType')) $('dashType').value = state.filters.type;
    if ($('dashSeverity')) $('dashSeverity').value = state.filters.severity;
    if ($('dashRegion')) $('dashRegion').value = state.filters.region;
    if ($('dashSort')) $('dashSort').value = state.filters.sort;
  }

  function renderAll() {
    populateFilters();
    syncFilterInputs();
    renderCharts();
    renderEventList();
  }

  function setPage(page) {
    state.page = page;
    $('dashChartsPage').hidden = page !== 'charts';
    $('dashEventsPage').hidden = page !== 'events';
    $('dashChartsTab').classList.toggle('active', page === 'charts');
    $('dashEventsTab').classList.toggle('active', page === 'events');
  }

  function setDashboard(open) {
    document.body.classList.toggle('dashboard-panel-open', open);
    const panel = $('dashboardPanel');
    if (panel) panel.setAttribute('aria-hidden', String(!open));
    if (state.dashboardButton) {
      state.dashboardButton.classList.toggle('active', open);
      state.dashboardButton.setAttribute('aria-expanded', String(open));
    }
    if (open) {
      document.body.classList.remove('map-panel-open', 'reader-panel-open');
      const mapBtn = $('mapPanelToggle');
      const readerBtn = $('readerPanelToggle');
      if (mapBtn) { mapBtn.classList.remove('active'); mapBtn.setAttribute('aria-expanded', 'false'); }
      if (readerBtn) { readerBtn.classList.remove('active'); readerBtn.setAttribute('aria-expanded', 'false'); }
      loadRows();
    }
  }

  function attachEvents() {
    const button = document.querySelector('.nav-item[title="Dashboard"]');
    if (button) {
      button.id = button.id || 'dashboardPanelToggle';
      button.setAttribute('role', 'button');
      button.setAttribute('tabindex', '0');
      button.setAttribute('aria-controls', 'dashboardPanel');
      button.setAttribute('aria-expanded', 'false');
      button.addEventListener('click', () => setDashboard(!document.body.classList.contains('dashboard-panel-open')));
      button.addEventListener('keydown', (event) => {
        if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); button.click(); }
      });
      state.dashboardButton = button;
    }
    $('dashboardPanelClose').addEventListener('click', () => setDashboard(false));
    document.querySelectorAll('[data-dash-page]').forEach((el) => el.addEventListener('click', () => setPage(el.dataset.dashPage)));
    ['dashType', 'dashSeverity', 'dashRegion', 'dashSort'].forEach((id) => $(id).addEventListener('change', () => { state.filters[id.replace('dash', '').toLowerCase()] = $(id).value; renderEventList(); }));
    $('dashSearch').addEventListener('input', () => { state.filters.query = $('dashSearch').value.trim(); renderEventList(); });
    $('dashClear').addEventListener('click', () => { state.filters = { type: 'all', severity: 'all', region: 'all', query: '', sort: 'recent' }; state.detailId = ''; syncFilterInputs(); renderEventList(); });
    document.addEventListener('click', (event) => {
      const filter = event.target.closest('[data-dash-filter]');
      if (filter) {
        const field = filter.dataset.dashFilter;
        const value = filter.dataset.value;
        if (field === 'typeLabel') state.filters.type = state.filters.type === value ? 'all' : value;
        if (field === 'severity') state.filters.severity = state.filters.severity === value ? 'all' : value;
        if (field === 'region') state.filters.region = state.filters.region === value ? 'all' : value;
        if (field === 'source') state.filters.query = state.filters.query === value ? '' : value;
        syncFilterInputs();
        setPage('events');
        renderEventList();
        return;
      }
      const card = event.target.closest('[data-dash-event-id]');
      if (card) {
        const id = card.dataset.dashEventId;
        state.detailId = state.detailId === id ? '' : id;
        renderEventList();
      }
    });
    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape' && document.body.classList.contains('dashboard-panel-open')) setDashboard(false);
      if ((event.key === 'Enter' || event.key === ' ') && event.target.matches('[data-dash-event-id]')) { event.preventDefault(); event.target.click(); }
    });
  }

  function init() {
    injectCss();
    injectPanel();
    attachEvents();
    loadRows();
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
  else init();
})();
