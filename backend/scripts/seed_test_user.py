"""Create a test user with a real wardrobe (Wikimedia Commons photos, tagged by the vision model).

Uses the real container (Supabase + Featherless). Run from repo root:
    uv run python -m backend.scripts.seed_test_user            # seed only
    uv run python -m backend.scripts.seed_test_user --taste    # seed + build taste profile with Claude Opus
"""
import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

from backend.app.container import build_container
from backend.app.domain import ImageInput, sniff_mime

UA = {"User-Agent": "wardrobe-stylist/0.1 (hackathon test data)"}
OUT = Path(__file__).with_name("test_user.json")

OWNED = ["Chino pants.jpg", "Preppy oxford shirt.jpg", "White sneakers.jpg", "Jean jacket.jpg",
         "Chelsea boot, black.jpg", "Green Aran Sweater.JPG", "Marinière de la Marine nationale.JPG",
         "High waisted jeans 1435042736.jpg"]
WANTED = ["A Penny Loafer.jpg", "Cashmere Wool Scarves.jpg"]
INSPIRATION = ["Street Style at London Fashion Week 01.jpg", "Street Style at London Fashion Week 02.jpg",
               "Street Style at London Fashion Week 03.jpg", "PittiUomo.jpg"]
USER = {"name": "Test User (seed)", "city": "Prague", "budget": 200, "currency": "EUR",
        "fit_prefs": {"prefers": "regular to relaxed", "avoid": "skinny"}, "sizes": {"top": "M", "shoe": "43"}}


def commons_urls(titles: list[str], width: int = 640, attempts: int = 5) -> dict[str, str]:
    """One batched request (Commons rate-limits bursts), with backoff."""
    for attempt in range(attempts):
        resp = requests.get("https://commons.wikimedia.org/w/api.php", headers=UA, timeout=30, params={
            "action": "query", "titles": "|".join("File:" + t for t in titles), "prop": "imageinfo",
            "iiprop": "url", "iiurlwidth": width, "format": "json"})
        if resp.ok and resp.text.startswith("{"):
            break
        time.sleep(5 * (attempt + 1))
    r = resp.json()
    by_title = {p["title"][5:]: p["imageinfo"][0]["thumburl"] for p in r["query"]["pages"].values() if "imageinfo" in p}
    missing = [t for t in titles if t not in by_title]
    if missing:
        print("WARN missing on Commons:", missing, file=sys.stderr)
    return by_title


def download(url: str, attempts: int = 8) -> ImageInput:
    """Sequential + backoff: upload.wikimedia.org answers 429 to parallel bursts."""
    for attempt in range(attempts):
        resp = requests.get(url, headers=UA, timeout=30)
        if resp.status_code != 429:
            resp.raise_for_status()
            return ImageInput(resp.content, sniff_mime(resp.content), source_url=url)
        wait = int(resp.headers.get("retry-after") or 10 * (attempt + 1))
        print(f"  429 from Wikimedia, waiting {wait}s", file=sys.stderr)
        time.sleep(wait)
    resp.raise_for_status()


def main(build_taste: bool) -> None:
    # Fetch everything first, so a network failure never leaves a half-seeded user.
    urls = commons_urls(OWNED + WANTED + INSPIRATION)
    jobs = []
    for kind, titles in (("owned", OWNED), ("wanted", WANTED), ("inspiration", INSPIRATION)):
        for t in (t for t in titles if t in urls):
            jobs.append((kind, download(urls[t])))
            time.sleep(3)
    c = build_container()
    user = c.users.create(USER)
    uid = user["id"]
    print("user", uid)

    def add(args):
        kind, image = args
        if kind == "inspiration":
            return kind, c.inspirations.add(uid, [image])[0]
        return kind, c.wardrobe.add(uid, [image], status=kind)[0]

    with ThreadPoolExecutor(4) as pool:
        for kind, row in pool.map(add, jobs):
            label = row.get("subtype") or ", ".join(row.get("style_tags") or [])
            print(f"  {kind:11} {label} {row.get('colors') or row.get('palette')}")

    OUT.write_text(json.dumps({"user_id": uid, "name": USER["name"]}, indent=2))
    print("saved", OUT)

    if build_taste:
        print("evidence:", c.taste.counts(c.taste.evidence(uid)))
        profile = c.taste.build(uid)["profile"]
        print(json.dumps(profile, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--taste", action="store_true", help="also build the taste profile with Claude Opus")
    main(ap.parse_args().taste)
