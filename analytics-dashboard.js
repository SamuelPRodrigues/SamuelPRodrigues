(()=>{
  document.querySelectorAll('#dbOpen,#dbModal,#analyticsDashboardOpen,#analyticsDashboardModal,.db-open,.db-modal').forEach(el=>el.remove());
  const existing=document.querySelector('script[data-analytics-v3="true"]');
  if(existing) return;
  const script=document.createElement('script');
  script.src='analytics-dashboard-v3.js?v=1';
  script.defer=true;
  script.dataset.analyticsV3='true';
  document.body.appendChild(script);
})();
