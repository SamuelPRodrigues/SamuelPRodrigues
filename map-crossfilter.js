(() => {
  function get(id) { return document.getElementById(id); }
  function safe(fn, fallback) { try { return fn(); } catch (_) { return fallback; } }
  function currentFilters() {
    return {
      type: get('filterType')?.value || 'all',
      severity: get('filterSeverity')?.value || 'critical',
      region: get('filterRegion')?.value || 'all',
    };
  }
  function eventSeverity(ev) {
    if (typeof severityOf === 'function') return severityOf(ev.risk);
    const value = Number(ev.risk) || 0;
    if (value >= 70) return 'critical';
    if (value >= 50) return 'high';
    if (value >= 30) return 'moderate';
    return 'low';
  }
  function eventRegion(ev) {
    if (typeof regionOf === 'function') return regionOf(ev);
    const raw = ev.raw || {};
    return String(raw.region || raw.regiao || raw.state || raw.uf || raw.city || 'Sem região').trim();
  }
  function eventMatches(ev, filters, ignore) {
    return (ignore === 'type' || filters.type === 'all' || ev.type === filters.type) &&
      (ignore === 'severity' || filters.severity === 'all' || eventSeverity(ev) === filters.severity) &&
      (ignore === 'region' || filters.region === 'all' || eventRegion(ev) === filters.region);
  }
  function rowsFor(events, ignore) {
    const filters = currentFilters();
    return (events || []).filter((ev) => eventMatches(ev, filters, ignore));
  }
  function countRows(events, values, labeler, field) {
    return values.map((value) => ({
      value,
      label: labeler(value),
      count: events.filter((ev) => field(ev) === value).length,
    })).filter((row) => row.count > 0);
  }
  function groupedRegions(events) {
    const map = new Map();
    events.forEach((ev) => {
      const key = eventRegion(ev);
      const row = map.get(key) || { value: key, label: key, count: 0, totalRisk: 0 };
      row.count += 1;
      row.totalRisk += Number(ev.risk) || 0;
      map.set(key, row);
    });
    return [...map.values()]
      .map((row) => ({ ...row, avgRisk: row.count ? row.totalRisk / row.count : 0 }))
      .sort((a, b) => b.count - a.count || b.avgRisk - a.avgRisk);
  }
  function esc(value) {
    return String(value ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
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
  function renderDonut(id, rows, filterKey, activeValue, colors) {
    const el = get(id);
    if (!el) return;
    const total = rows.reduce((sum, row) => sum + row.count, 0);
    if (!total) {
      el.innerHTML = '<div class="empty-chart">Sem eventos para este recorte.</div>';
      return;
    }
    let start = 0;
    const palette = ['#60a5fa', '#f97316', '#a855f7', '#22c55e', '#f59e0b'];
    const slices = rows.map((row, i) => {
      const angle = (row.count / total) * Math.PI * 2;
      const end = start + angle;
      const active = row.value === activeValue;
      const color = colors[row.value] || palette[i % palette.length];
      const path = donutPath(66, 66, 35, 58, start, end - (Math.abs(angle - Math.PI * 2) < 0.00001 ? 0.0001 : 0));
      start = end;
      return `<path class="chart-slice ${active ? 'active' : ''}" tabindex="0" role="button" aria-label="${esc(row.label)}: ${row.count}" data-filter="${filterKey}" data-value="${esc(row.value)}" d="${path}" fill="${color}"></path>`;
    }).join('');
    const legend = rows.map((row, i) => {
      const color = colors[row.value] || palette[i % palette.length];
      const active = row.value === activeValue;
      return `<button class="chart-legend ${active ? 'active' : ''}" type="button" data-filter="${filterKey}" data-value="${esc(row.value)}"><i style="background:${color}"></i><span>${esc(row.label)}</span><b>${row.count}</b></button>`;
    }).join('');
    el.innerHTML = `<svg width="132" height="132" viewBox="0 0 132 132" aria-hidden="true">${slices}<text class="donut-center" x="66" y="63" text-anchor="middle">${total}</text><text class="donut-center" x="66" y="78" text-anchor="middle">eventos</text></svg><div class="chart-legend-list">${legend}</div>`;
  }
  function renderRegionLine(events, activeRegion) {
    const el = get('regionLine');
    if (!el) return;
    const rows = groupedRegions(events).slice(0, 6).sort((a, b) => a.label.localeCompare(b.label, 'pt-BR'));
    if (!rows.length) {
      el.innerHTML = '<div class="empty-chart">Sem regiões para este recorte.</div>';
      return;
    }
    const w = 360, h = 168, pad = 28;
    const step = rows.length > 1 ? (w - pad * 2) / (rows.length - 1) : 0;
    const points = rows.map((row, i) => {
      const x = rows.length > 1 ? pad + i * step : w / 2;
      const y = h - pad - (row.avgRisk / 100) * (h - pad * 2);
      return { ...row, x, y };
    });
    const area = `M ${points[0].x} ${h - pad} ` + points.map((p) => `L ${p.x} ${p.y}`).join(' ') + ` L ${points[points.length - 1].x} ${h - pad} Z`;
    const line = points.map((p) => `${p.x},${p.y}`).join(' ');
    el.innerHTML = `<svg class="line-chart" viewBox="0 0 ${w} ${h}" role="img" aria-label="Risco médio por região">${[25, 50, 75].map((v) => `<line class="line-grid" x1="${pad}" x2="${w - pad}" y1="${h - pad - (v / 100) * (h - pad * 2)}" y2="${h - pad - (v / 100) * (h - pad * 2)}"></line><text x="4" y="${h - pad - (v / 100) * (h - pad * 2) + 3}">${v}</text>`).join('')}<path class="line-area" d="${area}"></path><polyline class="line-path" points="${line}"></polyline>${points.map((p) => `<circle class="line-point ${activeRegion === p.value ? 'active' : ''}" tabindex="0" role="button" aria-label="${esc(p.label)}: risco médio ${Math.round(p.avgRisk)}" data-filter="region" data-value="${esc(p.value)}" cx="${p.x}" cy="${p.y}" r="6"></circle>`).join('')}${points.map((p) => `<text x="${p.x}" y="${h - 8}" text-anchor="middle">${esc(String(p.label).slice(0, 8))}</text>`).join('')}</svg>`;
  }
  function renderRegionBars(events, activeRegion) {
    const el = get('regionBars');
    if (!el) return;
    const rows = groupedRegions(events).slice(0, 8);
    const max = Math.max(1, ...rows.map((r) => r.count));
    if (!rows.length) {
      el.innerHTML = '<div class="empty-chart">Nenhuma região encontrada.</div>';
      return;
    }
    el.innerHTML = rows.map((row) => `<button class="region-row ${activeRegion === row.value ? 'active' : ''}" type="button" data-filter="region" data-value="${esc(row.value)}"><span>${esc(row.label)}</span><div class="region-track"><div class="region-fill" style="width:${Math.max(8, (row.count / max) * 100)}%"></div></div><b>${row.count}</b></button>`).join('');
  }
  function updateSummary(visible, total) {
    const f = currentFilters();
    const typeText = f.type === 'all' ? 'todos os tipos' : safe(() => typeLabel(f.type), f.type);
    const sevText = f.severity === 'all' ? 'todas as severidades' : safe(() => severityLabel(f.severity).toLowerCase(), f.severity);
    const regionText = f.region === 'all' ? 'todas as regiões' : f.region;
    const el = get('filterSummary');
    if (el) el.textContent = `${visible.length} de ${total} evento(s) · ${typeText}, ${sevText}, ${regionText}`;
  }
  function install() {
    if (window.__mapCrossFilterInstalled) return;
    window.__mapCrossFilterInstalled = true;

    if (typeof window.setFilter === 'function' || typeof setFilter === 'function') {
      window.setFilter = setFilter = function mapCrossFilterSetFilter(key, value) {
        const select = key === 'type' ? get('filterType') : key === 'severity' ? get('filterSeverity') : key === 'region' ? get('filterRegion') : null;
        if (!select) return;
        const next = select.value === value ? 'all' : value;
        if ([...select.options].some((option) => option.value === next)) select.value = next;
        if (typeof applyFilters === 'function') applyFilters({ fit: true });
      };
    }

    if (typeof window.renderPanelCharts === 'function' || typeof renderPanelCharts === 'function') {
      window.renderPanelCharts = renderPanelCharts = function mapCrossFilterRenderPanelCharts(source, visible) {
        const f = currentFilters();
        const typeRows = countRows(rowsFor(source, 'type'), ['climate', 'road', 'operational'], safe(() => typeLabel, (x) => x), (ev) => ev.type);
        const severityRows = countRows(rowsFor(source, 'severity'), ['critical', 'high', 'moderate', 'low'], safe(() => severityLabel, (x) => x), (ev) => eventSeverity(ev));
        const regionRows = rowsFor(source, 'region');
        renderDonut('typeDonut', typeRows, 'type', f.type, { climate: '#f97316', road: '#3b82f6', operational: '#a855f7' });
        renderDonut('severityDonut', severityRows, 'severity', f.severity, { critical: '#ef4444', high: '#f59e0b', moderate: '#3b82f6', low: '#22c55e' });
        renderRegionLine(regionRows, f.region);
        renderRegionBars(regionRows, f.region);
        updateSummary(visible || rowsFor(source), (source || []).length);
      };
    }
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', install);
  else install();
})();
