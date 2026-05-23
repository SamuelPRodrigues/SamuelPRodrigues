#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path

path = Path("index.html")
text = path.read_text(encoding="utf-8")

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

path.write_text(text, encoding="utf-8")
