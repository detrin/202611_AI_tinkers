-- Explore/exploit swipe deck: remember what was served (so pins are never shown twice) and how.
create table pin_impressions (
  user_id uuid not null references users(id) on delete cascade,
  pin_id uuid not null references style_pins(id) on delete cascade,
  mode text check (mode in ('explore', 'exploit')),
  p_like real,                       -- model's belief for the pin's style when served
  served_at timestamptz default now(),
  primary key (user_id, pin_id)
);
alter table pin_impressions enable row level security;

-- Swipes = the "interested" / "not interested" boards. Record how the pin was served and where it was swiped.
alter table swipes
  add column mode text check (mode in ('explore', 'exploit')),
  add column source text not null default 'deck' check (source in ('deck', 'recommendations'));
create index on swipes(user_id, liked, created_at desc);
