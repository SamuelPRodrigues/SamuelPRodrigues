(() => {
  const state = {
    loaded: false,
    byId: new Map(),
    bySignature: new Map(),
  };

  const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[c]));

  function addStyles() {
    if (document.getElementById('dashboardSourceLinksStyles')) return;
    const style = document.createElement('style');
    style.id = 'dashboardSourceLinksStyles';
    style.textContent = `
      .dash-detail a,.dash-source-list a{color:#93c5fd;text-decoration:none;font-weight:950;overflow-wrap:anywhere}.dash-detail a:hover,.dash-source-list a:hover{color:#dbeafe;text-decoration:underline}.dash-source-list{grid-column:1/-1;margin-top:10px;border-top:1px solid rgba(96,165,250,.14);padding-top:10px}.dash-source-list-title{font-size:11px;color:#dbeafe;font-weight:950;margin-bottom:8px}.dash-source-item{border:1px solid rgba(96,165,250,.14);background:rgba(15,35,64,.38);border-radius:12px;padding:8px;margin-top:7px}.dash-source-name{display:flex;align-items:center;gap:6px;flex-wrap:wrap;font-size:11px}.dash-source-meta{font-size:10px;color:#9db2d4;margin-top:4px;line-height:1.35}.dash-source-headline{font-size:11px;color:#cbd5e1;margin-top:5px;line-height:1.35}.dash-source-empty{grid-column:1/-1;color:#9db2d4;font-size:11px;margin-top:8px}`;
    document.head.appendChild(style);
  }

  async function fetchJson(path) {
    try {
      const response = await fetch(`${path}?sources=${Date.now()}`, { cache: 'no-store' });
      return response.ok ? await response.json() : null;
    } catch (_) {
      return null;
    }
  }

  function text(value) {
    return String(value ?? '').trim();
  }

  function idKeys(row) {
    return [row?.stable_event_id, row?.event_id, row?.hash, row?.id].map(text).filter(Boolean);
  }

  function rowSignature(row) {
    return [row?.name, row?.road, row?.region, row?.source_type || row?.type].map(text).join('|').toLowerCase();
  }

  function sourceScore(item) {
    const haystack = `${item.source || ''} ${item.url || ''}`.toLowerCase();
    if (/gov\.br|dnit|antt|prf|defesa civil/.test(haystack)) return 100;
    if (/g1|globo|folha|estadao|estadão|uol|r7|cnn|band/.test(haystack)) return 80;
    if (/portal|not[ií]cias|jornal/.test(haystack)) return 55;
    return 40;
  }

  function normalizeSource(item, fallback = {}) {
    if (!item || typeof item !== 'object') return null;
    const source = text(item.source || item.name || item.provider || fallback.source || 'Fonte pública');
    const url = text(item.url || item.source_url || item.sourceUrl || fallback.url || '');
    const headline = text(item.headline || item.title || item.description || fallback.headline || '');
    const date = text(item.date || item.published || item.newsDate || fallback.date || '');
    if (!source && !url && !headline) return null;
    return { source, url, headline, date, score: Number(item.score || item._rank || sourceScore({ source, url })) };
  }

  function sourcesFor(row) {
    const sources = [];
    const raw = row?.sources || row?.sourceList || row?.raw?.sources || row?.raw?.sourceList || [];
    if (Array.isArray(raw)) {
      raw.forEach((item) => {
        const normalized = normalizeSource(item);
        if (normalized) sources.push(normalized);
      });
    }
    const primary = normalizeSource({
      source: row?.source || row?.sourceProvider || row?.provider,
      url: row?.source_url || row?.sourceUrl,
      headline: row?.headline || row?.description || row?.name,
      date: row?.newsDate || row?.updated_at || row?.updatedAt || row?.snapshot_at,
    });
    if (primary) sources.push(primary);

    const dedup = new Map();
    sources.forEach((item) => {
      const key = item.url || `${item.source}|${item.headline}`;
      const current = dedup.get(key);
      if (!current || item.score > current.score) dedup.set(key, item);
    });
    return [...dedup.values()].sort((a, b) => (b.score - a.score) || String(b.date).localeCompare(String(a.date)));
  }

  function ingest(row) {
    if (!row || typeof row !== 'object') return;
    const existing = idKeys(row).map((key) => state.byId.get(key)).find(Boolean);
    const merged = existing ? { ...row, ...existing, sources: [...sourcesFor(row), ...sourcesFor(existing)] } : row;
    idKeys(merged).forEach((key) => state.byId.set(key, merged));
    const signature = rowSignature(merged);
    if (signature && signature !== '|||') state.bySignature.set(signature, merged);
  }

  async function loadData() {
    if (state.loaded) return;
    const payloads = await Promise.all([
      fetchJson('data/analytics_cache.json'),
      fetchJson('data/supabase_analytics_cache.json'),
      fetchJson('data/road_events.json'),
      fetchJson('data/manual_events.json'),
      fetchJson('data/deactivated_events.json'),
    ]);
    payloads.forEach((payload) => {
      const rows = Array.isArray(payload) ? payload : Array.isArray(payload?.rows) ? payload.rows : [];
      rows.forEach(ingest);
    });
    state.loaded = true;
  }

  function findDetailPair(detail, label) {
    const children = [...detail.children];
    for (let i = 0; i < children.length - 1; i += 1) {
      if (children[i].tagName === 'SPAN' && children[i].textContent.trim().toLowerCase() === label.toLowerCase()) {
        return children[i + 1];
      }
    }
    return null;
  }

  function urlAnchor(url, label = 'Abrir fonte principal') {
    if (!/^https?:\/\//i.test(url)) return esc(url);
    return `<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(label)}</a>`;
  }

  function articleHtml(item, index) {
    const label = item.url ? `Artigo ${index + 1}` : `Fonte ${index + 1}`;
    const link = item.url ? `<a href="${esc(item.url)}" target="_blank" rel="noopener noreferrer">${esc(label)}</a>` : `<strong>${esc(label)}</strong>`;
    return `<div class="dash-source-item"><div class="dash-source-name">${link}<span>· ${esc(item.source || 'Fonte pública')}</span></div>${item.date ? `<div class="dash-source-meta">${esc(item.date)}</div>` : ''}${item.headline ? `<div class="dash-source-headline">${esc(item.headline)}</div>` : ''}</div>`;
  }

  function enhanceCard(card) {
    const detail = card.querySelector('.dash-detail');
    if (!detail) return;
    const id = card.dataset.dashEventId;
    const row = state.byId.get(id) || state.bySignature.get(rowSignature({
      name: card.querySelector('.dash-event-title')?.textContent,
      road: [...card.querySelectorAll('.dash-pill')].map((el) => el.textContent).find((value) => /^BR-|^[A-Z]{2}-\d/i.test(value)),
    }));
    if (!row) return;

    const urlCell = findDetailPair(detail, 'URL');
    const url = text(row.source_url || row.sourceUrl || row.raw?.source_url || row.raw?.sourceUrl || urlCell?.textContent);
    if (urlCell && url && !urlCell.querySelector('a')) {
      urlCell.innerHTML = urlAnchor(url);
    }

    if (detail.querySelector('.dash-source-list')) return;
    const sources = sourcesFor(row);
    if (!sources.length) {
      const empty = document.createElement('div');
      empty.className = 'dash-source-empty';
      empty.textContent = 'Nenhum artigo consolidado foi encontrado para este evento.';
      detail.appendChild(empty);
      return;
    }
    const section = document.createElement('div');
    section.className = 'dash-source-list';
    section.innerHTML = `<div class="dash-source-list-title">Artigos usados neste evento (${sources.length})</div>${sources.map(articleHtml).join('')}`;
    detail.appendChild(section);
  }

  async function enhanceDashboard() {
    addStyles();
    await loadData();
    document.querySelectorAll('[data-dash-event-id]').forEach(enhanceCard);
  }

  function observe() {
    const observer = new MutationObserver(() => enhanceDashboard());
    observer.observe(document.body, { childList: true, subtree: true });
    document.addEventListener('click', () => setTimeout(enhanceDashboard, 50));
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => { enhanceDashboard(); observe(); });
  } else {
    enhanceDashboard();
    observe();
  }
})();
