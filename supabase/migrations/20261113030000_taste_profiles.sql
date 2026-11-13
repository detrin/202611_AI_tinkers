-- Taste profiles built by a strong reasoning model (Claude Opus via `claude -p`) from all user evidence.
-- Append-only: the latest row per user is the current profile.
create table taste_profiles (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references users(id) on delete cascade,
  model text not null,
  profile jsonb not null,          -- current vs aspirational style, gap, palette, shop queries, confidence
  facts jsonb not null,            -- deterministic wardrobe statistics computed in code
  evidence_counts jsonb not null,  -- how much evidence of each kind went in
  created_at timestamptz default now()
);
create index on taste_profiles(user_id, created_at desc);
alter table taste_profiles enable row level security;
