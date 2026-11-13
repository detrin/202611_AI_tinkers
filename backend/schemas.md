# Backend spec: Wardrobe stylist API

This is a FastAPI service backed by Supabase (Postgres and Storage), Featherless for the LLMs and Apify for scraping. The Python notebook is the client for now, with no web UI. Interactive docs are at `http://localhost:8000/docs` while the server runs.

## Run

```bash
uv sync
uv run uvicorn backend.app.main:app --reload --port 8000
```

Secrets are read from environment variables first, then from the macOS Keychain (account `$USER`):

| Name | What |
|---|---|
| `SUPABASE_URL` | `https://yyzesrwijgyxyjbawvib.supabase.co` |
| `SUPABASE_SERVICE_KEY` | service-role key (backend only, never ship to a browser) |
| `FEATHERLESS_API_KEY` | LLM and vision models |
| `APIFY_TOKEN` | Pinterest and e-commerce Actors |
| `SUPABASE_ACCESS_TOKEN` | Management API (migrations), not used at runtime |
| `SUPABASE_DB_PASSWORD` | Postgres password, not used at runtime |

You can override the models with `VISION_MODEL` (default `Qwen/Qwen3-VL-30B-A3B-Instruct`) and `TEXT_MODEL` (default `zai-org/GLM-5.3-Flash`). Don't use GLM-5.3-Flash for images: on Featherless it ignores them.

## Supabase

- **Project:** `wardrobe-stylist`, ref `yyzesrwijgyxyjbawvib`, region `eu-central-1`, org "AI Tinkers 202611" (free plan).
- **Schema:** in `supabase/migrations/`. Apply with `supabase db push` (CLI), or POST the SQL to the Management API `/v1/projects/{ref}/database/query`.
- **Access:** RLS (row-level security) is on for every table with no policies. Public/anon access is blocked; the service role used by the backend bypasses RLS.
- **Images:** go in the private Storage bucket `images`, at `{user_id|shared}/{kind}/{uuid}.{ext}`. The DB only stores the path. Image URLs returned by the API are signed and expire after 1 hour.

## Data model

| Table | Key columns | Notes |
|---|---|---|
| `users` | id, name, city, budget, currency, fit_prefs jsonb, sizes jsonb, color_profile jsonb | `color_profile` comes from the selfie analysis |
| `images` | id, user_id, bucket_path, source_url, kind (wardrobe/selfie/pin/product) | Storage index |
| `wardrobe_items` | id, user_id, image_id, category, subtype, colors[], pattern, material, formality 1-5, warmth 1-5, style_tags[], raw jsonb | tagged by the vision model |
| `styles` | id, name (unique), query, summary jsonb | shared style library |
| `style_pins` | id, style_id, pin_url (unique), image_url, title | Pinterest reference pins |
| `swipes` | (user_id, pin_id) PK, liked | preference signal |
| `profiles` | id, user_id, style_mix jsonb, taste_summary, gaps jsonb, queries[] | append-only; the latest row is the current profile |
| `products` | id, url (unique), name, description, price, currency, image_url, marketplace, query, raw | scraped products; also acts as the cache |
| `recommendation_sets` | id, user_id, profile_id, params | one per shopping run |
| `recommendations` | (set_id, product_id) PK, rank, reason, pairs_with uuid[] | `pairs_with` holds wardrobe item ids |
| `product_feedback` | (user_id, product_id) PK, liked, bought | `bought=true` adds the item to the wardrobe |
| `link_checks` | id, user_id, product_id, url, score 1-10, verdict jsonb | links the user pasted |
| `outfits` | id, user_id, date, event, city, weather jsonb, item_ids uuid[], explanation, missing_item_tip, feedback jsonb | daily outfits |
| `jobs` | id, kind, user_id, status (queued/running/done/failed), input, result, error | async work |

## Async jobs

Anything that calls Apify takes 1–3 minutes. Those endpoints return `{"job_id", "status": "queued"}` straight away. Poll `GET /jobs/{job_id}` until `status` is `done` (the output is in `result`) or `failed` (the reason is in `error`). Jobs run in-process as FastAPI background tasks, so restarting the server kills any running jobs.

Job endpoints:
- `POST /styles/refresh`
- `POST /users/{uid}/recommendations`
- `POST /users/{uid}/links`

## Endpoints

### Utility
| Method | Path | Body / params | Returns |
|---|---|---|---|
| GET | `/health` | | `{ok: true}` |
| GET | `/jobs/{job_id}` | | job row |
| GET | `/weather` | `?city=Prague&date=YYYY-MM-DD` | Open-Meteo daily forecast: temp max/min, rain %, wind, weather_code |

### Users
| Method | Path | Body | Returns |
|---|---|---|---|
| POST | `/users` | `{name, city?, budget?, currency="EUR", fit_prefs={}, sizes={}}` | user |
| GET | `/users/{uid}` | | user |
| PATCH | `/users/{uid}` | any user field | user |
| POST | `/users/{uid}/selfie` | multipart `file` **or** form `image_url` | colour profile `{season, undertone, contrast, best_colors[], avoid_colors[], notes}`, also saved on the user |

### Wardrobe
| Method | Path | Body / params | Returns |
|---|---|---|---|
| POST | `/users/{uid}/wardrobe` | multipart: repeated `files` and/or repeated form `image_urls` | list of tagged items with signed `image_url` |
| GET | `/users/{uid}/wardrobe` | `?category=&color=` | items with signed `image_url` |
| GET | `/users/{uid}/wardrobe/{item_id}` | | item |
| PATCH | `/users/{uid}/wardrobe/{item_id}` | `{category?, subtype?, colors?, pattern?, material?, formality?, warmth?, style_tags?}` | item (to fix wrong tags) |
| DELETE | `/users/{uid}/wardrobe/{item_id}` | | `{deleted}` |

### Style library (shared across users)
| Method | Path | Body | Returns |
|---|---|---|---|
| GET | `/styles` | | styles with `summary {key_items, palette, materials, formality_1to5, vibe}` |
| GET | `/styles/{style_id}` | | style and its `pins[]` |
| POST | `/styles/refresh` | `{queries: ["old money outfit", ...], pins_per_style=12}` | **job**: Pinterest scrape, then a vision-model summary per style |

### Preferences (swipe game)
| Method | Path | Body / params | Returns |
|---|---|---|---|
| GET | `/users/{uid}/swipe-deck` | `?n=20` | unseen pins, rotating through the styles in turn |
| POST | `/users/{uid}/swipes` | `[{pin_id, liked}]` | `{saved}` |

### Profile
| Method | Path | Returns |
|---|---|---|
| POST | `/users/{uid}/profile/compute` | new profile `{style_mix[{style, percent, why}], taste_summary, gaps[{item, why}], queries[]}`. Built from the wardrobe, swipes, pasted links, colour profile and style library |
| GET | `/users/{uid}/profile` | latest profile (404 if none) |

### Shopping
| Method | Path | Body | Returns |
|---|---|---|---|
| POST | `/users/{uid}/recommendations` | `{n=5, per_query=6, marketplaces=["www.etsy.com"], queries?}` | **job**: e-commerce scrape per profile query, then LLM ranking. `result = {rec_set_id, count}` |
| GET | `/users/{uid}/recommendations/{set_id}` | | `[{rank, reason, pairs_with[], products{...}}]` |
| POST | `/users/{uid}/products/{product_id}/feedback` | `{liked?, bought=false}` | `bought=true` tags the product image and adds it to the wardrobe |

### Pasted links
| Method | Path | Body | Returns |
|---|---|---|---|
| POST | `/users/{uid}/links` | `{url}` | **job**: scrape the product page, then a verdict `{score_1to10, pairs_with[], verdict, redundant_with[]}` |
| GET | `/users/{uid}/links` | | history with product info |

### Daily outfit
| Method | Path | Body | Returns |
|---|---|---|---|
| POST | `/users/{uid}/outfits/daily` | `{event="casual day", city?, date?}` (city defaults to the user's) | outfit `{item_ids, explanation, missing_item_tip, weather, items[] with image_url}` |
| GET | `/users/{uid}/outfits` | | history |
| POST | `/users/{uid}/outfits/{outfit_id}/feedback` | `{worn?, rating?, comment?}` | outfit |

## External services

| Purpose | Service | Notes |
|---|---|---|
| Item tagging, selfie colour analysis, style summary, link verdict | Featherless `Qwen/Qwen3-VL-30B-A3B-Instruct` | images are sent as base64 or URLs |
| Profile, ranking, outfit | Featherless `zai-org/GLM-5.3-Flash` | JSON-only prompts, parsed leniently |
| Pinterest | Apify `epctex/pinterest-scraper` | ~$0.0015 per pin |
| Products (search and links) | Apify `apify/e-commerce-scraping-tool` | `keyword`+`marketplaces` (Etsy works well; M&S didn't), or `detailsUrls` for any shop |
| Weather | Open-Meteo | free, no key |

## Notebook usage (sketch)

```python
import requests, time
API = "http://localhost:8000"
u = requests.post(f"{API}/users", json={"name": "Dan", "city": "Prague", "budget": 150}).json()
uid = u["id"]
requests.post(f"{API}/users/{uid}/wardrobe", data={"image_urls": [url1, url2]})
requests.post(f"{API}/users/{uid}/outfits/daily", json={"event": "office"}).json()

def wait(job):
    while (j := requests.get(f"{API}/jobs/{job['job_id']}").json())["status"] in ("queued", "running"):
        time.sleep(5)
    return j

wait(requests.post(f"{API}/styles/refresh", json={"queries": ["old money outfit", "streetwear outfit"]}).json())
requests.post(f"{API}/users/{uid}/profile/compute").json()
rec = wait(requests.post(f"{API}/users/{uid}/recommendations", json={}).json())
requests.get(f"{API}/users/{uid}/recommendations/{rec['result']['rec_set_id']}").json()
```

## Known limits and next steps
- No auth, because the `user_id` is in the path. Add Supabase Auth before any public deploy.
- Jobs are in-process and get lost on restart. Move them to a queue or a Supabase Edge Function if needed.
- No image embeddings yet, so style matching is done purely by the LLM. A next step is Marqo-FashionSigLIP embeddings stored in pgvector.
- Optional: connect the GitHub repo in the Supabase dashboard so migrations deploy automatically from `main`.
