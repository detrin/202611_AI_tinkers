"""Cheap product-page scraping: JSON-LD `Product` + OpenGraph meta, with Apify as the fallback for hard shops.

Parsing is pure (`parse_product_page`, unit-tested); `HtmlProductSource` only adds the HTTP GET.
"""
import json
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import requests

from ..domain import Product
from ..ports import ProductSource

BROWSER_UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 (KHTML, like Gecko) "
                            "Chrome/130.0 Safari/537.36", "Accept-Language": "en;q=0.9"}


class _PageParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.meta: dict[str, str] = {}
        self.ld_json: list[str] = []
        self._in_ld = False

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "meta" and (key := a.get("property") or a.get("name")) and a.get("content"):
            self.meta.setdefault(key.lower(), a["content"])
        elif tag == "script" and (a.get("type") or "").lower() == "application/ld+json":
            self._in_ld = True
            self.ld_json.append("")

    def handle_endtag(self, tag):
        if tag == "script":
            self._in_ld = False

    def handle_data(self, data):
        if self._in_ld:
            self.ld_json[-1] += data


def _walk(node):
    """Yield every dict in a JSON-LD tree (handles lists and @graph)."""
    if isinstance(node, dict):
        yield node
        for v in node.values():
            yield from _walk(v)
    elif isinstance(node, list):
        for v in node:
            yield from _walk(v)


def _is_product(d: dict) -> bool:
    t = d.get("@type")
    return "Product" in (t if isinstance(t, list) else [t])


def _first_image(value) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, list) and value:
        return _first_image(value[0])
    if isinstance(value, dict):
        return value.get("url") or value.get("contentUrl")
    return None


def _ld_product(blobs: list[str]) -> dict:
    for blob in blobs:
        try:
            tree = json.loads(blob)
        except ValueError:
            continue
        if found := next((d for d in _walk(tree) if _is_product(d)), None):
            return found
    return {}


def _price(value) -> float | None:
    try:
        return float(str(value).replace(",", ".")) if value not in (None, "") else None
    except ValueError:
        return None


def parse_product_page(url: str, html: str) -> Product | None:
    p = _PageParser()
    p.feed(html)
    ld, m = _ld_product(p.ld_json), p.meta
    offers = ld.get("offers") or {}
    offer = offers[0] if isinstance(offers, list) and offers else offers if isinstance(offers, dict) else {}
    image = _first_image(ld.get("image")) or m.get("og:image") or m.get("twitter:image")
    if not image:
        return None
    brand = ld.get("brand")
    raw = {k: v for k, v in {
        "brand": brand.get("name") if isinstance(brand, dict) else brand,
        "material": ld.get("material"), "color": ld.get("color"), "category": ld.get("category"),
        "sku": ld.get("sku"), "source": "json-ld" if ld else "opengraph"}.items() if v}
    return Product(
        url=url, name=ld.get("name") or m.get("og:title"),
        description=(ld.get("description") or m.get("og:description") or "")[:4000] or None,
        price=_price(offer.get("price") or offer.get("lowPrice") or m.get("product:price:amount")),
        currency=offer.get("priceCurrency") or m.get("product:price:currency"),
        image_url=urljoin(url, image), marketplace=urlparse(url).netloc, raw=raw,
    )


class HtmlProductSource:
    """`details` only: one GET, no headless browser. Direct image links become an imageless-metadata Product."""

    def __init__(self, session: requests.Session | None = None, timeout: int = 15):
        self._s, self._timeout = session or requests.Session(), timeout

    def details(self, url: str) -> list[Product]:
        r = self._s.get(url, headers=BROWSER_UA, timeout=self._timeout)
        r.raise_for_status()
        if r.headers.get("content-type", "").startswith("image/"):
            return [Product(url=url, image_url=url, marketplace=urlparse(url).netloc, raw={"source": "direct_image"})]
        product = parse_product_page(url, r.text)
        return [product] if product else []


class FallbackProductSource:
    """Search goes to the full scraper; details try the cheap HTML parse first, then the full scraper."""

    def __init__(self, fast: HtmlProductSource, full: ProductSource):
        self._fast, self._full = fast, full

    def search(self, query: str, marketplaces: list[str], limit: int) -> list[Product]:
        return self._full.search(query, marketplaces, limit)

    def details(self, url: str) -> list[Product]:
        try:
            if found := self._fast.details(url):
                return found
        except requests.RequestException:
            pass   # blocked / bot-walled shop → let Apify's browser handle it
        return self._full.details(url)
