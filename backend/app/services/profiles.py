from ..errors import NotFound
from ..ports import Database, Row
from .base import latest
from .preferences import PreferenceService
from .styles import StyleService
from .stylist import Stylist
from .users import UserService
from .wardrobe import WardrobeService, summarise

USER_FIELDS = ("city", "budget", "currency", "fit_prefs", "color_profile")


class ProfileService:
    def __init__(self, db: Database, users: UserService, wardrobe: WardrobeService, styles: StyleService,
                 prefs: PreferenceService, stylist: Stylist):
        self._db, self._users, self._wardrobe, self._styles, self._prefs, self._stylist = (
            db, users, wardrobe, styles, prefs, stylist)

    def compute(self, uid: str) -> Row:
        user = self._users.get(uid)
        links = self._db.select("link_checks", {"user_id": uid}, order_by="created_at", desc=True, limit=20)
        context = {
            "user": {k: user.get(k) for k in USER_FIELDS},
            "wardrobe": summarise(self._wardrobe.items(uid)),
            "style_library": self._styles.library(),
            **self._prefs.signals(uid),
            "checked_links": [{"score": l.get("score"), "verdict": (l.get("verdict") or {}).get("verdict")} for l in links],
        }
        p = self._stylist.profile(context)
        return self._db.insert("profiles", {"user_id": uid, "style_mix": p.get("style_mix"),
                                            "taste_summary": p.get("taste_summary"), "gaps": p.get("wardrobe_gaps"),
                                            "queries": p.get("shop_queries") or []})

    def current(self, uid: str) -> Row | None:
        return latest(self._db, "profiles", user_id=uid)

    def get(self, uid: str) -> Row:
        if not (p := self.current(uid)):
            raise NotFound("No profile yet; POST /users/{uid}/profile/compute")
        return p
