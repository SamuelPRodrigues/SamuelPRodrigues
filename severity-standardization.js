(() => {
  const severityFromRisk = (risk) => {
    const value = Number(risk) || 0;
    if (value >= 70) return 'Crítico';
    if (value >= 50) return 'Alto';
    if (value >= 30) return 'Moderado';
    if (value >= 1) return 'Baixo';
    return 'Sem risco';
  };

  const severityKeyFromRisk = (risk) => {
    const value = Number(risk) || 0;
    if (value >= 70) return 'critical';
    if (value >= 50) return 'high';
    if (value >= 30) return 'moderate';
    if (value >= 1) return 'low';
    return 'none';
  };

  function standardizeRow(row) {
    if (!row || typeof row !== 'object' || Array.isArray(row)) return row;
    const risk = Number(row.risk);
    if (Number.isFinite(risk)) {
      row.severity = severityFromRisk(risk);
      row.severity_key = severityKeyFromRisk(risk);
      row.severityStandard = 'Crítico >=70; Alto 50-69; Moderado 30-49; Baixo 1-29; Sem risco 0';
    }
    return row;
  }

  function standardizePayload(payload) {
    if (Array.isArray(payload)) return payload.map((item) => standardizePayload(item));
    if (!payload || typeof payload !== 'object') return payload;
    if (Array.isArray(payload.rows)) payload.rows = payload.rows.map((item) => standardizePayload(item));
    return standardizeRow(payload);
  }

  window.__eventSeverityFromRisk = severityFromRisk;
  window.__eventSeverityKeyFromRisk = severityKeyFromRisk;

  const originalFetch = window.fetch;
  if (typeof originalFetch === 'function' && !window.__severityFetchPatchInstalled) {
    window.__severityFetchPatchInstalled = true;
    window.fetch = async (...args) => {
      const response = await originalFetch(...args);
      const url = String(args[0]?.url || args[0] || '');
      const isDataFile = /(^|\/)data\/.+\.json/i.test(url);
      if (!isDataFile || typeof response.json !== 'function') return response;
      const originalJson = response.json.bind(response);
      response.json = async () => standardizePayload(await originalJson());
      return response;
    };
  }
})();
