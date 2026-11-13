# Wardrobe stylist (AI Tinkers hackathon, Nov 2026)

Upload photos of what you own, what you want and looks you love. The app works out your taste, then:
- suggests what to wear today (weather + event, owned items only)
- suggests what to buy next (real shop links that fill the gap between how you dress and how you want to dress)

| Part | Where |
|---|---|
| REST API (FastAPI, ports & adapters) | `backend/app/`, spec: [`backend/schemas.md`](backend/schemas.md) |
| Database + image storage | Supabase project `wardrobe-stylist`, migrations in `supabase/migrations/` |
| Vision tagging, cheap reasoning | OpenRouter: `gemini-3.1-flash-lite` for images, `gpt-oss-120b` on Groq for text (`LLM_PROVIDER=featherless` switches back) |
| Taste profile | Claude Opus 5.5 via `claude -p` |
| Scraping (Pinterest, shops, Instagram) | Apify |
| End-to-end PoC notebook | `examples/` |

## Run the backend

```bash
uv sync
uv run uvicorn backend.app.main:app --reload --port 8000   # Swagger UI: http://localhost:8000/docs
uv run pytest                                               # unit tests, no network
```

Secrets are read from env vars first, then the macOS Keychain:
- `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `FEATHERLESS_API_KEY`, `APIFY_TOKEN`
- the taste profile also needs the `claude` CLI, installed and logged in

## Public URL

The API is live at **https://goodenough.hermandaniel.com/api**. Swagger UI: https://goodenough.hermandaniel.com/api/docs

```bash
curl https://goodenough.hermandaniel.com/api/health   # {"ok":true}
API=https://goodenough.hermandaniel.com/api          # use instead of http://localhost:8000 in the examples below
```

How it is wired:
- A Cloudflare Tunnel (`goodenough`) runs on Daniel's Mac and forwards `/api/...` to `127.0.0.1:8000`. The tunnel can't rewrite paths, so the server runs `backend.app.public:app`. That entrypoint serves the same app under `/api` (and still under `/` for local use).
- Everything outside `/api` returns 404 for now. The site will take over `/` later, as a second tunnel rule (or a separate host), and the frontend then calls `/api` on the same origin, so no CORS setup is needed.
- It is only up while that Mac is awake. It runs on the Mac because it needs the Keychain secrets and the `claude` login.
- There is no authentication yet, so don't post the URL publicly. Anyone with it can create users and start paid scraping and LLM jobs.

Operating it (on the Mac):
```bash
launchctl kickstart -k gui/$(id -u)/com.hermandaniel.goodenough-api      # restart the API, e.g. after git pull
launchctl kickstart -k gui/$(id -u)/com.hermandaniel.goodenough-tunnel   # restart the tunnel
tail -f ~/Library/Logs/goodenough-api.log ~/Library/Logs/goodenough-tunnel.log
# config: ~/Library/LaunchAgents/com.hermandaniel.goodenough-{api,tunnel}.plist, ~/.cloudflared/goodenough.yml
```

To run the same entrypoint locally: `uv run uvicorn backend.app.public:app --port 8000` (then both `/api/health` and `/health` work).

## Demo user (for the live demo)

A user whose wardrobe is **69 real photos of owned clothes** (18 jackets, 17 pants, 19 shirts, 15 pairs of shoes), every one tagged by Qwen3-VL and given an Opus taste profile:

| | |
|---|---|
| `user_id` | `8b63ae0d-35e8-4cc7-8896-f1785c47d54c` (also in `backend/scripts/demo_user.json`) |
| name | Demo User, Prague, budget 250 EUR, `fit_prefs.audience = menswear` |
| taste profile | "An Ivy-leaning dresser with a strong workwear/utility streak and a black streetwear layer". Current: Ivy 32%, Workwear 22%, Streetwear 18%. Aspiration: Ivy 45%, Workwear 30%, Minimalism 25% |

```bash
curl $API/users/demo-user            # the latest "Demo User": use its id in the UI
```

To re-create it from a folder of photos (`jackets-01.jpg`, `pants-03.jpg`, …; the file name is a category hint). Photos are downscaled to 1024 px, and imports are idempotent per file. It takes about 5 min:
```bash
uv run python -m backend.scripts.seed_demo_user --dir ~/Downloads/Demo-whatIown-photos --taste
```

## Test user (for UI work and manual testing)

A seeded user with a real, already-tagged wardrobe lives in the shared Supabase project:

| | |
|---|---|
| `user_id` | `24272756-ee74-40ac-81a8-2669e9a7bc69` |
| name | Test User (seed), Prague, budget 200 EUR, sizes M / 43, `fit_prefs.audience = menswear` |
| owned items (8) | white dress shirt, beige chinos, white sneakers, light denim jacket, black Chelsea boots, grey sweater, navy/white striped long-sleeve tee, dark jeans |
| wanted (2) | brown penny loafers, camel cashmere (the tagger says "sweater"; it's a scarf photo) |
| inspiration looks (4) | old money, quiet luxury, dark academia and Scandinavian minimalist menswear looks |
| taste profile | Opus 5.5, confidence 0.55. Current: minimalism, normcore, Parisian, business casual. Aspiration: preppy, old money, minimalism in earth tones |
| style recommendations | Workwear (owns 6 of 10 key pieces), Black Ivy, Scandinavian, Eclectic Grandpa, E-Boy (rising), … |

You don't need anyone to send you the ID. Ask the API for it, so UIs can default to it:
```bash
curl $API/users/test-user          # the latest seeded "Test User (seed)", with its id
curl "$API/users?name=seed"        # list users (newest first, ?name= filters by substring)
```
The ID is also in `backend/scripts/test_user.json` in git. The photos are the first Pinterest pin for each search (Apify `automation-lab/pinterest-scraper`), tagged by Qwen3-VL.

To make a fresh one (new user every run, about 2–4 min):
```bash
uv run python -m backend.scripts.seed_test_user           # wardrobe, wishlist and inspirations
uv run python -m backend.scripts.seed_test_user --taste   # ...and build the taste profile with Opus
```

### Playground (Streamlit debug UI)

Click through every endpoint as the test user: wardrobe and inspiration grids, daily outfit, taste profile, swipe deck, style library and trends, shopping recommendations, link checks, a raw-request console (any method or path, `{uid}` gets substituted, jobs are polled) and a log of every call.

```bash
uv run uvicorn backend.app.main:app --reload --port 8000        # backend first
uv run --group playground streamlit run backend/playground/app.py
```

The sidebar picks the API (localhost or the public tunnel) and the `user_id`. It defaults to the test user from `backend/scripts/test_user.json`. Delete buttons stay disabled until you turn on **Allow deletes**. For destructive experiments, create a scratch user on the User page.

### Calling the API as the test user

```bash
API=http://localhost:8000
UID=24272756-ee74-40ac-81a8-2669e9a7bc69

curl $API/users/$UID                                   # profile basics
curl "$API/users/$UID/wardrobe"                        # owned items (signed image_url valid 1 h)
curl "$API/users/$UID/wardrobe?status=wanted"          # wishlist   (status=all for both)
curl $API/users/$UID/inspirations                      # saved looks
curl $API/users/$UID/taste-profile                     # latest Opus taste profile
curl $API/users/$UID/taste-profile/evidence            # what the model sees (no LLM call)
curl "$API/users/$UID/style-recommendations?n=5"       # style cards: coverage, missing pieces, reasons, trend
curl "$API/style-library/trending?stage=rising"        # rising styles (Google Trends, weekly)
curl $API/style-library                                # 43 styles grounded in Aesthetics Wiki (+ discovered)

# daily outfit for the user's city (Prague), owned items only
curl -X POST $API/users/$UID/outfits/daily -H 'Content-Type: application/json' -d '{"event":"office day"}'

# add an item by photo URL (or multipart files=@photo.jpg); status=wanted for wishlist
curl -X POST $API/users/$UID/wardrobe -F image_urls=https://example.com/coat.jpg -F status=owned

# rebuild the taste profile (async job), then poll it
JOB=$(curl -s -X POST $API/users/$UID/taste-profile | python3 -c 'import json,sys;print(json.load(sys.stdin)["job_id"])')
curl $API/jobs/$JOB                                    # status: queued → running → done
```

From Python or a notebook:
```python
import requests, time, json, pathlib
API = "http://localhost:8000"
UID = json.loads(pathlib.Path("backend/scripts/test_user.json").read_text())["user_id"]

wardrobe = requests.get(f"{API}/users/{UID}/wardrobe").json()
taste = requests.get(f"{API}/users/{UID}/taste-profile").json()["profile"]
print(taste["headline"], taste["current_style"]["style_mix"], taste["aspirational_style"]["style_mix"])

def wait(job):
    while (j := requests.get(f"{API}/jobs/{job['job_id']}").json())["status"] in ("queued", "running"):
        time.sleep(3)
    return j

wait(requests.post(f"{API}/users/{UID}/taste-profile").json())
```

**Please don't delete the test user's items.** Other people use this user for UI testing. To experiment with destructive calls, create your own user with `POST /users`, or run the seed script.

Response shapes for every endpoint are in [`backend/schemas.md`](backend/schemas.md) and in Swagger at `/docs`.
