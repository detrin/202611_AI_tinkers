"""Generates examples/poc.ipynb. Run: uv run python examples/build_poc.py"""
import nbformat as nbf

cells = []
md = lambda s: cells.append(nbf.v4.new_markdown_cell(s))
code = lambda s: cells.append(nbf.v4.new_code_cell(s))

md("""# Wardrobe stylist PoC (end to end)
1. Wardrobe photos → vision model tags items
2. Pinterest (Apify) → reference looks for a few styles
3. LLM matches the wardrobe to a style, finds gaps, writes shop queries
4. Etsy via Apify e-commerce tool → product candidates → LLM picks + explains
5. Pasted product link → scrape → "does it fit you?"
6. Daily outfit: Open-Meteo weather + event → outfit from the wardrobe

Keys come from the macOS Keychain (`env.sh`). Every Apify call is cached in `cache/` so re-runs are instant.""")

code('''import os, json, re, base64, hashlib, subprocess, concurrent.futures as cf
from pathlib import Path
from datetime import timedelta
from decimal import Decimal
import requests
from openai import OpenAI
from apify_client import ApifyClient
from IPython.display import HTML, display

def keychain(name):
    return subprocess.run(["security", "find-generic-password", "-a", os.environ["USER"], "-s", name, "-w"],
                          capture_output=True, text=True).stdout.strip() or os.environ.get(name)

llm = OpenAI(base_url="https://api.featherless.ai/v1", api_key=keychain("FEATHERLESS_API_KEY"))
apify = ApifyClient(keychain("APIFY_TOKEN"))
VISION = "Qwen/Qwen3-VL-30B-A3B-Instruct"   # GLM-5.3-Flash ignores images on Featherless
TEXT = "zai-org/GLM-5.3-Flash"
CACHE = Path("cache"); CACHE.mkdir(exist_ok=True)
UA = {"User-Agent": "wardrobe-poc/0.1 (hackathon)"}''')

code('''def parse_json(s):
    s = re.sub(r"^```(json)?|```$", "", s.strip(), flags=re.M).strip()
    m = re.search(r"[\\[{].*[\\]}]", s, re.S)
    return json.loads(m.group(0) if m else s)

def ask(prompt, images=(), model=None, max_tokens=2000):
    content = [{"type": "text", "text": prompt}] + [{"type": "image_url", "image_url": {"url": u}} for u in images]
    r = llm.chat.completions.create(model=model or (VISION if images else TEXT), max_tokens=max_tokens,
                                    temperature=0.3, messages=[{"role": "user", "content": content}])
    return r.choices[0].message.content

def img_data_url(url):
    b = requests.get(url, headers=UA, timeout=30).content
    return "data:image/jpeg;base64," + base64.b64encode(b).decode()

def run_actor(actor, run_input, cap="1"):
    key = CACHE / (actor.replace("/", "_") + "_" + hashlib.md5(json.dumps(run_input, sort_keys=True).encode()).hexdigest()[:10] + ".json")
    if key.exists():
        return json.loads(key.read_text())
    run = apify.actor(actor).call(run_input=run_input, max_total_charge_usd=Decimal(cap),
                                  run_timeout=timedelta(minutes=6), logger=None)
    run = run if isinstance(run, dict) else run.model_dump(by_alias=True)
    items = apify.dataset(run["defaultDatasetId"]).list_items().items
    key.write_text(json.dumps(items, default=str))
    return items

def pmap(fn, xs, n=4):
    with cf.ThreadPoolExecutor(n) as ex:
        return list(ex.map(fn, xs))

def gallery(rows):  # rows: (image_url, caption)
    display(HTML("<div style='display:flex;flex-wrap:wrap;gap:8px'>" + "".join(
        f"<div style='width:160px;font-size:11px'><img src='{u}' style='width:160px;height:200px;object-fit:cover'><br>{c}</div>"
        for u, c in rows) + "</div>"))''')

md("## 1. Wardrobe photos → tagged items\nStand-in for user uploads: a few garment photos from Wikimedia Commons.")
code('''WARDROBE_QUERIES = ["denim jacket", "white sneakers", "black turtleneck sweater", "chino trousers", "wool overcoat", "striped shirt"]

def commons_image(q):
    r = requests.get("https://commons.wikimedia.org/w/api.php", headers=UA, params={
        "action": "query", "generator": "search", "gsrsearch": f"{q} filetype:bitmap", "gsrnamespace": 6,
        "gsrlimit": 1, "prop": "imageinfo", "iiprop": "url", "iiurlwidth": 512, "format": "json"}).json()
    return next(iter(r["query"]["pages"].values()))["imageinfo"][0]["thumburl"]

wardrobe_urls = pmap(commons_image, WARDROBE_QUERIES)

TAG_PROMPT = """Identify the single main clothing item or shoe in this photo. Return ONLY JSON:
{"category":"top|bottom|outerwear|shoes|dress|accessory","subtype":"","colors":[],"pattern":"","material":"",
 "formality_1to5":0,"warmth_1to5":0,"style_tags":[]}"""

def tag(url):
    try:
        d = parse_json(ask(TAG_PROMPT, [img_data_url(url)])); d["image"] = url; return d
    except Exception as e:
        return {"error": repr(e), "image": url}

wardrobe = [w for w in pmap(tag, wardrobe_urls) if "error" not in w]
gallery([(w["image"], f"<b>{w['subtype']}</b><br>{', '.join(w['colors'])} · formality {w['formality_1to5']} · warmth {w['warmth_1to5']}") for w in wardrobe])''')

md("## 2. Style library from Pinterest (Apify `epctex/pinterest-scraper`)")
code('''STYLES = ["scandinavian minimalist outfit", "streetwear outfit", "old money outfit", "smart casual men outfit"]

def pins(q):
    items = run_actor("epctex/pinterest-scraper", {"search": q, "maxItems": 6, "getDetails": False, "endPage": 1})
    return [{"style": q, "title": i.get("grid_title") or i.get("title") or "", "image": i["images"]["474x"]["url"]}
            for i in items if i.get("images")][:4]

style_pins = dict(zip(STYLES, pmap(pins, STYLES)))
for s, ps in style_pins.items():
    print(s); gallery([(p["image"], p["title"][:60]) for p in ps])''')

code('''STYLE_PROMPT = """These are Pinterest reference images for the style "{s}".
Summarise the style in JSON: {{"style":"{s}","key_items":[],"palette":[],"materials":[],"formality_1to5":0,"vibe":""}}"""
def summarise(s):
    return parse_json(ask(STYLE_PROMPT.format(s=s), [img_data_url(p["image"]) for p in style_pins[s][:3]]))
style_library = pmap(summarise, STYLES)
style_library''')

md("## 3. Match wardrobe → style profile, gaps, shopping queries")
code('''profile = parse_json(ask(f"""You are a personal stylist.
WARDROBE: {json.dumps([{k: v for k, v in w.items() if k != 'image'} for w in wardrobe])}
STYLE LIBRARY: {json.dumps(style_library)}
Return ONLY JSON:
{{"style_mix":[{{"style":"","percent":0,"why":""}}],
  "taste_summary":"",
  "wardrobe_gaps":[{{"item":"","why":""}}],
  "etsy_queries":["3 short product search queries that fill the gaps and match the style"]}}"""))
profile''')

md("## 4. Shop: Etsy via Apify `apify/e-commerce-scraping-tool` → LLM ranking")
code('''def shop(q):
    items = run_actor("apify/e-commerce-scraping-tool",
                      {"keyword": q, "marketplaces": ["www.etsy.com"], "maxProductResults": 5})
    out = []
    for i in items:
        o = (i.get("offers") or [{}]); o = o[0] if isinstance(o, list) and o else (o if isinstance(o, dict) else {})
        out.append({"query": q, "name": i.get("name"), "url": i.get("url"), "image": i.get("image"),
                    "price": o.get("price"), "currency": o.get("priceCurrency")})
    return out

products = [p for ps in pmap(shop, profile["etsy_queries"][:3], n=3) for p in ps if p["image"]]
print(len(products), "candidates")

recs = parse_json(ask(f"""User style: {json.dumps(profile['style_mix'])}. Taste: {profile['taste_summary']}
Wardrobe: {json.dumps([w['subtype'] + ' (' + ', '.join(w['colors']) + ')' for w in wardrobe])}
Candidates: {json.dumps([{'id': i, 'name': p['name'], 'price': p['price'], 'currency': p['currency']} for i, p in enumerate(products)])}
Pick the 5 best. Return ONLY JSON list: [{{"id":0,"reason":"one sentence: why it fits + which wardrobe items it pairs with"}}]"""))
gallery([(products[r["id"]]["image"], f"<a href='{products[r['id']]['url']}' target=_blank>{(products[r['id']]['name'] or '')[:50]}</a><br>"
          f"{products[r['id']]['price']} {products[r['id']]['currency'] or ''}<br><i>{r['reason']}</i>") for r in recs])''')

md("## 5. User pastes a product link → scrape → verdict")
code('''PASTED_URL = products[-1]["url"]   # replace with any product URL the user pastes
item = run_actor("apify/e-commerce-scraping-tool", {"detailsUrls": [{"url": PASTED_URL}], "maxProductResults": 1})[0]
verdict = parse_json(ask(f"""Product: {item.get('name')} — {str(item.get('description'))[:600]}
User style: {json.dumps(profile['style_mix'])}. Wardrobe: {json.dumps([w['subtype'] for w in wardrobe])}
Look at the product photo. Return ONLY JSON: {{"fits_style_score_1to10":0,"pairs_with":[],"verdict":""}}""",
    [img_data_url(item["image"])]))
gallery([(item["image"], item.get("name", "")[:60])]); verdict''')

md("## 6. Daily outfit: Open-Meteo weather + event")
code('''CITY, EVENT = "Prague", "office day with an after-work dinner"
geo = requests.get("https://geocoding-api.open-meteo.com/v1/search", params={"name": CITY, "count": 1}).json()["results"][0]
wx = requests.get("https://api.open-meteo.com/v1/forecast", params={
    "latitude": geo["latitude"], "longitude": geo["longitude"], "forecast_days": 1, "timezone": "auto",
    "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,wind_speed_10m_max"}).json()["daily"]
weather = {k: v[0] for k, v in wx.items()}
print(weather)

outfit = parse_json(ask(f"""Weather in {CITY} today: {json.dumps(weather)}. Event: {EVENT}.
Wardrobe (use ids): {json.dumps([{'id': i, **{k: v for k, v in w.items() if k != 'image'}} for i, w in enumerate(wardrobe)])}
Build the best outfit ONLY from these items. Return ONLY JSON: {{"item_ids":[],"explanation":"","missing_item_tip":""}}"""))
gallery([(wardrobe[i]["image"], wardrobe[i]["subtype"]) for i in outfit["item_ids"]]); outfit''')

nb = nbf.v4.new_notebook(); nb.cells = cells
nb.metadata["kernelspec"] = {"name": "python3", "display_name": "Python 3", "language": "python"}
from pathlib import Path
nbf.write(nb, Path(__file__).with_name("poc.ipynb"))
print("wrote poc.ipynb")
