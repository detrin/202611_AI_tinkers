"""Create the demo user from a folder of real photos of owned clothes (e.g. ~/Downloads/Demo-whatIown-photos),
or add more photos to the existing demo user with --append.

File names like `jackets-01.jpg` / `pants-03.jpg` give the tagger a category hint (or pass --label for folders
with hash file names). Photos are downscaled to 1024 px JPEG before upload. Run from repo root:
    uv run python -m backend.scripts.seed_demo_user --dir ~/Downloads/Demo-whatIown-photos --taste
    uv run python -m backend.scripts.seed_demo_user --dir "~/Downloads/hoodie design" --label hoodies --append --taste
"""
import argparse
import io
import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image, ImageOps

from backend.app.container import build_container
from backend.app.domain import ImageInput
from backend.app.services.users import DEMO_USER_NAME

OUT = Path(__file__).with_name("demo_user.json")
EXTS = {".jpg", ".jpeg", ".png", ".webp", ".avif"}
MAX_SIDE = 1024
USER = {"name": DEMO_USER_NAME, "city": "Prague", "budget": 250, "currency": "EUR",
        "fit_prefs": {"prefers": "regular"}, "sizes": {}}


def load(path: Path) -> ImageInput:
    img = ImageOps.exif_transpose(Image.open(path))
    img = img.convert("RGBA").convert("RGB") if img.mode == "P" else img.convert("RGB")
    img.thumbnail((MAX_SIDE, MAX_SIDE))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=88)
    return ImageInput(buf.getvalue(), "image/jpeg")


def category_hint(path: Path, label: str | None = None) -> dict:
    return {"photo_folder_label": label or path.stem.rsplit("-", 1)[0]}     # "jackets-01" -> "jackets"


def main(folder: Path, build_taste: bool, workers: int, append: bool = False, label: str | None = None) -> None:
    photos = sorted(p for p in folder.expanduser().iterdir() if p.suffix.lower() in EXTS)
    if not photos:
        raise SystemExit(f"No photos in {folder}")
    images = {p: load(p) for p in photos}                  # fail on unreadable files before creating the user
    c = build_container()
    uid = c.users.demo_user()["id"] if append else c.users.create(USER)["id"]
    print(f"user {uid} ({'append' if append else 'new'}): {len(photos)} photos", flush=True)

    def existing(marker: str):
        return next((i for i in c.wardrobe.items(uid) if i.get("source_url") == marker), None)

    def add(path: Path, attempts: int = 3):
        """Idempotent: the file name is stored as source_url, so a retry after a dropped connection
        (where the insert may already have landed) never creates a duplicate."""
        marker = f"file:{path.name}"
        for attempt in range(attempts):
            try:
                item = existing(marker) or c.wardrobe.add(uid, [images[path]], context=category_hint(path, label),
                                                          source={"source_type": "upload", "source_url": marker})[0]
                return path.name, f"{item.get('category')}/{item.get('subtype')} {item.get('colors')}"
            except Exception as e:  # noqa: BLE001 — transient network errors; retry, then report
                error = e
                time.sleep(3 * (attempt + 1))
        return path.name, f"SKIPPED ({type(error).__name__}: {str(error)[:100]})"

    with ThreadPoolExecutor(workers) as pool:
        for name, label in pool.map(add, photos):
            print(f"  {name:18} -> {label}", flush=True)

    OUT.write_text(json.dumps({"user_id": uid, "name": DEMO_USER_NAME}, indent=2) + "\n")
    print("saved", OUT, flush=True)
    if build_taste:
        print("evidence:", c.taste.counts(c.taste.evidence(uid)), flush=True)
        print(json.dumps(c.taste.build(uid)["profile"], indent=2, ensure_ascii=False))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", type=Path, default=Path("~/Downloads/Demo-whatIown-photos"))
    ap.add_argument("--taste", action="store_true", help="also build the taste profile with Claude Opus")
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--append", action="store_true", help="add to the existing demo user instead of creating one")
    ap.add_argument("--label", help="category hint for every photo (for folders without category file names)")
    args = ap.parse_args()
    main(args.dir, args.taste, args.workers, args.append, args.label)
