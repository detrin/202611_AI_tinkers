from ..errors import Conflict
from ..ports import Database, Row
from .base import get_one
from .catalog import CatalogService
from .profiles import ProfileService
from .stylist import Stylist
from .wardrobe import WardrobeService, summarise

MAX_QUERIES = 5


class RecommendationService:
    def __init__(self, db: Database, catalog: CatalogService, profiles: ProfileService, wardrobe: WardrobeService,
                 stylist: Stylist):
        self._db, self._catalog, self._profiles, self._wardrobe, self._stylist = db, catalog, profiles, wardrobe, stylist

    def queries_for(self, uid: str, override: list[str] | None) -> list[str]:
        """Validated eagerly (before a job is queued)."""
        queries = override or (self._profiles.current(uid) or {}).get("queries")
        if not queries:
            raise Conflict("Compute a profile first or pass queries")
        return queries[:MAX_QUERIES]

    def create(self, uid: str, queries: list[str], n: int, per_query: int, marketplaces: list[str]) -> dict:
        products = self._candidates(queries, marketplaces, per_query)
        wardrobe = self._wardrobe.items(uid)
        profile = self._profiles.current(uid) or {}
        candidates = [{"id": i, "name": p["name"], "price": p.get("price"), "currency": p.get("currency")}
                      for i, p in enumerate(products)]
        picks = self._stylist.rank_products(profile, summarise(wardrobe), candidates, n) if products else []
        rec_set = self._db.insert("recommendation_sets", {
            "user_id": uid, "profile_id": profile.get("id"),
            "params": {"queries": queries, "n": n, "per_query": per_query, "marketplaces": marketplaces}})
        rows = self._rows(rec_set["id"], picks, products, {w["id"] for w in wardrobe})
        if rows:
            self._db.upsert("recommendations", rows, "set_id,product_id")
        return {"rec_set_id": rec_set["id"], "count": len(rows)}

    def _candidates(self, queries: list[str], marketplaces: list[str], per_query: int) -> list[Row]:
        found = {p["id"]: p for q in queries for p in self._catalog.search(q, marketplaces, per_query)}
        return [p for p in found.values() if p.get("image_url")]

    @staticmethod
    def _rows(set_id: str, picks: list[dict], products: list[Row], wardrobe_ids: set[str]) -> list[Row]:
        rows: dict[str, Row] = {}
        for rank, pick in enumerate(picks):
            idx = pick.get("id")
            if not isinstance(idx, int) or not 0 <= idx < len(products):
                continue   # LLM hallucinated an id
            pid = products[idx]["id"]
            rows.setdefault(pid, {"set_id": set_id, "product_id": pid, "rank": rank, "reason": pick.get("reason"),
                                  "pairs_with": [w for w in pick.get("pairs_with", []) if w in wardrobe_ids]})
        return list(rows.values())

    def get(self, uid: str, set_id: str) -> list[Row]:
        get_one(self._db, "recommendation_sets", id=set_id, user_id=uid)
        recs = self._db.select("recommendations", {"set_id": set_id}, order_by="rank")
        products = {p["id"]: p for p in self._db.select("products", in_={"id": [r["product_id"] for r in recs]})} if recs else {}
        return [{**r, "product": products.get(r["product_id"])} for r in recs]
