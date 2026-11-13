"""Create a test user with a real wardrobe: Pinterest photos (via Apify) tagged by the vision model.

Uses the real container (Supabase + Featherless + Apify). Run from repo root:
    uv run python -m backend.scripts.seed_test_user            # wardrobe, wishlist, inspirations
    uv run python -m backend.scripts.seed_test_user --taste    # ...plus taste profile with Claude Opus
"""
import argparse
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from apify_client import ApifyClient

from backend.app.adapters.apify import ApifyPinSource, ApifyRunner
from backend.app.config import read_secret
from backend.app.container import build_container

OUT = Path(__file__).with_name("test_user.json")

# One Pinterest search per item; the first pin with an image is used.
OWNED = ["white oxford shirt men flat lay", "beige chino trousers men", "white leather sneakers minimalist",
         "light wash denim jacket men", "black chelsea boots men", "grey crew neck wool sweater men",
         "navy breton striped shirt", "dark indigo straight leg jeans men"]
WANTED = ["brown penny loafers men", "camel cashmere scarf"]
INSPIRATION = ["old money outfit men street style", "quiet luxury men outfit", "dark academia men outfit",
               "scandinavian minimalist men outfit"]
USER = {"name": "Test User (seed)", "city": "Prague", "budget": 200, "currency": "EUR",
        "fit_prefs": {"prefers": "regular to relaxed", "avoid": "skinny"}, "sizes": {"top": "M", "shoe": "43"}}


def first_pin_images(queries: list[str]) -> dict[str, str]:
    pins = ApifyPinSource(ApifyRunner(ApifyClient(read_secret("APIFY_TOKEN"))))
    with ThreadPoolExecutor(4) as pool:
        found = pool.map(lambda q: (q, next((p.image_url for p in pins.search(q, 5)), None)), queries)
    return {q: url for q, url in found if url}


def main(build_taste: bool) -> None:
    plan = [("owned", q) for q in OWNED] + [("wanted", q) for q in WANTED] + [("inspiration", q) for q in INSPIRATION]
    urls = first_pin_images([q for _, q in plan])          # resolve first: a failure leaves no half-seeded user
    if len(urls) < len(plan) // 2:
        raise SystemExit(f"Only {len(urls)}/{len(plan)} images found on Pinterest; not creating the user.")
    c = build_container()
    uid = c.users.create(USER)["id"]
    print("user", uid, flush=True)

    def add(item):
        kind, query = item
        try:
            image = c.images.from_url(urls[query])
            row = c.inspirations.add(uid, [image])[0] if kind == "inspiration" else c.wardrobe.add(uid, [image], status=kind)[0]
        except Exception as e:  # noqa: BLE001 — one bad image shouldn't sink the whole seed
            row = {"subtype": f"SKIPPED ({type(e).__name__}: {str(e)[:80]})"}
        return kind, query, row

    with ThreadPoolExecutor(4) as pool:
        for kind, query, row in pool.map(add, [p for p in plan if p[1] in urls]):
            label = row.get("subtype") or ", ".join(row.get("style_tags") or [])
            print(f"  {kind:11} {query:40} -> {label} {row.get('colors') or row.get('palette')}", flush=True)

    OUT.write_text(json.dumps({"user_id": uid, "name": USER["name"]}, indent=2) + "\n")
    print("saved", OUT, flush=True)
    if build_taste:
        print("evidence:", c.taste.counts(c.taste.evidence(uid)), flush=True)
        print(json.dumps(c.taste.build(uid)["profile"], indent=2, ensure_ascii=False))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--taste", action="store_true", help="also build the taste profile with Claude Opus")
    main(ap.parse_args().taste)
