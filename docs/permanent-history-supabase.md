# Histórico permanente de eventos com Supabase

Este guia prepara o mapa para usar Google Sheets como painel operacional leve e Supabase/Postgres como histórico permanente.

## 1. Criar o projeto

1. Acesse https://supabase.com
2. Crie um projeto novo.
3. Escolha uma senha forte para o banco.
4. Espere o projeto terminar de provisionar.

## 2. Criar as tabelas

No Supabase, abra **SQL Editor** e rode:

```sql
create table if not exists events (
  stable_event_id text primary key,
  source_type text not null,
  category text,
  event_type text,
  name text,
  road text,
  city text,
  state text,
  region text,
  lat double precision,
  lon double precision,
  source text,
  source_url text,
  first_seen_at timestamptz not null default now(),
  last_seen_at timestamptz not null default now(),
  current_risk integer default 0,
  current_severity text,
  current_description text,
  current_observation_hash text,
  active boolean default true,
  total_snapshots integer default 1,
  updated_at timestamptz not null default now()
);

create table if not exists event_observations (
  observation_id text primary key,
  stable_event_id text references events(stable_event_id) on delete cascade,
  observed_at timestamptz not null,
  snapshot_bucket text,
  risk integer default 0,
  severity text,
  description text,
  precipitation numeric,
  source text,
  source_url text,
  raw jsonb,
  created_at timestamptz not null default now()
);

create table if not exists daily_event_summary (
  summary_date date not null,
  source_type text not null,
  region text not null,
  severity text not null,
  events_count integer not null default 0,
  avg_risk numeric,
  max_risk integer,
  rain_events integer default 0,
  road_events integer default 0,
  operational_events integer default 0,
  updated_at timestamptz not null default now(),
  primary key (summary_date, source_type, region, severity)
);

create index if not exists idx_events_last_seen on events(last_seen_at desc);
create index if not exists idx_events_source_type on events(source_type);
create index if not exists idx_events_region on events(region);
create index if not exists idx_event_observations_seen on event_observations(observed_at desc);
create index if not exists idx_event_observations_stable on event_observations(stable_event_id, observed_at desc);
```

## 3. Criar função RPC de ingestão

Ainda no SQL Editor, rode:

```sql
create or replace function ingest_event_batch(events_payload jsonb)
returns jsonb
language plpgsql
security definer
as $$
declare
  item jsonb;
  inserted_events integer := 0;
  updated_events integer := 0;
  inserted_observations integer := 0;
  sid text;
  obs_id text;
  obs_hash text;
begin
  for item in select * from jsonb_array_elements(events_payload)
  loop
    sid := coalesce(item->>'stable_event_id', item->>'event_id');
    obs_hash := coalesce(item->>'observation_hash', md5(item::text));
    obs_id := md5(sid || '|' || obs_hash || '|' || coalesce(item->>'snapshot_bucket', ''));

    insert into events (
      stable_event_id, source_type, category, event_type, name, road, city, state, region,
      lat, lon, source, source_url, first_seen_at, last_seen_at,
      current_risk, current_severity, current_description, current_observation_hash,
      active, total_snapshots, updated_at
    ) values (
      sid,
      coalesce(item->>'source_type', ''),
      item->>'category',
      item->>'event_type',
      item->>'name',
      item->>'road',
      item->>'city',
      item->>'state',
      item->>'region',
      nullif(item->>'lat','')::double precision,
      nullif(item->>'lon','')::double precision,
      item->>'source',
      item->>'source_url',
      coalesce(nullif(item->>'snapshot_at','')::timestamptz, now()),
      coalesce(nullif(item->>'last_seen_at','')::timestamptz, now()),
      coalesce(nullif(item->>'risk','')::integer, 0),
      item->>'severity',
      item->>'description',
      obs_hash,
      coalesce(nullif(item->>'active','')::boolean, true),
      1,
      now()
    )
    on conflict (stable_event_id) do update set
      last_seen_at = excluded.last_seen_at,
      current_risk = excluded.current_risk,
      current_severity = excluded.current_severity,
      current_description = excluded.current_description,
      source = excluded.source,
      source_url = excluded.source_url,
      active = excluded.active,
      total_snapshots = events.total_snapshots + 1,
      updated_at = now();

    if found then
      updated_events := updated_events + 1;
    else
      inserted_events := inserted_events + 1;
    end if;

    -- Histórico permanente compacto: salva observação só quando muda o conteúdo relevante.
    insert into event_observations (
      observation_id, stable_event_id, observed_at, snapshot_bucket,
      risk, severity, description, precipitation, source, source_url, raw
    )
    select
      obs_id,
      sid,
      coalesce(nullif(item->>'snapshot_at','')::timestamptz, now()),
      item->>'snapshot_bucket',
      coalesce(nullif(item->>'risk','')::integer, 0),
      item->>'severity',
      item->>'description',
      nullif(item->>'precipitation','')::numeric,
      item->>'source',
      item->>'source_url',
      item
    where not exists (
      select 1
      from event_observations
      where stable_event_id = sid
        and raw->>'observation_hash' = obs_hash
    )
    on conflict do nothing;

    if found then
      inserted_observations := inserted_observations + 1;
    end if;
  end loop;

  return jsonb_build_object(
    'ok', true,
    'inserted_events', inserted_events,
    'updated_events', updated_events,
    'inserted_observations', inserted_observations
  );
end;
$$;
```

## 4. Criar uma view para leitura do dashboard

```sql
create or replace view dashboard_events_recent as
select
  e.stable_event_id,
  e.source_type,
  e.category,
  e.event_type,
  e.name,
  e.road,
  e.city,
  e.state,
  e.region,
  e.lat,
  e.lon,
  e.source,
  e.source_url,
  e.first_seen_at,
  e.last_seen_at,
  e.current_risk as risk,
  e.current_severity as severity,
  e.current_description as description,
  e.total_snapshots,
  round(e.total_snapshots * 0.25, 2) as estimated_hours,
  e.active
from events e
order by e.last_seen_at desc;
```

## 5. Criar API key e secrets no GitHub

No Supabase:

1. Abra **Project Settings → API**.
2. Copie:
   - Project URL
   - service_role key

No GitHub:

1. Vá em **Settings → Secrets and variables → Actions**.
2. Crie:
   - `SUPABASE_URL`
   - `SUPABASE_SERVICE_ROLE_KEY`

Não coloque essas chaves no código do site público.

## 6. Próxima etapa no repositório

Depois que os secrets estiverem criados, o workflow pode chamar um script `scripts/sync_events_to_supabase.py` para enviar os eventos ao Supabase a cada atualização.

Google Sheets continuará servindo como painel leve/current state. Supabase será o histórico permanente.
