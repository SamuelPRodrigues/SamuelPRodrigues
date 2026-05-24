(()=>{
  document.querySelectorAll('#dbOpen,#dbModal,#analyticsDashboardOpen,#analyticsDashboardModal,#advOpen,#advModal,.db-open,.db-modal').forEach(el=>el.remove());
  const old = document.querySelector('script[data-analytics-v3="true"]');
  if (old) old.remove();
  if (document.querySelector('script[data-site-redesign="true"]')) return;
  const script = document.createElement('script');
  script.src = 'site-redesign.js?v=1';
  script.defer = true;
  script.dataset.siteRedesign = 'true';
  document.body.appendChild(script);
})();
