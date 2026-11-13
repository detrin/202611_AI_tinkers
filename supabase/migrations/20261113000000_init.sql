-- Wardrobe stylist: initial schema. Backend uses the service-role key, so RLS is enabled with no policies
-- (blocks anon/public access; service role bypasses RLS).

create extension if not exists pgcrypto;

create table users (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  city text,
  budget numeric,
  currency text default 'EUR',
  fit_prefs jsonb default '{}'::jsonb,
  sizes jsonb default '{}'::jsonb,
  color_profile jsonb,
  created_at timestamptz default now()
);

create table images (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references users(id) on delete cascade,
  bucket_path text,
  source_url text,
  kind text not null check (kind in ('wardrobe','selfie','pin','product')),
  created_at timestamptz default now()
);

create table wardrobe_items (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references users(id) on delete cascade,
  image_id uuid references images(id) on delete set null,
  category text,
  subtype text,
  colors text[] default '{}',
  pattern text,
  material text,
  formality int,
  warmth int,
  style_tags text[] default '{}',
  raw jsonb,
  created_at timestamptz default now()
);
create index on wardrobe_items(user_id);

create table styles (
  id uuid primary key default gen_random_uuid(),
  name text not null unique,
  query text not null,
  summary jsonb,
  created_at timestamptz default now()
);

create table style_pins (
  id uuid primary key default gen_random_uuid(),
  style_id uuid not null references styles(id) on delete cascade,
  pin_url text unique,
  image_url text not null,
  title text
);

create table swipes (
  user_id uuid not null references users(id) on delete cascade,
  pin_id uuid not null references style_pins(id) on delete cascade,
  liked boolean not null,
  created_at timestamptz default now(),
  primary key (user_id, pin_id)
);

create table profiles (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references users(id) on delete cascade,
  style_mix jsonb,
  taste_summary text,
  gaps jsonb,
  queries text[] default '{}',
  created_at timestamptz default now()
);
create index on profiles(user_id, created_at desc);

create table products (
  id uuid primary key default gen_random_uuid(),
  url text not null unique,
  name text,
  description text,
  price numeric,
  currency text,
  image_url text,
  marketplace text,
  query text,
  raw jsonb,
  created_at timestamptz default now()
);

create table recommendation_sets (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references users(id) on delete cascade,
  profile_id uuid references profiles(id) on delete set null,
  params jsonb,
  created_at timestamptz default now()
);

create table recommendations (
  set_id uuid not null references recommendation_sets(id) on delete cascade,
  product_id uuid not null references products(id) on delete cascade,
  rank int,
  reason text,
  pairs_with uuid[] default '{}',
  primary key (set_id, product_id)
);

create table product_feedback (
  user_id uuid not null references users(id) on delete cascade,
  product_id uuid not null references products(id) on delete cascade,
  liked boolean,
  bought boolean default false,
  created_at timestamptz default now(),
  primary key (user_id, product_id)
);

create table link_checks (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references users(id) on delete cascade,
  product_id uuid references products(id) on delete set null,
  url text not null,
  score int,
  verdict jsonb,
  created_at timestamptz default now()
);

create table outfits (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references users(id) on delete cascade,
  date date default current_date,
  event text,
  city text,
  weather jsonb,
  item_ids uuid[] default '{}',
  explanation text,
  missing_item_tip text,
  feedback jsonb,
  created_at timestamptz default now()
);

create table jobs (
  id uuid primary key default gen_random_uuid(),
  kind text not null,
  user_id uuid references users(id) on delete cascade,
  status text not null default 'queued' check (status in ('queued','running','done','failed')),
  input jsonb,
  result jsonb,
  error text,
  created_at timestamptz default now(),
  updated_at timestamptz default now()
);

do $$ declare t text; begin
  foreach t in array array['users','images','wardrobe_items','styles','style_pins','swipes','profiles','products',
    'recommendation_sets','recommendations','product_feedback','link_checks','outfits','jobs'] loop
    execute format('alter table %I enable row level security', t);
  end loop;
end $$;

-- private bucket for user photos (served to the app/LLM via signed URLs)
insert into storage.buckets (id, name, public) values ('images', 'images', false)
on conflict (id) do nothing;
