"""Apify-backed PinSource, ProductSource and SocialSource (Instagram). Normalisers are pure functions (unit-tested)."""
from datetime import timedelta
from decimal import Decimal

from apify_client import ApifyClient

from ..domain import Pin, Product, SocialPost

PINTEREST_ACTOR = "epctex/pinterest-scraper"
ECOMMERCE_ACTOR = "apify/e-commerce-scraping-tool"
INSTAGRAM_ACTOR = "apify/instagram-scraper"


class ApifyRunner:
    def __init__(self, client: ApifyClient, max_charge_usd: str = "1", timeout_min: int = 8):
        self._c, self._cap, self._timeout = client, Decimal(max_charge_usd), timedelta(minutes=timeout_min)

    def run(self, actor: str, run_input: dict) -> list[dict]:
        run = self._c.actor(actor).call(run_input=run_input, max_total_charge_usd=self._cap,
                                        run_timeout=self._timeout, logger=None)
        run = run if isinstance(run, dict) else run.model_dump(by_alias=True)
        if run.get("status") != "SUCCEEDED":
            raise RuntimeError(f"{actor} run {run.get('id')} ended with {run.get('status')}")
        return self._c.dataset(run["defaultDatasetId"]).list_items().items


def to_pin(item: dict) -> Pin | None:
    image = ((item.get("images") or {}).get("474x") or {}).get("url")
    return Pin(url=item.get("url"), image_url=image, title=item.get("grid_title") or item.get("title")) if image else None


def _price(value) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def to_product(item: dict) -> Product | None:
    if not item.get("url"):
        return None
    offers = item.get("offers") or {}
    offer = offers[0] if isinstance(offers, list) and offers else offers if isinstance(offers, dict) else {}
    image = item.get("image")
    return Product(
        url=item["url"], name=item.get("name"), description=(item.get("description") or "")[:4000],
        price=_price(offer.get("price", item.get("price"))), currency=offer.get("priceCurrency") or item.get("currency"),
        image_url=image if isinstance(image, str) else None, marketplace=item.get("marketplace"), raw=item,
    )


def to_post(item: dict) -> SocialPost | None:
    """Image post, carousel (childPosts) or video (thumbnail). Error rows (private/missing profile) have no images."""
    urls = [item.get("displayUrl"), *(item.get("images") or []), *(c.get("displayUrl") for c in item.get("childPosts") or [])]
    urls = tuple(dict.fromkeys(u for u in urls if isinstance(u, str) and u))
    if not urls or not item.get("url"):
        return None
    return SocialPost(url=item["url"], image_urls=urls, caption=(item.get("caption") or "")[:1000] or None,
                      timestamp=item.get("timestamp"))


class ApifyPinSource:
    def __init__(self, runner: ApifyRunner):
        self._runner = runner

    def search(self, query: str, limit: int) -> list[Pin]:
        items = self._runner.run(PINTEREST_ACTOR, {"search": query, "maxItems": limit, "getDetails": False, "endPage": 1})
        return [p for p in map(to_pin, items) if p]


class ApifyProductSource:
    def __init__(self, runner: ApifyRunner):
        self._runner = runner

    def _run(self, run_input: dict) -> list[Product]:
        return [p for p in map(to_product, self._runner.run(ECOMMERCE_ACTOR, run_input)) if p]

    def search(self, query: str, marketplaces: list[str], limit: int) -> list[Product]:
        return self._run({"keyword": query, "marketplaces": marketplaces, "maxProductResults": limit})

    def details(self, url: str) -> list[Product]:
        return self._run({"detailsUrls": [{"url": url}], "maxProductResults": 1})


class ApifyInstagramSource:
    """Public profile or single post/reel URL → newest posts."""

    def __init__(self, runner: ApifyRunner):
        self._runner = runner

    def posts(self, url: str, limit: int) -> list[SocialPost]:
        items = self._runner.run(INSTAGRAM_ACTOR, {"directUrls": [url], "resultsType": "posts",
                                                   "resultsLimit": limit, "addParentData": False})
        return [p for p in map(to_post, items) if p][:limit]
