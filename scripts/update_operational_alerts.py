#!/usr/bin/env python3
from __future__ import annotations

import email.utils, json, re, time, urllib.parse, urllib.request, xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

OUTPUT = Path('data/operational_alerts.json')
STATUS = Path('data/operational_alerts_status.json')
BR_TZ = ZoneInfo('America/Sao_Paulo')

CITIES = {
    'são paulo': (-23.550, -46.633, 'SP'), 'rio de janeiro': (-22.906, -43.173, 'RJ'),
    'belo horizonte': (-19.916, -43.934, 'MG'), 'brasília': (-15.793, -47.882, 'DF'),
    'curitiba': (-25.428, -49.273, 'PR'), 'porto alegre': (-30.034, -51.217, 'RS'),
    'salvador': (-12.977, -38.501, 'BA'), 'recife': (-8.047, -34.877, 'PE'),
    'fortaleza': (-3.731, -38.526, 'CE'), 'manaus': (-3.119, -60.021, 'AM'),
    'belém': (-1.455, -48.490, 'PA'), 'goiânia': (-16.686, -49.264, 'GO'),
    'campinas': (-22.907, -47.063, 'SP'), 'santos': (-23.960, -46.333, 'SP'),
    'guarulhos': (-23.454, -46.533, 'SP'), 'osasco': (-23.532, -46.791, 'SP'),
    'niterói': (-22.883, -43.103, 'RJ'), 'duque de caxias': (-22.785, -43.311, 'RJ'),
    'nova iguaçu': (-22.759, -43.451, 'RJ'), 'são gonçalo': (-22.826, -43.063, 'RJ'),
    'contagem': (-19.932, -44.053, 'MG'), 'betim': (-19.967, -44.198, 'MG'),
    'joinville': (-26.304, -48.849, 'SC'), 'florianópolis': (-27.594, -48.548, 'SC'),
    'cuiabá': (-15.601, -56.098, 'MT'), 'campo grande': (-20.469, -54.620, 'MS'),
    'vitória': (-20.315, -40.312, 'ES'), 'maceió': (-9.665, -35.735, 'AL'),
    'natal': (-5.795, -35.209, 'RN'), 'joão pessoa': (-7.119, -34.845, 'PB'),
    'teresina': (-5.091, -42.803, 'PI'), 'são luís': (-2.530, -44.306, 'MA'),
    'aracaju': (-10.947, -37.073, 'SE'), 'palmas': (-10.184, -48.334, 'TO'),
    'rio branco': (-9.975, -67.824, 'AC'), 'porto velho': (-8.761, -63.901, 'RO'),
    'boa vista': (2.824, -60.675, 'RR'), 'macapá': (0.035, -51.070, 'AP'),
}

# Aliases amplos: usados para área aproximada, nunca para ponto exato.
LOCATION_ALIASES = {
    'no rio': 'rio de janeiro', 'grande rio': 'rio de janeiro', 'rj': 'rio de janeiro',
    'zona norte': 'rio de janeiro', 'zona oeste': 'rio de janeiro', 'centro do rio': 'rio de janeiro',
    'linha vermelha': 'rio de janeiro', 'linha amarela': 'rio de janeiro', 'avenida brasil': 'rio de janeiro',
    'baixada fluminense': 'duque de caxias', 'caxias': 'duque de caxias', 'nova iguacu': 'nova iguaçu',
    'grande recife': 'recife', 'região metropolitana do recife': 'recife',
    'grande são paulo': 'são paulo', 'região metropolitana de são paulo': 'são paulo',
    'abc paulista': 'são paulo', 'baixada santista': 'santos',
}

TRUSTED_NEWS_SITES = [('CNN Brasil','cnnbrasil.com.br'),('Jovem Pan','jovempan.com.br'),('G1','g1.globo.com'),('UOL Notícias','noticias.uol.com.br'),('Agência Brasil','agenciabrasil.ebc.com.br'),('Estadão','estadao.com.br'),('Folha','folha.uol.com.br'),('O Globo','oglobo.globo.com'),('R7','noticias.r7.com'),('Band','band.uol.com.br'),('Metrópoles','metropoles.com'),('Terra','terra.com.br')]

SAFETY_TERMS = ['tiroteio','disparos','baleado','baleada','arrastão','troca de tiros','roubo de carga','carga roubada','saque de carga']
BLOCK_TERMS = ['bloqueio','bloqueada','bloqueado','interdição','interditada','interditado','manifestação','protesto']
TRAFFIC_CONTEXT = ['rua','avenida','av.','via','vias','rodovia','estrada','trânsito','trafego','tráfego','pista','faixa','ponte','túnel','terminal','estação','br-','sp-','mg-','rj-','km ','linha vermelha','linha amarela','avenida brasil']
EMERGENCY_TERMS = ['incêndio','explosão','fumaça','desabamento','queda de árvore','alagamento','enchente','deslizamento','semáforo apagado','falta de energia']
IRRELEVANT_TERMS = ['futebol','campeonato','partida','jogo','jogador','jogadores','técnico','treinador','time','times','clube','clubes','série a','série b','libertadores','sul-americana','copa do brasil','brasileirão','crb','ponte preta','flamengo','corinthians','palmeiras','santos fc','são paulo fc','vasco','fluminense','botafogo','grêmio','internacional','atlético','cruzeiro','orçamento','bloqueio do orçamento','bloqueio orçamentário','contingenciamento','verba','fiscal','ministério da fazenda','arcabouço','congresso','senado','câmara','deputado','senador','bolsa','mercado','ações','dólar','juros','selic','inflação','lucro','prejuízo','balanço financeiro','confronto contra','duelo contra','enfrenta','escalação','rodada','placar','torcida','atacante','goleiro']
MAJOR_CONTEXT_TERMS = ['mortes','mortos','feridos','bloqueio total','enchente','deslizamento','explosão','grandes proporções','interdição total','estado de emergência']

BASE_QUERY = '("tiroteio" OR "troca de tiros" OR "disparos" OR "arrastão" OR "roubo de carga" OR "carga roubada" OR "manifestação bloqueia" OR "protesto bloqueia" OR "via interditada" OR "rodovia interditada" OR "incêndio" OR "explosão" OR "alagamento" OR "queda de árvore")'
NEGATIVE_QUERY = ' -futebol -jogo -partida -campeonato -orçamento -mercado -ações -dólar -crb -"ponte preta"'
SAME_DAY_QUERY = BASE_QUERY + ' sourcecountry:BR'
MAJOR_CONTEXT_QUERY = '("mortes" OR "mortos" OR "feridos" OR "bloqueio total" OR "enchente" OR "deslizamento" OR "explosão" OR "incêndio de grandes proporções" OR "interdição total") sourcecountry:BR'
GOOGLE_GENERAL_QUERIES = [BASE_QUERY + ' Brasil when:1d' + NEGATIVE_QUERY, '("via interditada" OR "trânsito bloqueado" OR "linha vermelha" OR "avenida brasil" OR "zona norte") Rio when:1d' + NEGATIVE_QUERY]
GOOGLE_SOURCE_QUERIES = [f'{BASE_QUERY} site:{domain} when:1d{NEGATIVE_QUERY}' for _, domain in TRUSTED_NEWS_SITES]
GOOGLE_QUERIES = [('geral', q) for q in GOOGLE_GENERAL_QUERIES] + [('fonte-confiavel', q) for q in GOOGLE_SOURCE_QUERIES]

def now_utc() -> datetime: return datetime.now(timezone.utc)
def now_br() -> datetime: return now_utc().astimezone(BR_TZ)
def now_iso() -> str: return now_utc().replace(microsecond=0).isoformat().replace('+00:00','Z')
def gdelt_stamp(dt: datetime) -> str: return dt.astimezone(timezone.utc).strftime('%Y%m%d%H%M%S')
def today_start_br_as_utc() -> datetime:
    br=now_br(); return datetime(br.year, br.month, br.day, 0, 0, 0, tzinfo=BR_TZ).astimezone(timezone.utc)
def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True); path.write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
def load_existing_events() -> list[dict[str, Any]]:
    try:
        if OUTPUT.exists():
            data=json.loads(OUTPUT.read_text(encoding='utf-8')); return data if isinstance(data, list) else []
    except Exception: pass
    return []
def fetch_url(url: str, timeout: int=60) -> bytes:
    req=urllib.request.Request(url, headers={'User-Agent':'Mozilla/5.0 operational-alerts-brazil/1.7'})
    with urllib.request.urlopen(req, timeout=timeout) as response: return response.read()
def fetch_gdelt_once(query: str, *, start: datetime|None=None, end: datetime|None=None, timespan: str|None=None, maxrecords: int=75, timeout: int=60) -> list[dict[str, Any]]:
    params={'query':query,'mode':'ArtList','format':'json','maxrecords':str(maxrecords),'sort':'HybridRel'}
    if start and end: params['startdatetime']=gdelt_stamp(start); params['enddatetime']=gdelt_stamp(end)
    elif timespan: params['timespan']=timespan
    else: params['timespan']='6h'
    payload=json.loads(fetch_url('https://api.gdeltproject.org/api/v2/doc/doc?'+urllib.parse.urlencode(params), timeout).decode('utf-8', errors='replace'))
    return payload.get('articles', []) if isinstance(payload, dict) else []
def fetch_gdelt(label: str, query: str, status: dict[str, Any], **kwargs: Any) -> list[dict[str, Any]]:
    errors=[]
    for attempt in range(1,4):
        try:
            result=fetch_gdelt_once(query, **kwargs); status['gdeltRequestsSucceeded']+=1
            if attempt>1: status['retryRecoveries']+=1
            return result
        except Exception as exc:
            errors.append(f'{label} tentativa {attempt}: {exc}'); time.sleep(attempt*2)
    status['gdeltRequestFailures']+=1; status['errors'].extend(errors[-2:]); return []
def parse_rss_date(raw: str) -> datetime|None:
    try:
        parsed=email.utils.parsedate_to_datetime(raw)
        if not parsed.tzinfo: parsed=parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(BR_TZ)
    except Exception: return None
def fetch_google_news(status: dict[str, Any]) -> list[dict[str, Any]]:
    articles=[]; status['googleNewsQueriesPlanned']=len(GOOGLE_QUERIES)
    for kind, query in GOOGLE_QUERIES:
        try:
            params={'q':query,'hl':'pt-BR','gl':'BR','ceid':'BR:pt-419'}
            root=ET.fromstring(fetch_url('https://news.google.com/rss/search?'+urllib.parse.urlencode(params), timeout=45))
            status['googleNewsRequestsSucceeded']+=1
            if kind=='fonte-confiavel': status['trustedSourceRequestsSucceeded']+=1
            for item in root.findall('.//item'):
                dt=parse_rss_date(item.findtext('pubDate') or ''); source_el=item.find('source')
                articles.append({'title':item.findtext('title') or '', 'url':item.findtext('link') or '', 'sourceCommonName':source_el.text if source_el is not None and source_el.text else 'Google News', 'seendate':dt.strftime('%Y%m%dT%H%M%S') if dt else '', 'provider':'Google News RSS' if kind=='geral' else 'Google News RSS - fonte confiável'})
        except Exception as exc:
            status['googleNewsRequestFailures']+=1; status['errors'].append(f'google-news {kind}: {exc}')
    return articles
def has_any(text: str, terms: list[str]) -> bool: return any(term in text for term in terms)
def classify(text: str, status: dict[str, Any]) -> tuple[str,str,int,int] | None:
    t=text.casefold()
    if has_any(t, IRRELEVANT_TERMS): status['skippedIrrelevant']+=1; return None
    if has_any(t, SAFETY_TERMS): return 'Segurança operacional','Ocorrência de segurança',78,2
    if (has_any(t, BLOCK_TERMS) and has_any(t, TRAFFIC_CONTEXT)) or 'manifestação bloqueia' in t or 'protesto bloqueia' in t:
        return 'Bloqueio urbano','Manifestação ou bloqueio',58,6
    if has_any(t, EMERGENCY_TERMS): return 'Emergência urbana','Incêndio ou emergência',62,4
    status['skippedNoRule']+=1; return None
def geocode(text: str, status: dict[str, Any]) -> tuple[float,float,str,str] | None:
    t=text.casefold(); best=None
    for city,(lat,lon,uf) in CITIES.items():
        if city in t and (not best or len(city)>len(best[0])): best=(city,lat,lon,uf)
    if best:
        city,lat,lon,uf=best; return lat,lon,city.title(),uf
    padded=f' {t} '
    for alias,city in LOCATION_ALIASES.items():
        if f' {alias} ' in padded or alias in t:
            lat,lon,uf=CITIES[city]; status['locationAliasMatches']+=1; return lat,lon,city.title(),uf
    return None
def clean_title(title: str) -> str: return re.sub(r'\s+',' ', title).strip()[:140]
def article_datetime_br(article: dict[str, Any]) -> datetime|None:
    m=re.search(r'(\d{8})T?(\d{6})', str(article.get('seendate') or ''))
    if not m: return None
    try: return datetime.strptime(''.join(m.groups()), '%Y%m%d%H%M%S').replace(tzinfo=BR_TZ).astimezone(BR_TZ)
    except ValueError: return None
def is_same_day_article(article: dict[str, Any]) -> bool:
    dt=article_datetime_br(article); return bool(dt and dt.date()==now_br().date())
def is_major_context(text: str, risk: int, article_dt: datetime|None) -> bool:
    if not article_dt or article_dt.date()==now_br().date() or article_dt < (now_br()-timedelta(hours=48)): return False
    return risk>=85 or has_any(text.casefold(), MAJOR_CONTEXT_TERMS)
def normalize(article: dict[str, Any], *, allow_major_context: bool, status: dict[str, Any]) -> dict[str, Any] | None:
    title=str(article.get('title') or ''); url=str(article.get('url') or ''); source=str(article.get('sourceCommonName') or article.get('domain') or 'GDELT')
    text=f'{title} {source}'; cls=classify(text, status)
    if not cls: return None
    geo=geocode(text, status)
    if not geo: status['skippedNoCity']+=1; return None
    if not url: return None
    category,event_type,risk,expires_hours=cls; article_dt=article_datetime_br(article); same_day=is_same_day_article(article); major_context=allow_major_context and is_major_context(text,risk,article_dt)
    if not same_day and not major_context: status['skippedByDate']+=1; return None
    if major_context: status['majorContextExceptions']+=1
    lat,lon,city,uf=geo; expires=datetime.now(timezone.utc)+timedelta(hours=expires_hours); provider=article.get('provider') or 'GDELT DOC 2.0'
    return {'active':True,'type':'other','category':category,'eventType':event_type,'name':f'{event_type} • {city}/{uf}','description':'Alerta operacional detectado em fonte pública. Região aproximada; evite a área se estiver em rota.','lat':lat,'lon':lon,'radiusMeters':2500 if category=='Segurança operacional' else 1400,'risk':risk,'confidence':'fonte pública automatizada' if same_day else 'contexto de grande evento','source':source,'sourceProvider':provider,'sourceUrl':url,'headline':clean_title(title),'newsDate':article_dt.isoformat() if article_dt else None,'datePolicy':'same-day' if same_day else 'major-event-context','createdAt':now_iso(),'expiresAt':expires.replace(microsecond=0).isoformat().replace('+00:00','Z')}
def main() -> None:
    start=today_start_br_as_utc(); end=now_utc()
    status={'updatedAt':now_iso(),'provider':'GDELT DOC 2.0 + Google News RSS + filtros anti-falso-positivo + aliases amplos','trustedSources':[n for n,_ in TRUSTED_NEWS_SITES],'datePolicy':'same-day Brazil time; older articles only for major-event context','sameDayWindowStartUtc':gdelt_stamp(start),'sameDayWindowEndUtc':gdelt_stamp(end),'gdeltRequestsSucceeded':0,'gdeltRequestFailures':0,'googleNewsQueriesPlanned':0,'googleNewsRequestsSucceeded':0,'trustedSourceRequestsSucceeded':0,'googleNewsRequestFailures':0,'retryRecoveries':0,'rawArticles':0,'eventsWritten':0,'skippedByDate':0,'skippedNoCity':0,'skippedNoRule':0,'skippedIrrelevant':0,'locationAliasMatches':0,'majorContextExceptions':0,'keptPreviousOnFailure':False,'errors':[]}
    articles=fetch_gdelt('same-day-window', SAME_DAY_QUERY, status, start=start, end=end, maxrecords=120, timeout=60)
    if not articles: articles=fetch_gdelt('same-day-timespan-fallback', SAME_DAY_QUERY, status, timespan='24h', maxrecords=120, timeout=60)
    google_articles=fetch_google_news(status); major_articles=fetch_gdelt('major-context', MAJOR_CONTEXT_QUERY, status, timespan='48h', maxrecords=50, timeout=60)
    status['rawArticles']=len(articles)+len(google_articles)+len(major_articles)
    seen=set(); events=[]
    for article in articles+google_articles:
        event=normalize(article, allow_major_context=False, status=status)
        if event and event['sourceUrl'] not in seen: seen.add(event['sourceUrl']); events.append(event)
    for article in major_articles:
        event=normalize(article, allow_major_context=True, status=status)
        if event and event['sourceUrl'] not in seen: seen.add(event['sourceUrl']); events.append(event)
    events.sort(key=lambda e:int(e.get('risk',0)), reverse=True)
    if events or status['gdeltRequestsSucceeded']>0 or status['googleNewsRequestsSucceeded']>0:
        write_json(OUTPUT, events[:40]); status['eventsWritten']=len(events[:40])
    else:
        existing=load_existing_events(); write_json(OUTPUT, existing); status['eventsWritten']=len(existing); status['keptPreviousOnFailure']=True
    write_json(STATUS, status); print(json.dumps(status, ensure_ascii=False, indent=2))
if __name__ == '__main__': main()
