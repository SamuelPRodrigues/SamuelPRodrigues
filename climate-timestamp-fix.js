(() => {
  const escapeHtml = (value) => String(value ?? '').replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[c]));

  function firstValue(obj, keys) {
    for (const key of keys) {
      if (obj && obj[key] !== undefined && obj[key] !== null && String(obj[key]).trim() !== '') return obj[key];
    }
    return '';
  }

  function fmtDate(value) {
    if (!value) return '';
    const date = new Date(value);
    return Number.isNaN(date.getTime())
      ? String(value)
      : date.toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', year: '2-digit', hour: '2-digit', minute: '2-digit' });
  }

  function severityFromRisk(risk) {
    const value = Number(risk) || 0;
    if (value >= 70) return 'Crítica';
    if (value >= 50) return 'Alta';
    if (value >= 30) return 'Moderada';
    return 'Baixa';
  }

  function typeLabel(type) {
    return type === 'road' ? 'Rodovia' : type === 'operational' ? 'Operacional' : 'Clima';
  }

  function regionOf(ev) {
    const raw = ev.raw || {};
    return String(firstValue(raw, ['region', 'regiao', 'state', 'uf', 'estado', 'city', 'municipality', 'cidade']) || 'Sem região').trim();
  }

  function detailRowsFixed(ev) {
    const raw = ev.raw || {};
    const current = raw.current || {};
    const place = [
      firstValue(raw, ['city', 'municipality', 'cidade']),
      firstValue(raw, ['state', 'uf', 'estado']),
      firstValue(raw, ['region', 'regiao']),
    ].filter(Boolean).join(' • ');

    const updatedAt = firstValue(raw, [
      'last_seen_at', 'lastSeenAt', 'updatedAt', 'updated_at', 'snapshot_at', 'snapshotAt',
      'createdAt', 'created_at', 'time', 'newsDate'
    ]);
    const observedAt = firstValue(current, ['time']) || firstValue(raw, ['time']);

    const rows = [
      ['Tipo', typeLabel(ev.type)],
      ['Severidade', severityFromRisk(ev.risk)],
      ['Risco', `${ev.risk}/100`],
      ['Local', place || regionOf(ev)],
      ['Coordenadas', `${ev.lat.toFixed(4)}, ${ev.lon.toFixed(4)}`],
      ['Categoria', firstValue(raw, ['category', 'event_type', 'eventType', 'type'])],
      ['Rodovia', firstValue(raw, ['road', 'corridor', 'highway', 'route'])],
      ['Fonte', firstValue(raw, ['source', 'provider', 'origin'])],
      ['Atualizado', fmtDate(updatedAt)],
    ];

    if (ev.type === 'climate' && observedAt && observedAt !== updatedAt) rows.push(['Observação', fmtDate(observedAt)]);
    if (current.temperature_2m !== undefined) rows.push(['Temperatura', `${current.temperature_2m} °C`]);
    if (current.precipitation !== undefined) rows.push(['Chuva', `${current.precipitation} mm`]);
    if (current.wind_speed_10m !== undefined) rows.push(['Vento', `${current.wind_speed_10m} km/h`]);

    return rows
      .filter(([, value]) => value !== undefined && value !== null && String(value).trim() !== '')
      .map(([key, value]) => `<span>${escapeHtml(key)}</span><b>${escapeHtml(value)}</b>`)
      .join('');
  }

  function addBulletinNavStyles() {
    if (document.getElementById('bulletinNavStyles')) return;
    const style = document.createElement('style');
    style.id = 'bulletinNavStyles';
    style.textContent = `
      .dock .nav{display:flex;flex-direction:column;flex:1;gap:10px;width:100%}
      .nav-item.bulletin-nav{margin-top:auto}
      .dock.expanded .nav-item.bulletin-nav{margin-top:auto}
      .bulletin-icon{-webkit-mask-image:url('assets/icons/Boletim.png');mask-image:url('assets/icons/Boletim.png')}
    `;
    document.head.appendChild(style);
  }

  function addBulletinButton() {
    const nav = document.querySelector('#dock .nav');
    if (!nav || document.getElementById('bulletinNav')) return;
    const button = document.createElement('button');
    button.id = 'bulletinNav';
    button.className = 'nav-item bulletin-nav';
    button.type = 'button';
    button.title = 'Boletim';
    button.setAttribute('aria-label', 'Abrir boletim de notícias');
    button.innerHTML = '<span class="nav-icon bulletin-icon"></span><span class="nav-label">Boletim</span>';
    button.addEventListener('click', () => {
      window.location.href = 'boletim.html';
    });
    nav.appendChild(button);
  }

  function initBulletinNav() {
    addBulletinNavStyles();
    addBulletinButton();
  }

  try {
    window.detailRows = detailRowsFixed;
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', initBulletinNav, { once: true });
    } else {
      initBulletinNav();
    }
  } catch (_) {}
})();
