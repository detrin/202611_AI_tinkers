-- Free-text visual description of each garment (from the vision tagger). Text-only models (e.g. Opus taste profile)
-- never see images, so this is how visual details reach them.
alter table wardrobe_items add column if not exists description text;

-- Backfill items tagged before this column existed, if the tagger's raw output already had one.
update wardrobe_items set description = raw->>'description' where description is null and raw ? 'description';
