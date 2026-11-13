"""Wardrobe stylist API. Run: uv run uvicorn backend.app.main:app --reload"""
import traceback
from datetime import date as Date

from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from . import ai
from .core import data_url, db, fetch_bytes, run_actor, signed_url, store_image, upsert_products, weather

app = FastAPI(title="Wardrobe stylist API", version="0.1")
PINTEREST = "epctex/pinterest-scraper"
ECOM = "apify/e-commerce-scraping-tool"


# ---------- helpers ----------
def one(table: str, **eq) -> dict:
    q = db().table(table).select("*")
    for k, v in eq.items():
        q = q.eq(k, v)
    rows = q.limit(1).execute().data
    if not rows:
        raise HTTPException(404, f"{table} not found")
    return rows[0]


def wardrobe_of(uid: str) -> list[dict]:
    return db().table("wardrobe_items").select("*").eq("user_id", uid).execute().data


def latest_profile(uid: str) -> dict | None:
    rows = db().table("profiles").select("*").eq("user_id", uid).order("created_at", desc=True).limit(1).execute().data
    return rows[0] if rows else None


def with_image_urls(items: list[dict]) -> list[dict]:
    ids = [i["image_id"] for i in items if i.get("image_id")]
    paths = {r["id"]: r["bucket_path"] for r in db().table("images").select("id,bucket_path").in_("id", ids).execute().data} if ids else {}
    return [{**i, "image_url": signed_url(paths.get(i.get("image_id")))} for i in items]


def start_job(bg: BackgroundTasks, kind: str, uid: str | None, payload: dict, fn) -> dict:
    job = db().table("jobs").insert({"kind": kind, "user_id": uid, "input": payload}).execute().data[0]

    def runner():
        db().table("jobs").update({"status": "running", "updated_at": "now()"}).eq("id", job["id"]).execute()
        try:
            result = fn()
            db().table("jobs").update({"status": "done", "result": result, "updated_at": "now()"}).eq("id", job["id"]).execute()
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            db().table("jobs").update({"status": "failed", "error": repr(e)[:2000], "updated_at": "now()"}).eq("id", job["id"]).execute()

    bg.add_task(runner)
    return {"job_id": job["id"], "status": "queued"}


async def read_upload_or_url(file: UploadFile | None, image_url: str | None) -> tuple[bytes, str, str | None]:
    if file:
        return await file.read(), file.content_type or "image/jpeg", None
    if image_url:
        return fetch_bytes(image_url), "image/jpeg", image_url
    raise HTTPException(422, "Provide file or image_url")


# ---------- utility ----------
@app.get("/health")
def health():
    return {"ok": True}


@app.get("/jobs/{job_id}")
def get_job(job_id: str):
    return one("jobs", id=job_id)


@app.get("/weather")
def get_weather(city: str, date: Date | None = None):
    return weather(city, date.isoformat() if date else None)


# ---------- users ----------
class UserIn(BaseModel):
    name: str
    city: str | None = None
    budget: float | None = None
    currency: str = "EUR"
    fit_prefs: dict = {}
    sizes: dict = {}


class UserPatch(BaseModel):
    name: str | None = None
    city: str | None = None
    budget: float | None = None
    currency: str | None = None
    fit_prefs: dict | None = None
    sizes: dict | None = None


@app.post("/users")
def create_user(u: UserIn):
    return db().table("users").insert(u.model_dump()).execute().data[0]


@app.get("/users/{uid}")
def get_user(uid: str):
    return one("users", id=uid)


@app.patch("/users/{uid}")
def patch_user(uid: str, u: UserPatch):
    return db().table("users").update(u.model_dump(exclude_none=True)).eq("id", uid).execute().data[0]


@app.post("/users/{uid}/selfie")
async def selfie(uid: str, file: UploadFile | None = File(None), image_url: str | None = Form(None)):
    one("users", id=uid)
    content, mime, src = await read_upload_or_url(file, image_url)
    store_image(uid, "selfie", content, mime, src)
    cp = ai.color_analysis(data_url(content, mime))
    db().table("users").update({"color_profile": cp}).eq("id", uid).execute()
    return cp


# ---------- wardrobe ----------
@app.post("/users/{uid}/wardrobe")
async def add_wardrobe(uid: str, files: list[UploadFile] | None = File(None), image_urls: list[str] | None = Form(None)):
    """Multipart: one or more `files`, and/or one or more `image_urls` form fields."""
    one("users", id=uid)
    sources = [(await f.read(), f.content_type or "image/jpeg", None) for f in files or []]
    sources += [(fetch_bytes(u), "image/jpeg", u) for u in image_urls or []]
    if not sources:
        raise HTTPException(422, "Provide files or image_urls")
    out = []
    for content, mime, src in sources:
        img = store_image(uid, "wardrobe", content, mime, src)
        t = ai.tag_item(data_url(content, mime))
        row = {"user_id": uid, "image_id": img["id"], "category": t.get("category"), "subtype": t.get("subtype"),
               "colors": t.get("colors") or [], "pattern": t.get("pattern"), "material": t.get("material"),
               "formality": t.get("formality_1to5"), "warmth": t.get("warmth_1to5"),
               "style_tags": t.get("style_tags") or [], "raw": t}
        out.append(db().table("wardrobe_items").insert(row).execute().data[0])
    return with_image_urls(out)


@app.get("/users/{uid}/wardrobe")
def list_wardrobe(uid: str, category: str | None = None, color: str | None = None):
    q = db().table("wardrobe_items").select("*").eq("user_id", uid)
    if category:
        q = q.eq("category", category)
    if color:
        q = q.contains("colors", [color])
    return with_image_urls(q.order("created_at").execute().data)


class ItemPatch(BaseModel):
    category: str | None = None
    subtype: str | None = None
    colors: list[str] | None = None
    pattern: str | None = None
    material: str | None = None
    formality: int | None = None
    warmth: int | None = None
    style_tags: list[str] | None = None


@app.get("/users/{uid}/wardrobe/{item_id}")
def get_item(uid: str, item_id: str):
    return with_image_urls([one("wardrobe_items", id=item_id, user_id=uid)])[0]


@app.patch("/users/{uid}/wardrobe/{item_id}")
def patch_item(uid: str, item_id: str, p: ItemPatch):
    return db().table("wardrobe_items").update(p.model_dump(exclude_none=True)).eq("id", item_id).eq("user_id", uid).execute().data[0]


@app.delete("/users/{uid}/wardrobe/{item_id}")
def delete_item(uid: str, item_id: str):
    db().table("wardrobe_items").delete().eq("id", item_id).eq("user_id", uid).execute()
    return {"deleted": item_id}


# ---------- styles ----------
@app.get("/styles")
def list_styles():
    return db().table("styles").select("*").order("name").execute().data


@app.get("/styles/{style_id}")
def get_style(style_id: str):
    s = one("styles", id=style_id)
    s["pins"] = db().table("style_pins").select("*").eq("style_id", style_id).execute().data
    return s


class StylesRefresh(BaseModel):
    queries: list[str]          # e.g. ["scandinavian minimalist outfit", "old money outfit"]
    pins_per_style: int = 12


@app.post("/styles/refresh")
def refresh_styles(req: StylesRefresh, bg: BackgroundTasks):
    def work():
        done = []
        for q in req.queries:
            items = run_actor(PINTEREST, {"search": q, "maxItems": req.pins_per_style, "getDetails": False, "endPage": 1})
            pins = [{"pin_url": i.get("url"), "image_url": i["images"]["474x"]["url"],
                     "title": i.get("grid_title") or i.get("title")} for i in items if i.get("images", {}).get("474x")]
            summary = ai.summarise_style(q, [p["image_url"] for p in pins])
            style = db().table("styles").upsert({"name": q, "query": q, "summary": summary}, on_conflict="name").execute().data[0]
            if pins:
                db().table("style_pins").upsert([{**p, "style_id": style["id"]} for p in pins], on_conflict="pin_url").execute()
            done.append({"style_id": style["id"], "name": q, "pins": len(pins)})
        return {"styles": done}
    return start_job(bg, "styles_refresh", None, req.model_dump(), work)


# ---------- swipes ----------
@app.get("/users/{uid}/swipe-deck")
def swipe_deck(uid: str, n: int = 20):
    seen = {s["pin_id"] for s in db().table("swipes").select("pin_id").eq("user_id", uid).execute().data}
    pins = db().table("style_pins").select("id,image_url,title,style_id").limit(500).execute().data
    by_style: dict[str, list] = {}
    for p in pins:
        if p["id"] not in seen:
            by_style.setdefault(p["style_id"], []).append(p)
    deck, i = [], 0
    while len(deck) < n and any(by_style.values()):   # round-robin across styles
        for lst in by_style.values():
            if lst and len(deck) < n:
                deck.append(lst.pop(0))
        i += 1
    return deck


class Swipe(BaseModel):
    pin_id: str
    liked: bool


@app.post("/users/{uid}/swipes")
def add_swipes(uid: str, swipes: list[Swipe]):
    rows = [{"user_id": uid, **s.model_dump()} for s in swipes]
    db().table("swipes").upsert(rows, on_conflict="user_id,pin_id").execute()
    return {"saved": len(rows)}


# ---------- profile ----------
@app.post("/users/{uid}/profile/compute")
def compute_profile(uid: str):
    user = one("users", id=uid)
    wd = [{k: w.get(k) for k in ["subtype", "category", "colors", "pattern", "material", "formality", "style_tags"]}
          for w in wardrobe_of(uid)]
    styles = [{"name": s["name"], **(s.get("summary") or {})} for s in list_styles()]
    sw = db().table("swipes").select("liked, style_pins(title, styles(name))").eq("user_id", uid).execute().data
    fmt = lambda s: {"style": ((s.get("style_pins") or {}).get("styles") or {}).get("name"), "title": (s.get("style_pins") or {}).get("title")}
    links = db().table("link_checks").select("url, score, products(name)").eq("user_id", uid).limit(20).execute().data
    p = ai.compute_profile(user, wd, styles, [fmt(s) for s in sw if s["liked"]], [fmt(s) for s in sw if not s["liked"]],
                           [{"name": (l.get("products") or {}).get("name"), "score": l.get("score")} for l in links])
    row = {"user_id": uid, "style_mix": p.get("style_mix"), "taste_summary": p.get("taste_summary"),
           "gaps": p.get("wardrobe_gaps"), "queries": p.get("shop_queries") or []}
    return db().table("profiles").insert(row).execute().data[0]


@app.get("/users/{uid}/profile")
def get_profile(uid: str):
    p = latest_profile(uid)
    if not p:
        raise HTTPException(404, "No profile yet — POST /users/{uid}/profile/compute")
    return p


# ---------- recommendations ----------
class RecIn(BaseModel):
    n: int = 5
    per_query: int = 6
    marketplaces: list[str] = ["www.etsy.com"]
    queries: list[str] | None = None   # override profile queries


@app.post("/users/{uid}/recommendations")
def create_recs(uid: str, req: RecIn, bg: BackgroundTasks):
    profile = latest_profile(uid)
    if not profile and not req.queries:
        raise HTTPException(409, "Compute a profile first or pass queries")

    def work():
        products = []
        for q in (req.queries or profile["queries"])[:5]:
            items = run_actor(ECOM, {"keyword": q, "marketplaces": req.marketplaces, "maxProductResults": req.per_query})
            products += upsert_products(items, q)
        products = [p for p in {p["id"]: p for p in products}.values() if p.get("image_url")]
        wd = wardrobe_of(uid)
        picks = ai.rank_products(profile or {}, wd, products, req.n)
        rs = db().table("recommendation_sets").insert({"user_id": uid, "profile_id": (profile or {}).get("id"),
                                                       "params": req.model_dump()}).execute().data[0]
        valid_wd = {w["id"] for w in wd}
        rows = [{"set_id": rs["id"], "product_id": products[p["id"]]["id"], "rank": r, "reason": p.get("reason"),
                 "pairs_with": [x for x in p.get("pairs_with", []) if x in valid_wd]}
                for r, p in enumerate(picks) if isinstance(p.get("id"), int) and p["id"] < len(products)]
        rows = list({r["product_id"]: r for r in rows}.values())
        if rows:
            db().table("recommendations").insert(rows).execute()
        return {"rec_set_id": rs["id"], "count": len(rows)}
    return start_job(bg, "recommendations", uid, req.model_dump(), work)


@app.get("/users/{uid}/recommendations/{set_id}")
def get_recs(uid: str, set_id: str):
    one("recommendation_sets", id=set_id, user_id=uid)
    return db().table("recommendations").select("rank, reason, pairs_with, products(*)").eq("set_id", set_id).order("rank").execute().data


class ProductFeedback(BaseModel):
    liked: bool | None = None
    bought: bool = False


@app.post("/users/{uid}/products/{product_id}/feedback")
def product_feedback(uid: str, product_id: str, f: ProductFeedback):
    db().table("product_feedback").upsert({"user_id": uid, "product_id": product_id, **f.model_dump()},
                                          on_conflict="user_id,product_id").execute()
    if f.bought:   # add to wardrobe
        p = one("products", id=product_id)
        if p.get("image_url"):
            content = fetch_bytes(p["image_url"])
            img = store_image(uid, "wardrobe", content, "image/jpeg", p["image_url"])
            t = ai.tag_item(data_url(content))
            db().table("wardrobe_items").insert({"user_id": uid, "image_id": img["id"], "category": t.get("category"),
                "subtype": t.get("subtype"), "colors": t.get("colors") or [], "pattern": t.get("pattern"),
                "material": t.get("material"), "formality": t.get("formality_1to5"), "warmth": t.get("warmth_1to5"),
                "style_tags": t.get("style_tags") or [], "raw": t}).execute()
    return {"ok": True}


# ---------- pasted links ----------
class LinkIn(BaseModel):
    url: str


@app.post("/users/{uid}/links")
def check_link(uid: str, req: LinkIn, bg: BackgroundTasks):
    one("users", id=uid)

    def work():
        prods = upsert_products(run_actor(ECOM, {"detailsUrls": [{"url": req.url}], "maxProductResults": 1}))
        if not prods:
            raise RuntimeError("Could not scrape product from URL")
        p = prods[0]
        v = ai.link_verdict(p, latest_profile(uid), wardrobe_of(uid), p.get("image_url"))
        row = db().table("link_checks").insert({"user_id": uid, "product_id": p["id"], "url": req.url,
                                                "score": v.get("score_1to10"), "verdict": v}).execute().data[0]
        return {"link_check_id": row["id"], "product": {k: p.get(k) for k in ["id", "name", "price", "currency", "image_url"]}, **v}
    return start_job(bg, "link_check", uid, req.model_dump(), work)


@app.get("/users/{uid}/links")
def list_links(uid: str):
    return db().table("link_checks").select("*, products(name, price, currency, image_url, url)").eq("user_id", uid).order("created_at", desc=True).execute().data


# ---------- daily outfit ----------
class DailyIn(BaseModel):
    event: str = "casual day"
    city: str | None = None
    date: Date | None = None


@app.post("/users/{uid}/outfits/daily")
def daily(uid: str, req: DailyIn):
    user = one("users", id=uid)
    city = req.city or user.get("city")
    if not city:
        raise HTTPException(422, "city missing (set on user or request)")
    wx = weather(city, req.date.isoformat() if req.date else None)
    wd = wardrobe_of(uid)
    if not wd:
        raise HTTPException(409, "Wardrobe is empty")
    recent = [i for o in db().table("outfits").select("item_ids").eq("user_id", uid).order("created_at", desc=True).limit(3).execute().data
              for i in o["item_ids"]]
    o = ai.daily_outfit(wx, req.event, wd, user.get("color_profile"), recent)
    valid = {w["id"] for w in wd}
    row = {"user_id": uid, "date": (req.date or Date.today()).isoformat(), "event": req.event, "city": city, "weather": wx,
           "item_ids": [i for i in o.get("item_ids", []) if i in valid], "explanation": o.get("explanation"),
           "missing_item_tip": o.get("missing_item_tip")}
    saved = db().table("outfits").insert(row).execute().data[0]
    saved["items"] = with_image_urls([w for w in wd if w["id"] in saved["item_ids"]])
    return saved


@app.get("/users/{uid}/outfits")
def list_outfits(uid: str):
    return db().table("outfits").select("*").eq("user_id", uid).order("created_at", desc=True).execute().data


class OutfitFeedback(BaseModel):
    worn: bool | None = None
    rating: int | None = None
    comment: str | None = None


@app.post("/users/{uid}/outfits/{outfit_id}/feedback")
def outfit_feedback(uid: str, outfit_id: str, f: OutfitFeedback):
    return db().table("outfits").update({"feedback": f.model_dump(exclude_none=True)}).eq("id", outfit_id).eq("user_id", uid).execute().data[0]
