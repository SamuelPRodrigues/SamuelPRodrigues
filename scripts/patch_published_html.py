#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

path = Path("index.html")
text = path.read_text(encoding="utf-8")


def replace(old: str, new: str) -> None:
    global text
    text = text.replace(old, new)


# Painel do mapa acoplado à barra lateral, com cantos retos.
map_panel_css = ".map-panel{position:fixed;z-index:970;left:var(--dock-collapsed);top:0;bottom:0;width:min(430px,calc(100vw - var(--dock-collapsed)));background:rgba(7,17,32,.98);border:1px solid rgba(96,165,250,.24);border-left:0;border-radius:0;color:var(--text);box-shadow:18px 0 70px rgba(0,0,0,.34);backdrop-filter:blur(16px);padding:16px;overflow:auto;opacity:0;pointer-events:none;transform:translateX(-100%);transition:opacity .18s ease,transform .18s ease,left .22s ease,width .22s ease}.dock.expanded + .map-panel{left:var(--dock-expanded);width:min(430px,calc(100vw - var(--dock-expanded)))}"
replace(
    ".map-panel{position:fixed;z-index:970;left:calc(var(--dock-collapsed) + 12px);top:12px;bottom:12px;width:min(430px,calc(100vw - 104px));background:rgba(7,17,32,.95);border:1px solid rgba(96,165,250,.24);border-radius:22px;color:var(--text);box-shadow:0 24px 70px rgba(0,0,0,.34);backdrop-filter:blur(16px);padding:16px;overflow:auto;opacity:0;pointer-events:none;transform:translateX(-12px);transition:opacity .18s ease,transform .18s ease,left .22s ease}.dock.expanded + .map-panel{left:calc(var(--dock-expanded) + 12px)}",
    map_panel_css,
)
replace(
    ".map-panel{position:fixed;z-index:970;left:var(--dock-collapsed);top:0;bottom:0;width:min(430px,calc(100vw - var(--dock-collapsed)));background:rgba(7,17,32,.98);border:1px solid rgba(96,165,250,.24);border-left:0;border-radius:0 22px 22px 0;color:var(--text);box-shadow:18px 0 70px rgba(0,0,0,.34);backdrop-filter:blur(16px);padding:16px;overflow:auto;opacity:0;pointer-events:none;transform:translateX(-100%);transition:opacity .18s ease,transform .18s ease,left .22s ease,width .22s ease}.dock.expanded + .map-panel{left:var(--dock-expanded);width:min(430px,calc(100vw - var(--dock-expanded)))}",
    map_panel_css,
)
replace(
    "@media(max-width:760px){.dock.expanded{width:min(220px,72vw)}.map-panel,.dock.expanded + .map-panel{left:calc(var(--dock-collapsed) + 8px);right:8px;top:8px;bottom:8px;width:auto;padding:13px}.donut-wrap{grid-template-columns:116px 1fr}.legend{right:10px;bottom:88px;width:calc(100vw - 92px);padding:12px}}",
    "@media(max-width:760px){.dock.expanded{width:var(--dock-collapsed);align-items:center}.dock.expanded .nav-item{width:48px;justify-content:center;padding:0;margin:0 auto}.dock.expanded .nav-label{display:none}.map-panel,.dock.expanded + .map-panel,.reader-panel,.dock.expanded + .map-panel + .reader-panel{left:var(--dock-collapsed);right:0;top:0;bottom:0;width:auto;border-radius:0;padding:13px}.donut-wrap{grid-template-columns:116px 1fr}.legend{right:10px;bottom:88px;width:calc(100vw - 92px);padding:12px}}",
)
replace("border-radius:0 18px 18px 0;padding:13px", "border-radius:0;padding:13px")

# CSS adicional: scrollbar suave + painel Leitura.
if ".reader-panel{position:fixed" not in text:
    extra_css = """.map-panel,.reader-panel{scrollbar-width:thin;scrollbar-color:rgba(147,197,253,.42) rgba(7,17,32,.32)}.map-panel::-webkit-scrollbar,.reader-panel::-webkit-scrollbar{width:10px}.map-panel::-webkit-scrollbar-track,.reader-panel::-webkit-scrollbar-track{background:rgba(7,17,32,.28);border-left:1px solid rgba(96,165,250,.10)}.map-panel::-webkit-scrollbar-thumb,.reader-panel::-webkit-scrollbar-thumb{background:linear-gradient(180deg,rgba(147,197,253,.55),rgba(37,99,235,.38));border:2px solid rgba(7,17,32,.95);border-radius:999px}.map-panel::-webkit-scrollbar-thumb:hover,.reader-panel::-webkit-scrollbar-thumb:hover{background:linear-gradient(180deg,rgba(191,219,254,.75),rgba(96,165,250,.55))}.reader-panel{position:fixed;z-index:968;left:var(--dock-collapsed);top:0;bottom:0;width:min(460px,calc(100vw - var(--dock-collapsed)));background:rgba(7,17,32,.98);border:1px solid rgba(96,165,250,.24);border-left:0;border-radius:0;color:var(--text);box-shadow:18px 0 70px rgba(0,0,0,.34);backdrop-filter:blur(16px);padding:16px;overflow:auto;opacity:0;pointer-events:none;transform:translateX(-100%);transition:opacity .18s ease,transform .18s ease,left .22s ease,width .22s ease}.dock.expanded + .map-panel + .reader-panel{left:var(--dock-expanded);width:min(460px,calc(100vw - var(--dock-expanded)))}body.reader-panel-open .reader-panel{opacity:1;pointer-events:auto;transform:translateX(0)}.reader-tools{border:1px solid rgba(96,165,250,.16);background:rgba(16,32,57,.52);border-radius:18px;padding:12px;margin-bottom:12px}.reader-search{width:100%;border-radius:12px;border:1px solid rgba(96,165,250,.22);background:#081426;color:var(--text);padding:11px 12px;outline:none;margin-bottom:10px}.reader-search:focus{border-color:#93c5fd}.reader-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px}.reader-grid select{width:100%;border-radius:12px;border:1px solid rgba(96,165,250,.22);background:#081426;color:var(--text);padding:9px 10px;outline:none}.reader-actions{display:flex;align-items:center;justify-content:space-between;gap:8px;margin-top:10px}.reader-count{font-size:11px;color:var(--muted);line-height:1.35}.reader-list{display:grid;gap:10px}.reader-card{position:relative;border:1px solid rgba(96,165,250,.16);background:rgba(11,22,40,.84);border-radius:16px;padding:12px 44px 12px 12px;cursor:pointer;transition:border-color .14s ease,background .14s ease,transform .14s ease}.reader-card:hover{border-color:rgba(147,197,253,.45);background:rgba(16,32,57,.9);transform:translateX(1px)}.reader-detail-btn{position:absolute;top:10px;right:10px;width:28px;height:28px;border-radius:10px;border:1px solid rgba(96,165,250,.24);background:rgba(37,99,235,.16);color:#dbeafe;font-weight:950;cursor:pointer}.reader-detail-btn:hover{border-color:rgba(147,197,253,.58);background:rgba(37,99,235,.28)}.reader-card-title{font-size:13px;font-weight:950;line-height:1.25;color:#eaf2ff}.reader-card-meta{display:flex;flex-wrap:wrap;gap:6px;margin-top:7px}.reader-pill{border:1px solid rgba(96,165,250,.16);background:rgba(15,35,64,.6);border-radius:999px;padding:3px 7px;font-size:10px;color:#bfdbfe;font-weight:850}.reader-desc{font-size:11px;color:#cbd5e1;line-height:1.38;margin-top:8px}.reader-detail{margin-top:10px;border-top:1px solid rgba(96,165,250,.14);padding-top:9px;display:grid;grid-template-columns:92px 1fr;gap:5px 10px;font-size:11px}.reader-detail span{color:#9db2d4}.reader-detail b{color:#eaf2ff;word-break:break-word}.reader-empty{border:1px dashed rgba(96,165,250,.24);border-radius:16px;padding:18px;text-align:center;color:var(--muted);font-size:12px;line-height:1.4}"""
    marker = ".panel-help{margin-top:10px;color:var(--muted);font-size:11px;line-height:1.35}"
    text = text.replace(marker, marker + extra_css)

# Botão Leitura real.
replace(
    '<div class="nav-item" title="Leitura"><span class="nav-icon events-icon"></span><span class="nav-label">Leitura</span></div>',
    '<button id="readerPanelToggle" class="nav-item" type="button" title="Leitura" aria-controls="readerPanel" aria-expanded="false"><span class="nav-icon events-icon"></span><span class="nav-label">Leitura</span></button>',
)

# Painel Leitura.
if 'id="readerPanel"' not in text:
    reader_panel = """<section id="readerPanel" class="reader-panel" aria-label="Leitura de eventos" aria-hidden="true">
    <header class="panel-head">
      <div>
        <div class="panel-eyebrow">Leitura</div>
        <div class="panel-title">Eventos do mapa</div>
        <div class="panel-subtitle">Pesquise, filtre e clique em um evento para abrir sua localização no mapa.</div>
      </div>
      <button id="readerPanelClose" class="panel-close" type="button" aria-label="Fechar leitura">×</button>
    </header>
    <section class="reader-tools" aria-label="Busca e filtros de leitura">
      <input id="readerSearch" class="reader-search" type="search" placeholder="Pesquisar por nome, rodovia, cidade, fonte..." autocomplete="off">
      <div class="reader-grid">
        <select id="readerType" aria-label="Filtrar tipo"><option value="all">Todos os tipos</option><option value="climate">Clima</option><option value="road">Rodovia</option><option value="operational">Operacional</option></select>
        <select id="readerSeverity" aria-label="Filtrar severidade"><option value="all">Todas as severidades</option><option value="critical">Crítica</option><option value="high">Alta</option><option value="moderate">Moderada</option><option value="low">Baixa</option></select>
        <select id="readerRegion" aria-label="Filtrar região"><option value="all">Todas as regiões</option></select>
        <select id="readerSort" aria-label="Ordenar eventos"><option value="risk">Maior risco</option><option value="recent">Mais recentes</option><option value="type">Tipo</option><option value="region">Região</option></select>
      </div>
      <div class="reader-actions"><div id="readerCount" class="reader-count">Carregando eventos...</div><button id="readerClear" class="filter-chip" type="button">Limpar</button></div>
    </section>
    <section id="readerList" class="reader-list" aria-label="Lista de eventos"></section>
  </section>"""
    text = text.replace('  <section class="legend" aria-label="Legenda e mapa de calor">', reader_panel + '\n  <section class="legend" aria-label="Legenda e mapa de calor">')

# Região inferida e sem opção "Sem região".
replace(
    "function regionOf(ev){const r=ev.raw||{};return String(firstValue(r,['region','regiao','state','uf','estado','city','municipality','cidade'])||'Sem região').trim()}",
    "function normalizeRegionName(v){const raw=String(v??'').trim();if(!raw||/^sem região$/i.test(raw))return'';const t=raw.normalize('NFD').replace(/[\\u0300-\\u036f]/g,'').toUpperCase();const full={NORTE:'Norte',NORDESTE:'Nordeste','CENTRO-OESTE':'Centro-Oeste',CENTROOESTE:'Centro-Oeste',SUDESTE:'Sudeste',SUL:'Sul'};const uf={AC:'Norte',AP:'Norte',AM:'Norte',PA:'Norte',RO:'Norte',RR:'Norte',TO:'Norte',AL:'Nordeste',BA:'Nordeste',CE:'Nordeste',MA:'Nordeste',PB:'Nordeste',PE:'Nordeste',PI:'Nordeste',RN:'Nordeste',SE:'Nordeste',DF:'Centro-Oeste',GO:'Centro-Oeste',MT:'Centro-Oeste',MS:'Centro-Oeste',ES:'Sudeste',MG:'Sudeste',RJ:'Sudeste',SP:'Sudeste',PR:'Sul',RS:'Sul',SC:'Sul'};return full[t]||uf[t]||''}function regionFromCoords(lat,lon){lat=Number(lat);lon=Number(lon);if(!Number.isFinite(lat)||!Number.isFinite(lon))return'Centro-Oeste';if(lat<-23.5&&lon<-44)return'Sul';if(lat>-18&&lon>-45)return'Nordeste';if(lon<-52&&lat>-18)return'Norte';if(lon<-50)return'Centro-Oeste';if(lat<-14&&lon>-52)return'Sudeste';if(lat>-8)return'Norte';return'Nordeste'}function regionOf(ev){const r=ev.raw||{};for(const value of [r.region,r.regiao,r.state,r.uf,r.estado]){const region=normalizeRegionName(value);if(region)return region}return regionFromCoords(ev.lat,ev.lon)}",
)

# Clique repetido em gráfico remove o filtro.
replace(
    "function setFilter(key,value){if(key==='type')$('filterType').value=value;if(key==='severity')$('filterSeverity').value=value;if(key==='region'){const select=$('filterRegion');if([...select.options].some(o=>o.value===value))select.value=value}applyFilters({fit:true})}",
    "function setFilter(key,value){const select=key==='type'?$('filterType'):key==='severity'?$('filterSeverity'):key==='region'?$('filterRegion'):null;if(!select)return;const next=select.value===value?'all':value;if([...select.options].some(o=>o.value===next))select.value=next;applyFilters({fit:true})}",
)

# IDs estáveis para eventos e marcadores navegáveis.
replace(
    "allEvents=events;populateRegionFilter(events);const sig=dataSignature(events);applyFilters({fit:sig!==lastDataSignature&&initialFit});",
    "events.forEach((ev,i)=>{ev.eventId='ev-'+i});allEvents=events;populateRegionFilter(events);const sig=dataSignature(events);applyFilters({fit:sig!==lastDataSignature&&initialFit});renderReaderList();",
)
replace(
    "events.forEach(ev=>{L.marker([ev.lat,ev.lon],{icon:markerIcon(ev.type)}).bindPopup(popup(ev)).addTo(markerLayer);heat.push([ev.lat,ev.lon,Math.max(.25,ev.risk/100)])});",
    "events.forEach(ev=>{const marker=L.marker([ev.lat,ev.lon],{icon:markerIcon(ev.type)});marker.bindPopup(popup(ev)).addTo(markerLayer);ev._marker=marker;heat.push([ev.lat,ev.lon,Math.max(.25,ev.risk/100)])});",
)

# Região nos dois painéis.
replace(
    "function populateRegionFilter(events){const select=$('filterRegion');if(!select)return;const current=select.value||'all';const regions=[...new Set(events.map(regionOf).filter(Boolean))].sort((a,b)=>a.localeCompare(b,'pt-BR'));select.innerHTML=`<option value=\"all\">Todas as regiões</option>`+regions.map(region=>`<option value=\"${esc(region)}\">${esc(region)}</option>`).join('');select.value=regions.includes(current)?current:'all'}",
    "function populateRegionFilter(events){const regions=[...new Set(events.map(regionOf).filter(Boolean))].sort((a,b)=>a.localeCompare(b,'pt-BR'));['filterRegion','readerRegion'].forEach(id=>{const select=$(id);if(!select)return;const current=select.value||'all';select.innerHTML=`<option value=\"all\">Todas as regiões</option>`+regions.map(region=>`<option value=\"${esc(region)}\">${esc(region)}</option>`).join('');select.value=regions.includes(current)?current:'all'})}",
)

# Painéis mutuamente exclusivos.
replace(
    "function setMapPanel(open){document.body.classList.toggle('map-panel-open',open);$('mapPanel').setAttribute('aria-hidden',String(!open));$('mapPanelToggle').setAttribute('aria-expanded',String(open));$('mapPanelToggle').classList.toggle('active',open);setTimeout(()=>map.invalidateSize(true),220)}",
    "function setMapPanel(open,skipPeer=false){if(open&&!skipPeer)setReaderPanel(false,true);document.body.classList.toggle('map-panel-open',open);$('mapPanel').setAttribute('aria-hidden',String(!open));$('mapPanelToggle').setAttribute('aria-expanded',String(open));$('mapPanelToggle').classList.toggle('active',open);setTimeout(()=>map.invalidateSize(true),220)}function setReaderPanel(open,skipPeer=false){if(open&&!skipPeer)setMapPanel(false,true);document.body.classList.toggle('reader-panel-open',open);const panel=$('readerPanel'),btn=$('readerPanelToggle');if(panel)panel.setAttribute('aria-hidden',String(!open));if(btn){btn.setAttribute('aria-expanded',String(open));btn.classList.toggle('active',open)}if(open)renderReaderList();setTimeout(()=>map.invalidateSize(true),220)}",
)

# Funções da aba Leitura.
if "function readerFilters()" not in text:
    reader_js = """
    function readerFilters(){return{query:($('readerSearch')?.value||'').trim().toLowerCase(),type:$('readerType')?.value||'all',severity:$('readerSeverity')?.value||'all',region:$('readerRegion')?.value||'all',sort:$('readerSort')?.value||'risk'}}
    function readerSearchText(ev){const r=ev.raw||{};return [ev.title,ev.desc,typeLabel(ev.type),severityLabel(severityOf(ev.risk)),regionOf(ev),r.road,r.corridor,r.city,r.state,r.uf,r.source,r.sourceProvider,r.headline].filter(Boolean).join(' ').toLowerCase()}
    function readerVisibleEvents(){const f=readerFilters();let rows=allEvents.filter(ev=>(f.type==='all'||ev.type===f.type)&&(f.severity==='all'||severityOf(ev.risk)===f.severity)&&(f.region==='all'||regionOf(ev)===f.region)&&(!f.query||readerSearchText(ev).includes(f.query)));rows=[...rows];rows.sort((a,b)=>f.sort==='recent'?String(firstValue(b.raw||{},['updatedAt','createdAt','time','newsDate'])).localeCompare(String(firstValue(a.raw||{},['updatedAt','createdAt','time','newsDate']))):f.sort==='type'?typeLabel(a.type).localeCompare(typeLabel(b.type),'pt-BR')||b.risk-a.risk:f.sort==='region'?regionOf(a).localeCompare(regionOf(b),'pt-BR')||b.risk-a.risk:b.risk-a.risk);return rows}
    function readerDetailRows(ev){const r=ev.raw||{};const rows=[['Tipo',typeLabel(ev.type)],['Severidade',severityLabel(severityOf(ev.risk))],['Risco',`${ev.risk}/100`],['Região',regionOf(ev)],['Rodovia',firstValue(r,['road','corridor','highway','route'])],['Fonte',firstValue(r,['source','sourceProvider','provider','origin'])],['Atualizado',fmtDate(firstValue(r,['updatedAt','updated_at','createdAt','created_at','time','newsDate']))],['Coordenadas',`${ev.lat.toFixed(4)}, ${ev.lon.toFixed(4)}`]];return rows.filter(([,v])=>v!==undefined&&v!==null&&String(v).trim()!=='').map(([k,v])=>`<span>${esc(k)}</span><b>${esc(v)}</b>`).join('')}
    let readerDetailId='';
    function renderReaderList(){const list=$('readerList'),count=$('readerCount');if(!list)return;const rows=readerVisibleEvents();if(count)count.textContent=`${rows.length} de ${allEvents.length} evento(s)`;if(!rows.length){list.innerHTML='<div class="reader-empty">Nenhum evento encontrado para a busca e os filtros atuais.</div>';return}list.innerHTML=rows.map(ev=>{const expanded=readerDetailId===ev.eventId;return`<article class="reader-card" tabindex="0" role="button" data-reader-card data-event-id="${esc(ev.eventId)}"><button class="reader-detail-btn" type="button" title="Ver detalhes" aria-label="Ver detalhes" aria-expanded="${expanded}" data-reader-detail data-event-id="${esc(ev.eventId)}">i</button><div class="reader-card-title">${esc(ev.title)}</div><div class="reader-card-meta"><span class="reader-pill">${esc(typeLabel(ev.type))}</span><span class="reader-pill">${esc(severityLabel(severityOf(ev.risk)))}</span><span class="reader-pill">${esc(regionOf(ev))}</span><span class="reader-pill">Risco ${ev.risk}</span></div>${ev.desc?`<div class="reader-desc">${esc(ev.desc).slice(0,220)}</div>`:''}${expanded?`<div class="reader-detail">${readerDetailRows(ev)}</div>`:''}</article>`}).join('')}
    function applyReaderFilters({fit=false}={}){const rows=readerVisibleEvents();renderEvents(rows,{fit});renderReaderList()}
    function clearReaderFilters(){if($('readerSearch'))$('readerSearch').value='';if($('readerType'))$('readerType').value='all';if($('readerSeverity'))$('readerSeverity').value='all';if($('readerRegion'))$('readerRegion').value='all';if($('readerSort'))$('readerSort').value='risk';readerDetailId='';applyReaderFilters({fit:true})}
    function focusEventById(id){const ev=allEvents.find(item=>item.eventId===id);if(!ev)return;if(!ev._marker)renderEvents([ev],{fit:true});setReaderPanel(false,true);setTimeout(()=>{map.flyTo([ev.lat,ev.lon],Math.max(map.getZoom(),8),{duration:.55});setTimeout(()=>{if(ev._marker)ev._marker.openPopup()},420)},40)}
"""
    text = text.replace("    $('mapPanelToggle').addEventListener", reader_js + "    $('mapPanelToggle').addEventListener")

# Eventos de interação dos painéis.
replace(
    "$('mapPanelToggle').addEventListener('click',()=>setMapPanel(!document.body.classList.contains('map-panel-open')));$('mapPanelClose').addEventListener('click',()=>setMapPanel(false));['filterType','filterSeverity','filterRegion'].forEach(id=>$(id).addEventListener('change',()=>applyFilters({fit:true})));$('resetFilters').addEventListener('click',resetFilters);document.addEventListener('click',e=>{const el=e.target.closest('[data-filter]');if(!el)return;setFilter(el.dataset.filter,el.dataset.value)});document.addEventListener('keydown',e=>{if((e.key==='Enter'||e.key===' ')&&e.target.matches('[data-filter]')){e.preventDefault();setFilter(e.target.dataset.filter,e.target.dataset.value)}if(e.key==='Escape'&&document.body.classList.contains('map-panel-open'))setMapPanel(false)});",
    "$('mapPanelToggle').addEventListener('click',()=>setMapPanel(!document.body.classList.contains('map-panel-open')));$('mapPanelClose').addEventListener('click',()=>setMapPanel(false));$('readerPanelToggle').addEventListener('click',()=>setReaderPanel(!document.body.classList.contains('reader-panel-open')));$('readerPanelClose').addEventListener('click',()=>setReaderPanel(false));['filterType','filterSeverity','filterRegion'].forEach(id=>$(id).addEventListener('change',()=>applyFilters({fit:true})));$('resetFilters').addEventListener('click',resetFilters);['readerSearch','readerType','readerSeverity','readerRegion','readerSort'].forEach(id=>$(id).addEventListener(id==='readerSearch'?'input':'change',()=>applyReaderFilters({fit:false})));$('readerClear').addEventListener('click',clearReaderFilters);document.addEventListener('click',e=>{const detail=e.target.closest('[data-reader-detail]');if(detail){e.preventDefault();e.stopPropagation();readerDetailId=readerDetailId===detail.dataset.eventId?'':detail.dataset.eventId;renderReaderList();return}const card=e.target.closest('[data-reader-card]');if(card){focusEventById(card.dataset.eventId);return}const el=e.target.closest('[data-filter]');if(!el)return;setFilter(el.dataset.filter,el.dataset.value)});document.addEventListener('keydown',e=>{if((e.key==='Enter'||e.key===' ')&&e.target.matches('[data-filter]')){e.preventDefault();setFilter(e.target.dataset.filter,e.target.dataset.value)}if((e.key==='Enter'||e.key===' ')&&e.target.matches('[data-reader-card]')){e.preventDefault();focusEventById(e.target.dataset.eventId)}if(e.key==='Escape'){if(document.body.classList.contains('reader-panel-open'))setReaderPanel(false);if(document.body.classList.contains('map-panel-open'))setMapPanel(false)}});",
)

# Compatibilidade com versões antigas do painel de leitura.
replace(
    "async function getJson(path,fallbackValue){return getJsonAny([path,RAW+path],fallbackValue)}",
    "async function getJson(path,fallbackValue){const sources=String(path||'').startsWith('data/')?[RAW+path,path]:[path,RAW+path];return getJsonAny(sources,fallbackValue)}",
)
replace('<button id="clearChartFilters" class="mini-action" type="button">Limpar filtros gráficos</button>', '')
replace("$('clearChartFilters').onclick=clearChartFilters;", "")

if "manualEvents:[]" not in text:
    replace(
        "state={climate:[],roadEvents:[],operationalEvents:[],heat:null",
        "state={climate:[],roadEvents:[],operationalEvents:[],manualEvents:[],heat:null",
    )

if "async function loadManualEvents()" not in text:
    marker = "async function loadOperationalEvents(){"
    insert = """async function loadManualEvents(){
 const events=await getJson('data/manual_events.json',[]);
 state.manualEvents=Array.isArray(events)?events.filter(e=>e.active!==false&&(!e.expiresAt||Date.parse(e.expiresAt)>Date.now())).map(e=>({...e,type:e.type||'operational',risk:Number(e.risk||50),reasons:e.reasons||[e.description||e.eventType||'Evento manual']})):[]
}
"""
    replace(marker, insert + marker)

replace(
    "await Promise.allSettled([loadClimate(),loadRoadEvents(),loadOperationalEvents()]);state.loaded=true;render()",
    "await Promise.allSettled([loadClimate(),loadRoadEvents(),loadOperationalEvents(),loadManualEvents()]);state.loaded=true;render()",
)
replace(
    "if(mode==='all'||mode==='operational')items.push(...state.operationalEvents);",
    "if(mode==='all'||mode==='operational')items.push(...state.operationalEvents,...state.manualEvents.filter(x=>x.type==='operational'));if(mode==='all'||mode==='climate')items.push(...state.manualEvents.filter(x=>x.type==='climate'));if(mode==='all'||mode==='road')items.push(...state.manualEvents.filter(x=>x.type==='road'));",
)

path.write_text(text, encoding="utf-8")
