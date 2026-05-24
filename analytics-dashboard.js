(()=>{
  document.querySelectorAll('#dbOpen,#dbModal,#analyticsDashboardOpen,#analyticsDashboardModal,#advOpen,#advModal,.db-open,.db-modal').forEach(el=>el.remove());
  const old = document.querySelector('script[data-analytics-v3="true"]');
  if (old) old.remove();

  function load(src, flag) {
    if (document.querySelector(`script[data-${flag}="true"]`)) return;
    const script = document.createElement('script');
    script.src = src;
    script.defer = true;
    script.dataset[flag.replace(/-([a-z])/g, (_, c) => c.toUpperCase())] = 'true';
    document.body.appendChild(script);
  }

  function css(src,id){
    if(document.getElementById(id)) return;
    const link=document.createElement('link');
    link.id=id;
    link.rel='stylesheet';
    link.href=src;
    document.head.appendChild(link);
  }

  load('site-redesign.js?v=2', 'site-redesign');
  load('site-redesign-enhance.js?v=5', 'site-redesign-enhance');
  css('site-redesign-hotfix.css?v=1','site-redesign-hotfix');
})();