"""URL imports: product pages (HTML parse + fallback) and Instagram (posts → style profile, optional items)."""
import pytest
import requests

from backend.app.adapters.apify import to_post
from backend.app.adapters.html import FallbackProductSource, parse_product_page
from backend.app.domain import Product, sniff_mime
from backend.app.errors import Invalid
from backend.app.services.imports import resolve

LD_PAGE = """<html><head>
<meta property="og:image" content="/og.jpg"><meta property="og:title" content="OG title">
<script type="application/ld+json">{"@context":"https://schema.org","@graph":[{"@type":"BreadcrumbList"},
 {"@type":["Product"],"name":"Wool coat","description":"100% wool, relaxed fit","material":"wool",
  "brand":{"@type":"Brand","name":"COS"},"image":["/coat.jpg"],
  "offers":[{"@type":"Offer","price":"199,90","priceCurrency":"EUR"}]}]}</script>
<script type="application/ld+json">{broken json</script></head></html>"""


# ---------- pure parsing ----------
def test_parse_product_page_prefers_json_ld():
    p = parse_product_page("https://shop.eu/p/1", LD_PAGE)
    assert (p.name, p.price, p.currency) == ("Wool coat", 199.9, "EUR")
    assert p.image_url == "https://shop.eu/coat.jpg" and p.marketplace == "shop.eu"
    assert p.raw["brand"] == "COS" and p.raw["material"] == "wool"


def test_parse_product_page_falls_back_to_opengraph_and_needs_an_image():
    og = '<meta property="og:image" content="https://cdn/x.jpg"><meta property="product:price:amount" content="10">'
    p = parse_product_page("https://s/p", og)
    assert (p.image_url, p.price, p.raw["source"]) == ("https://cdn/x.jpg", 10.0, "opengraph")
    assert parse_product_page("https://s/p", "<html>nothing</html>") is None


def test_fallback_source_uses_full_scraper_when_fast_fails_or_finds_nothing():
    class Fast:
        def __init__(self, result): self.result = result
        def details(self, url):
            if isinstance(self.result, Exception):
                raise self.result
            return self.result

    class Full:
        def details(self, url): return [Product(url=url, name="apify")]
        def search(self, *a): return []

    hit = [Product(url="u", name="html")]
    assert FallbackProductSource(Fast(hit), Full()).details("u")[0].name == "html"
    assert FallbackProductSource(Fast([]), Full()).details("u")[0].name == "apify"
    assert FallbackProductSource(Fast(requests.HTTPError("403")), Full()).details("u")[0].name == "apify"


def test_to_post_collects_carousel_images_and_skips_error_rows():
    post = to_post({"url": "https://ig/p/1", "displayUrl": "a", "images": ["a", "b"],
                    "childPosts": [{"displayUrl": "c"}], "caption": "fit check"})
    assert post.image_urls == ("a", "b", "c") and post.caption == "fit check"
    assert to_post({"error": "not_found", "url": "https://ig/x"}) is None


def test_sniff_mime():
    assert sniff_mime(b"\x89PNG....") == "image/png"
    assert sniff_mime(b"RIFF\x00\x00\x00\x00WEBPVP8") == "image/webp"
    assert sniff_mime(b"\xff\xd8\xff") == "image/jpeg"


@pytest.mark.parametrize("ref,expected", [
    ("@jane.doe", ("instagram", "https://www.instagram.com/jane.doe/")),
    ("jane_doe", ("instagram", "https://www.instagram.com/jane_doe/")),
    ("https://www.instagram.com/p/ABC123/", ("instagram", "https://www.instagram.com/p/ABC123/")),
    ("https://www.zalando.cz/coat.html", ("product", "https://www.zalando.cz/coat.html")),
])
def test_resolve_detects_kind(ref, expected):
    assert resolve(ref) == expected


def test_resolve_rejects_garbage_and_kind_mismatch():
    with pytest.raises(Invalid):
        resolve("not a url!")
    with pytest.raises(Invalid):
        resolve("https://www.instagram.com/jane/", "product")


# ---------- services ----------
def test_product_import_tags_with_page_context_and_records_source(env):
    uid = env.user()["id"]
    out = env.c.imports.product(uid, "https://shop/coat")
    item = out["item"]
    assert item["source_type"] == "product_url" and item["source_url"] == "https://shop/coat"
    assert item["product_id"] == out["product"]["id"] and item["status"] == "owned"
    tag_prompt = next(p for kind, p, _ in env.chat.calls if kind == "tag")
    assert "Product page text" in tag_prompt and "Linked thing" in tag_prompt


def test_product_import_without_scrapable_product_fails(env):
    uid = env.user()["id"]
    with pytest.raises(Invalid):
        env.c.imports.product(uid, "https://shop/broken")


def test_instagram_import_builds_style_profile_and_feeds_profile(env):
    uid = env.user()["id"]
    out = env.c.imports.instagram(uid, "https://www.instagram.com/jane/", 3, import_items=False)
    assert out["posts_analysed"] == 3 and out["items_added"] == []
    assert env.c.users.get(uid)["style_profile"]["style_tags"] == ["minimal", "classic"]
    assert len(env.c.imports.list(uid)) == 1
    assert sum(k == "post" for k, *_ in env.chat.calls) == 3
    env.c.profiles.compute(uid)
    profile_prompt = next(p for kind, p, _ in env.chat.calls if kind == "profile")
    assert "preferred_colors" in profile_prompt


def test_instagram_import_items_share_the_post_image(env):
    uid = env.user()["id"]
    out = env.c.imports.instagram(uid, "https://www.instagram.com/p/X/", 1, import_items=True)
    items = out["items_added"]
    assert len(items) == 2 and len({i["image_id"] for i in items}) == 1
    assert {i["source_type"] for i in items} == {"instagram"} and items[0]["source_url"].startswith("https://ig/")


def test_instagram_import_skips_failed_images_and_rejects_no_outfits(env):
    uid = env.user()["id"]
    env.chat.answers["post"] = {"has_outfit": False}
    with pytest.raises(Invalid):
        env.c.imports.instagram(uid, "https://www.instagram.com/jane/", 2, import_items=False)
    env.social.n = 0
    with pytest.raises(Invalid):
        env.c.imports.instagram(uid, "https://www.instagram.com/empty/", 2, import_items=False)


# ---------- API ----------
def test_import_endpoint_routes_by_kind(client, env):
    uid = client.post("/users", json={"name": "Dan"}).json()["id"]
    job = client.post(f"/users/{uid}/imports", json={"url": "@jane", "max_posts": 2}).json()
    done = client.get(f"/jobs/{job['job_id']}").json()
    assert done["status"] == "done" and done["kind"] == "import_instagram"
    assert env.social.urls == ["https://www.instagram.com/jane/"]
    job = client.post(f"/users/{uid}/imports", json={"url": "https://shop/coat"}).json()
    assert client.get(f"/jobs/{job['job_id']}").json()["result"]["kind"] == "product"
    assert len(client.get(f"/users/{uid}/imports").json()) == 1


def test_import_endpoint_validates_eagerly(client):
    uid = client.post("/users", json={"name": "Dan"}).json()["id"]
    assert client.post(f"/users/{uid}/imports", json={"url": "??"}).status_code == 422
    assert client.post("/users/nope/imports", json={"url": "@jane"}).status_code == 404
    assert client.post(f"/users/{uid}/imports", json={"url": "@jane", "max_posts": 99}).status_code == 422


# ---------- free-text description ----------
def test_item_description_is_stored_and_reaches_text_only_prompts(env):
    uid = env.user()["id"]
    item = env.items(uid, 1)[0]
    assert item["description"].startswith("Boxy white crew-neck")
    assert "description" in next(p for kind, p, _ in env.chat.calls if kind == "tag")
    assert env.c.taste.evidence(uid)["owned_items"][0]["description"] == item["description"]   # what Opus sees


def test_instagram_items_keep_their_description(env):
    uid = env.user()["id"]
    env.chat.answers["post"] = {"has_outfit": True, "items": [{"category": "top", "description": "Navy oxford"}]}
    items = env.c.imports.instagram(uid, "https://www.instagram.com/p/X/", 1, import_items=True)["items_added"]
    assert items[0]["description"] == "Navy oxford"
