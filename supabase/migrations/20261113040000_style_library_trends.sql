-- Style library v2: rich, source-grounded style records + trend momentum + per-user style feedback.
alter table styles
  add column status text not null default 'active' check (status in ('active', 'candidate', 'rejected')),
  add column definition text,
  add column key_pieces text[] default '{}',
  add column palette text[] default '{}',
  add column materials text[] default '{}',
  add column formality_min int,
  add column formality_max int,
  add column seasons text[] default '{}',
  add column aliases text[] default '{}',
  add column related text[] default '{}',
  add column search_term text,
  add column source text,            -- aesthetics_wiki | trends_discovery | manual | pinterest
  add column source_url text,        -- attribution (Aesthetics Wiki content is CC BY-SA)
  add column lifecycle text,         -- emerging | rising | peak | stable | fading
  add column trend jsonb,            -- latest momentum metrics
  add column updated_at timestamptz default now();

-- Weekly Google Trends snapshots per style (time series + rising related queries for discovery).
create table style_trend_snapshots (
  id uuid primary key default gen_random_uuid(),
  style_id uuid not null references styles(id) on delete cascade,
  term text not null,
  geo text not null default '',
  points jsonb not null,             -- [[iso_date, value], ...] weekly interest 0-100
  rising jsonb default '[]'::jsonb,  -- [[query, growth_percent], ...]
  metrics jsonb not null,            -- lifecycle stage + growth numbers
  created_at timestamptz default now()
);
create index on style_trend_snapshots(style_id, created_at desc);

create table user_style_feedback (
  user_id uuid not null references users(id) on delete cascade,
  style_id uuid not null references styles(id) on delete cascade,
  interested boolean not null,
  created_at timestamptz default now(),
  primary key (user_id, style_id)
);

alter table style_trend_snapshots enable row level security;
alter table user_style_feedback enable row level security;
