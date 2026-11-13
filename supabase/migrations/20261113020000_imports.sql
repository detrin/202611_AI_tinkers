-- Imports from URLs: retailer product pages and Instagram profiles/posts.

-- Where an item came from + a few fields the vision tagger now fills / the user maintains.
alter table wardrobe_items
  add column fit text,
  add column availability text not null default 'available'
    check (availability in ('available', 'laundry', 'lent', 'stored')),
  add column source_type text not null default 'upload'
    check (source_type in ('upload', 'product_url', 'instagram', 'pin')),
  add column source_url text;

-- Aggregated style inferred from the user's Instagram (style_tags, preferred_colors, preferred_fit, avoid_tags, ...).
alter table users add column style_profile jsonb;

alter table images drop constraint images_kind_check;
alter table images add constraint images_kind_check
  check (kind in ('wardrobe', 'selfie', 'pin', 'product', 'inspiration', 'instagram'));

-- One row per Instagram import: per-post outfit analyses + the aggregated style profile.
create table social_imports (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references users(id) on delete cascade,
  platform text not null default 'instagram',
  url text not null,
  posts jsonb default '[]'::jsonb,
  style_profile jsonb,
  item_ids uuid[] default '{}',
  created_at timestamptz default now()
);
create index on social_imports(user_id, created_at desc);
alter table social_imports enable row level security;
