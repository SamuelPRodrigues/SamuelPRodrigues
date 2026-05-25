#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

path = Path("index.html")
text = path.read_text(encoding="utf-8")

# Mantém o painel de filtros do mapa fisicamente acoplado à barra lateral no HTML publicado.
text = text.replace(
    ".map-panel{position:fixed;z-index:970;left:calc(var(--dock-collapsed) + 12px);top:12px;bottom:12px;width:min(430px,calc(100vw - 104px));background:rgba(7,17,32,.95);border:1px solid rgba(96,165,250,.24);border-radius:22px;color:var(--text);box-shadow:0 24px 70px rgba(0,0,0,.34);backdrop-filter:blur(16px);padding:16px;overflow:auto;opacity:0;pointer-events:none;transform:translateX(-12px);transition:opacity .18s ease,transform .18s ease,left .22s ease}.dock.expanded + .map-panel{left:calc(var(--dock-expanded) + 12px)}",
    ".map-panel{position:fixed;z-index:970;left:var(--dock-collapsed);top:0;bottom:0;width:min(430px,calc(100vw - var(--dock-collapsed)));background:rgba(7,17,32,.98);border:1px solid rgba(96,165,250,.24);border-left:0;border-radius:0 22px 22px 0;color:var(--text);box-shadow:18px 0 70px rgba(0,0,0,.34);backdrop-filter:blur(16px);padding:16px;overflow:auto;opacity:0;pointer-events:none;transform:translateX(-100%);transition:opacity .18s ease,transform .18s ease,left .22s ease,width .22s ease}.dock.expanded + .map-panel{left:var(--dock-expanded);width:min(430px,calc(100vw - var(--dock-expanded)))}",
)
text = text.replace(
    "@media(max-width:760px){.dock.expanded{width:min(220px,72vw)}.map-panel,.dock.expanded + .map-panel{left:calc(var(--dock-collapsed) + 8px);right:8px;top:8px;bottom:8px;width:auto;padding:13px}.donut-wrap{grid-template-columns:116px 1fr}.legend{right:10px;bottom:88px;width:calc(100vw - 92px);padding:12px}}",
    "@media(max-width:760px){.dock.expanded{width:var(--dock-collapsed);align-items:center}.dock.expanded .nav-item{width:48px;justify-content:center;padding:0;margin:0 auto}.dock.expanded .nav-label{display:none}.map-panel,.dock.expanded + .map-panel{left:var(--dock-collapsed);right:0;top:0;bottom:0;width:auto;border-radius:0 18px 18px 0;padding:13px}.donut-wrap{grid-template-columns:116px 1fr}.legend{right:10px;bottom:88px;width:calc(100vw - 92px);padding:12px}}",
)

text = text.replace(
    "async function getJson(path,fallbackValue){return getJsonAny([path,RAW+path],fallbackValue)}",
    "async function getJson(path,fallbackValue){const sources=String(path||'').startsWith('data/')?[RAW+path,path]:[path,RAW+path];return getJsonAny(sources,fallbackValue)}",
)
text = text.replace('<button id="clearChartFilters" class="mini-action" type="button">Limpar filtros gráficos</button>', '')
text = text.replace("$('clearChartFilters').onclick=clearChartFilters;", "")

if "manualEvents:[]" not in text:
    text = text.replace(
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
    text = text.replace(marker, insert + marker)

text = text.replace(
    "await Promise.allSettled([loadClimate(),loadRoadEvents(),loadOperationalEvents()]);state.loaded=true;render()",
    "await Promise.allSettled([loadClimate(),loadRoadEvents(),loadOperationalEvents(),loadManualEvents()]);state.loaded=true;render()",
)
text = text.replace(
    "if(mode==='all'||mode==='operational')items.push(...state.operationalEvents);",
    "if(mode==='all'||mode==='operational')items.push(...state.operationalEvents,...state.manualEvents.filter(x=>x.type==='operational'));if(mode==='all'||mode==='climate')items.push(...state.manualEvents.filter(x=>x.type==='climate'));if(mode==='all'||mode==='road')items.push(...state.manualEvents.filter(x=>x.type==='road'));",
)

if ".reader-filter-toggle" not in text:
    filter_css = """.reader-filter-toggle{margin-top:10px;width:100%;border:1px solid var(--line);background:#0b1220;color:#e5e7eb;border-radius:12px;padding:10px 12px;font-size:13px;font-weight:950;cursor:pointer;display:flex;align-items:center;justify-content:space-between;gap:8px}.reader-filter-toggle:hover{border-color:#60a5fa;background:#10243d}.reader-filter-toggle .filter-word{display:flex;align-items:center;gap:8px}.reader-filter-toggle .filter-icon{font-size:15px;color:#93c5fd}.reader-filter-toggle .chevron{color:#93c5fd;transition:transform .16s ease}.reader-filter-toggle[aria-expanded=\"true\"] .chevron{transform:rotate(180deg)}.reader-filter-panel{margin-top:10px;padding:10px;border:1px solid var(--line);border-radius:14px;background:#0b1220}.reader-filter-panel[hidden]{display:none}.reader-filter-panel .reader-more{margin-top:0}.reader-filter-panel .reader-chips{margin-top:10px}.reader-filter-panel .reader-actions{margin-top:10px}"""
    text = text.replace("@media(max-width:950px)", filter_css + "@media(max-width:950px)")

if "readerFilterToggle" not in text:
    text = text.replace(
        "</select></div><div class=\"reader-more\">",
        "</select></div><button id=\"readerFilterToggle\" class=\"reader-filter-toggle\" type=\"button\" aria-expanded=\"false\" aria-controls=\"readerFilterPanel\"><span class=\"filter-word\"><span class=\"filter-icon\" aria-hidden=\"true\">☰</span>Filtros</span><span class=\"chevron\" aria-hidden=\"true\">▾</span></button><div id=\"readerFilterPanel\" class=\"reader-filter-panel\" hidden><div class=\"reader-more\">",
    )
    text = text.replace(
        "<button id=\"readerClear\" class=\"reader-clear\" type=\"button\">Limpar</button></div></header><div id=\"eventList\"",
        "<button id=\"readerClear\" class=\"reader-clear\" type=\"button\">Limpar</button></div></div></header><div id=\"eventList\"",
    )

if "readerFilterPanel" in text and "const readerFilterPanel=$('readerFilterPanel')" not in text:
    text = text.replace(
        "$('readerClear').onclick=()=>{state.readerFilter.type='all';$('eventSearch').value='';$('readerSeverity').value='all';$('readerRegion').value='all';$('eventSort').value='recent';updateReader(visibleItems())};document.querySelectorAll('[data-reader-type]')",
        "$('readerClear').onclick=()=>{state.readerFilter.type='all';$('eventSearch').value='';$('readerSeverity').value='all';$('readerRegion').value='all';$('eventSort').value='recent';updateReader(visibleItems())};const readerFilterToggle=$('readerFilterToggle'),readerFilterPanel=$('readerFilterPanel');if(readerFilterToggle&&readerFilterPanel){readerFilterToggle.onclick=()=>{const expanded=readerFilterToggle.getAttribute('aria-expanded')==='true';readerFilterToggle.setAttribute('aria-expanded',String(!expanded));readerFilterPanel.hidden=expanded}};document.querySelectorAll('[data-reader-type]')",
    )

path.write_text(text, encoding="utf-8")
