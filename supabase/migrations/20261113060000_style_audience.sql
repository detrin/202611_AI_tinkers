-- Who a style is typically worn by, so e.g. womenswear-only aesthetics are not recommended to a menswear user.
alter table styles add column audience text not null default 'unisex' check (audience in ('menswear', 'womenswear', 'unisex'));
