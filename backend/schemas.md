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

## Architecture (ports & adapters)

```
backend/app/
  config.py        Settings + secret loading (env → Keychain)
  errors.py        NotFound / Conflict / Invalid → 404 / 409 / 422
  domain.py        value objects: ImageInput, Pin, Product, SocialPost
  ports.py         Protocols: Database, ChatModel, ImageStore, ImageFetcher, PinSource, ProductSource,
                   SocialSource, WeatherProvider, Executor
  adapters/        concrete I/O: supabase.py, featherless.py, apify.py (Pinterest, e-commerce, Instagram),
                   html.py (JSON-LD/OpenGraph product pages + Apify fallback), web.py (HTTP fetch + Open-Meteo), executors.py
  services/        business logic, depends only on ports
    stylist.py       every prompt + JSON parsing (the only LLM-aware module)
    images.py        upload/URL → Storage + `images` row, signed URLs
    users.py         users + selfie colour analysis
    wardrobe.py      single garments, owned or wanted
    inspirations.py  whole looks (upload / URL / pin)
    imports.py       URL imports: product page → item, Instagram → style profile (+ items)
    styles.py        Pinterest style library
    preferences.py   swipe deck + signals
    profiles.py      style profile
    catalog.py       product scraping + deduplicated persistence
    recommendations.py, feedback.py, links.py, outfits.py, jobs.py
  container.py     composition root: build_services(ports…) and build_container() (real adapters)
  api/             FastAPI routers (thin), request schemas, DI via app.state.container
  main.py          create_app(container_factory)
backend/tests/     unit tests over in-memory fakes (no network)
```

Rules:
- Services never import FastAPI or an SDK.
- Adapters hold no business logic.
- Routers only translate HTTP to and from service calls.

To swap a provider (for example another LLM or a different scraper), write a new adapter for the port and wire it in `container.py`.

### Tests
```bash
uv run pytest          # 60 unit tests, ~0.5 s, all fakes (tests/fakes.py)
```

`create_app(lambda: build_services(...fakes...))` gives a fully working API in memory, which is useful in notebooks too.

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
| `wardrobe_items` | id, user_id, image_id, **status (owned/wanted)**, **product_id**, category, subtype, colors[], pattern, material, formality 1-5, warmth 1-5, style_tags[], raw jsonb | single garments, tagged by the vision model. `wanted` = wishlist, optionally linked to a shop product |
| `inspirations` | id, user_id, image_id, pin_id, source_url, style_tags[], palette[], formality, vibe, pieces jsonb, raw | whole looks (upload, URL or saved pin), tagged as a look; unique (user_id, pin_id) |
| `styles` | id, name (unique), query, summary jsonb | shared style library |
| `style_pins` | id, style_id, pin_url (unique), image_url, title | Pinterest reference pins |
| `swipes` | (user_id, pin_id) PK, liked | preference signal |
| `profiles` | id, user_id, style_mix jsonb, taste_summary, gaps jsonb, queries[] | append-only; the latest row is the current profile |
| `products` | id, url (unique), name, description, price, currency, image_url, marketplace, query, raw | scraped products; also acts as the cache |
| `recommendation_sets` | id, user_id, profile_id, params | one per shopping run |
| `recommendations` | (set_id, product_id) PK, rank, reason, pairs_with uuid[] | `pairs_with` holds wardrobe item ids |
| `product_feedback` | (user_id, product_id) PK, liked, bought | `liked` creates a wanted item; `bought` flips it to owned |
| `link_checks` | id, user_id, product_id, url, score 1-10, verdict jsonb | links the user pasted |
| `outfits` | id, user_id, date, event, city, weather jsonb, item_ids uuid[], explanation, missing_item_tip, feedback jsonb | daily outfits |
| `taste_profiles` | id, user_id, model, profile jsonb, facts jsonb, evidence_counts jsonb | Opus-built taste profile; append-only, latest row wins |
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
| POST | `/users/{uid}/wardrobe` | multipart: repeated `files` and/or repeated form `image_urls`, form `status=owned\|wanted` (default owned) | list of tagged items with signed `image_url` |
| GET | `/users/{uid}/wardrobe` | `?status=owned\|wanted\|all` (default owned) `&category=&color=` | items with signed `image_url` |
| GET | `/users/{uid}/wardrobe/{item_id}` | | item |
| PATCH | `/users/{uid}/wardrobe/{item_id}` | `{status?, category?, subtype?, colors?, pattern?, material?, fit?, description?, formality?, warmth?, style_tags?, availability?}` (`availability`: available\|laundry\|lent\|stored) | item (to fix wrong tags) |
| POST | `/users/{uid}/wardrobe/{item_id}/buy` | | item with `status=owned` (no re-upload or re-tagging) |
| DELETE | `/users/{uid}/wardrobe/{item_id}` | | `{deleted}` |

Items also carry `fit`, `availability` and `source_type` (upload\|product_url\|instagram\|pin) + `source_url`. Every item also gets a free-text `description` (1-2 sentences of visual detail from the vision model). It is included in every text prompt, including the Opus taste profile, which never sees images.

### Imports from a URL (retailer page or Instagram)
| Method | Path | Body | Returns |
|---|---|---|---|
| POST | `/users/{uid}/imports` | `{url, kind="auto"\|"product"\|"instagram", max_posts=12, import_items=false}` | **job**, see below. `url` may be a product page, a direct image URL, an Instagram profile/post/reel URL or a bare `@handle` |
| GET | `/users/{uid}/imports` | | Instagram imports `{url, posts[{post_url, image_id, analysis}], style_profile, item_ids}`, newest first |

- **Product page / image URL** → owned wardrobe item. The page is parsed cheaply first (JSON-LD `Product`, then OpenGraph); shops that block plain HTTP fall back to the Apify e-commerce scraper. The vision tagger also gets the page text (name, description, brand, material), so material and fit come out better than from the photo alone. Result `{kind:"product", item, product}`. (`POST /links` and product feedback use the same scraper.)
- **Instagram** (public profiles only) → each post's first image is copied to Storage (IG CDN links expire) and analysed: `{has_outfit, items[], style_tags, colors, setting, vibe}`. The outfits are then aggregated into `style_profile {style_tags, preferred_colors, preferred_fit, avoid_tags, typical_formality_1to5, summary, confidence_0to1}`, saved on the user and used by `profile/compute`. With `import_items=true` the detected garments become owned items (`source_type=instagram`, all sharing the post image). Result `{kind:"instagram", import_id, posts_analysed, outfits, style_profile, items_added}`.

### Inspirations (whole looks, not garments)
| Method | Path | Body | Returns |
|---|---|---|---|
| POST | `/users/{uid}/inspirations` | multipart: repeated `files` and/or repeated form `image_urls` | looks `{style_tags, palette, formality, vibe, pieces[{category, subtype, colors}], image_url}` |
| POST | `/users/{uid}/inspirations/from-pin` | `{pin_id}` | promotes a swipe-deck pin to a look and records a like; idempotent |
| GET | `/users/{uid}/inspirations` | | looks, newest first |
| GET/DELETE | `/users/{uid}/inspirations/{id}` | | look / `{deleted}` |

How each feature uses them:
- **Daily outfit and recommendation `pairs_with`:** owned items only.
- **Profile:** owned + wishlist (so it doesn't re-suggest them) + inspiration looks (the strongest taste signal).
- **Link check:** compares against owned and wishlist items and reports `on_wishlist_as`.

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
| POST | `/users/{uid}/products/{product_id}/feedback` | `{liked?, bought=false}` | `liked` creates a wanted item linked to the product; `bought` flips it to owned (or creates an owned one). Returns `{item_id, status}` |

### Pasted links
| Method | Path | Body | Returns |
|---|---|---|---|
| POST | `/users/{uid}/links` | `{url}` | **job**: scrape the product page, then a verdict `{score_1to10, pairs_with[], verdict, redundant_with[]}` |
| GET | `/users/{uid}/links` | | history with product info |

### Taste profile (Claude Opus via `claude -p`)
| Method | Path | Returns |
|---|---|---|
| POST | `/users/{uid}/taste-profile` | **job** (about 10–60 s). Gathers all evidence and sends it to Opus with a JSON schema. 409 if there are fewer than 3 pieces of evidence |
| GET | `/users/{uid}/taste-profile` | latest `{model, profile, facts, evidence_counts}` (404 if none) |
| GET | `/users/{uid}/taste-profile/evidence` | exactly what would be sent to the model, plus `counts` (cheap, no LLM) |

**Evidence pack:**
- `wardrobe_facts`: deterministic statistics over owned items, such as top categories, primary colours, materials, fits, style tags and a formality histogram
- owned items, wishlist, inspiration looks, liked/disliked swipes, liked products, rated outfits
- the Instagram style profile and the colour profile

The prompt weights the sources:
- **High:** outfit feedback, Instagram, inspirations
- **Medium:** owned items, wishlist, liked products
- **Low:** swipes

It also keeps **current** style (what they own and wear) apart from **aspirational** style (what they save and like).

`profile` fields:
- `headline`
- `current_style` / `aspirational_style`: `{summary, style_mix[{style, percent, evidence}], palette, silhouettes, key_pieces, formality_range}`
- `gap {summary, moves[{action, why}]}`
- `colors {wear_more, avoid}`
- `avoid`, `shop_queries`, `confidence` (0–1), `missing_evidence`

**Runtime:** the `claude` CLI must be installed and logged in on the backend host. `ANTHROPIC_API_KEY` is removed from the child process environment so your Claude login is used. Override the model with `TASTE_MODEL` (default `claude-opus-5-5`).

### Daily outfit
| Method | Path | Body | Returns |
|---|---|---|---|
| POST | `/users/{uid}/outfits/daily` | `{event="casual day", city?, date?}` (city defaults to the user's) | outfit `{item_ids, explanation, missing_item_tip, weather, items[] with image_url}` |
| POST | `/users/{uid}/outfits/today` | `{date?, note?}` plus server bearer token | outfit, `context`, `steps`, `from_fallback` |
| GET | `/users/{uid}/outfits` | | history |
| POST | `/users/{uid}/outfits/{outfit_id}/feedback` | `{worn?, rating?, comment?}` | outfit |

The Today endpoint uses an internal MCP session to read the calendar, hourly weather, owned and available
clothes, recent outfits, and the user's usual transport. The backend gathers these inputs in parallel.
Featherless picks the outfit and can request one venue lookup through Apify MCP when enabled.
The fallback uses the existing stylist with the same availability rules. The endpoint saves the outfit
in the existing table and returns event context and tool summaries with the response. A forecast or
calendar failure appears as an unavailable tool step. If both pickers fail, the endpoint returns
`503`. If no owned clothes are available, it returns `409`.

| Environment variable | Today endpoint configuration |
|---|---|
| `TODAY_API_TOKEN` | Enables the endpoint. Send it as `Authorization: Bearer <token>` from a trusted server or local test client. Keep it on the server for a browser integration. |
| `CALENDAR_ICS_URL` | Secret iCal URL for a dedicated demo calendar. |
| `CALENDAR_DEMO_USER_ID` | User ID allowed to read the configured demo calendar. |
| `OUTFIT_TIMEZONE` | Local day and forecast time zone, default `Europe/Prague`. |
| `APIFY_VENUE_LOOKUP` | Set to `1` to allow a capped lookup for the public venue in the demo calendar. Default is off. |

Set the demo user's city before calling the endpoint. Set `fit_prefs.commute_mode` to `metro`, `bike`,
`walk`, or `car` to include the usual transport. `context.events` contains local event timestamps and
the matching forecast when available. `context.weather.rain_probability` is a fraction between 0
and 1. Use `note` to give an occasion when the calendar is empty. To replace a garment in the laundry,
PATCH its `availability` to `laundry` through the wardrobe endpoint and call Today again.

For a live check, call `/health`, then `POST /users/{uid}/outfits/today` with `{}` and the bearer token.
Confirm that the response contains the demo event, its forecast, and signed image URLs for owned,
available items. Repeat after marking one item as laundry.

## External services

The taste profile uses Claude Opus 5.5 through `claude -p --json-schema` (`adapters/claude_cli.py`, port `StructuredModel`).


| Purpose | Service | Notes |
|---|---|---|
| Item tagging, selfie colour analysis, style summary, link verdict | Featherless `Qwen/Qwen3-VL-30B-A3B-Instruct` | images are sent as base64 or URLs |
| Profile, ranking, outfit | Featherless `zai-org/GLM-5.3-Flash` | JSON-only prompts, parsed leniently |
| Pinterest | Apify `epctex/pinterest-scraper` | ~$0.0015 per pin |
| Instagram posts | Apify `apify/instagram-scraper` | `directUrls` + `resultsType=posts`; public profiles only |
| Products (search and links) | JSON-LD/OpenGraph HTML parse, then Apify `apify/e-commerce-scraping-tool` | `keyword`+`marketplaces` (Etsy works well; M&S didn't), or `detailsUrls` for any shop |
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
