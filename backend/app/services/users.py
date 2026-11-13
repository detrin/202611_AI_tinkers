from ..domain import ImageInput
from ..errors import NotFound
from ..ports import Database, Row
from .base import get_one
from .images import ImageService
from .stylist import Stylist

TEST_USER_NAME = "Test User (seed)"   # created by backend/scripts/seed_test_user.py (Pinterest photos)
DEMO_USER_NAME = "Demo User"          # created by backend/scripts/seed_demo_user.py (real photos of owned clothes)
LIST_FIELDS = ("id", "name", "city", "created_at")


class UserService:
    def __init__(self, db: Database, images: ImageService, stylist: Stylist):
        self._db, self._images, self._stylist = db, images, stylist

    def create(self, data: Row) -> Row:
        return self._db.insert("users", data)

    def get(self, uid: str) -> Row:
        return get_one(self._db, "users", id=uid)

    def list(self, name: str | None = None, limit: int = 50) -> list[Row]:
        """Newest first; `name` is a case-insensitive substring filter. Compact rows (no profiles)."""
        rows = self._db.select("users", order_by="created_at", desc=True)
        rows = [r for r in rows if not name or name.lower() in (r.get("name") or "").lower()]
        return [{k: r.get(k) for k in LIST_FIELDS} for r in rows[:limit]]

    def seeded(self, name: str, script: str) -> Row:
        """Latest user with this exact seed name, so UIs and teammates never need ids passed around."""
        rows = self._db.select("users", {"name": name}, order_by="created_at", desc=True, limit=1)
        if not rows:
            raise NotFound(f"No '{name}' user yet; run: uv run python -m backend.scripts.{script} --taste")
        return rows[0]

    def test_user(self) -> Row:
        return self.seeded(TEST_USER_NAME, "seed_test_user")

    def demo_user(self) -> Row:
        return self.seeded(DEMO_USER_NAME, "seed_demo_user")

    def update(self, uid: str, patch: Row) -> Row:
        self.get(uid)
        return self._db.update("users", {"id": uid}, patch)[0] if patch else self.get(uid)

    def analyse_selfie(self, uid: str, image: ImageInput) -> dict:
        self.get(uid)
        self._images.save(uid, "selfie", image)
        profile = self._stylist.color_analysis(image.data_url)
        self._db.update("users", {"id": uid}, {"color_profile": profile})
        return profile
