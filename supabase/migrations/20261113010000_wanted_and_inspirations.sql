-- Items: owned vs wanted (wishlist), optionally linked to a shop product.
alter table wardrobe_items
  add column status text not null default 'owned' check (status in ('owned', 'wanted')),
  add column product_id uuid references products(id) on delete set null;
create index on wardrobe_items(user_id, status);

-- Images can now also be inspiration looks.
alter table images drop constraint images_kind_check;
alter table images add constraint images_kind_check
  check (kind in ('wardrobe', 'selfie', 'pin', 'product', 'inspiration'));

-- Inspiration = a whole look (upload, URL or saved Pinterest pin), tagged by the vision model.
create table inspirations (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references users(id) on delete cascade,
  image_id uuid references images(id) on delete set null,
  pin_id uuid references style_pins(id) on delete set null,
  source_url text,
  style_tags text[] default '{}',
  palette text[] default '{}',
  formality int,
  vibe text,
  pieces jsonb default '[]'::jsonb,
  raw jsonb,
  created_at timestamptz default now(),
  unique (user_id, pin_id)
);
create index on inspirations(user_id);
alter table inspirations enable row level security;
