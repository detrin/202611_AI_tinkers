# Handoff: the outfit agent and its MCP tools

**To the human:** open this repo in Codex and say: "Read docs/codex-handoff.md and start." Codex takes it from there and will tell you what to do, including what to ask Dan.

**To Codex:** everything below is for you. It is the full context of a planning session you were not part of. Read all of it, then read the files listed under "What already exists" before writing anything.

---

## How to work with this person

- They are a capable developer who has not used MCP, iCal or Apify before. Explain each new term in one or two plain sentences the first time it comes up. Use the glossary at the bottom.
- Lead. At every point, tell them the one next thing to do. Do not present menus of options; pick one and say why in a sentence.
- Some steps only a human can do (get a key from Dan, click through Google Calendar settings, agree a decision). When you reach one, stop and give them the exact words to say or the exact clicks, then wait.
- This is a hackathon with a hard deadline. Run every piece against the real service as soon as it exists and show the real output. Never substitute made-up data for a failing call; show the error.
- Keep the code small. Match the style in `backend/app/`: plain functions, short modules, no new frameworks.
- Do not rewrite or reformat Dan's files. Add new files, and make the smallest possible edits to his. Run `uv run pytest` before every push; all existing tests must still pass. Tell the human to check with Dan before pushing anything that touches his files.

## The situation

- **Event:** AI Tinkerers Prague hackathon, today, 13 Nov 2026. Live demos at **18:00**, no recordings. Feature freeze for our team is **17:15**.
- **Product:** "Good Enough", a personal wardrobe agent. In the morning it reads your day and tells you what to wear from clothes you already own, with a one-line reason. The full idea is in `personal-wardrobe-agent.md` if it is in the repo.
- **Judges ask:** does it solve a real problem for a real person, does it work live, how well did we use the sponsor tools (Apify, Featherless, PostHog), would non-technical people use it.
- **Team:**
  - Sun: owns the idea and the data schema.
  - Dan: owns the backend and the LLM calls. His laptop is the server for the demo.
  - The PWA developer: building the phone app that calls Dan's API.
  - You and your human: the piece described here.

## What already exists (read these first)

**Updated 15:20.** Dan refactored the backend after the first version of this file. If you were told about `backend/app/core.py` or `backend/app/ai.py`, those files are gone. Run `git pull` before anything else; Dan pushes often, so pull before each step.

Dan's backend is in `backend/`, Python 3.12 with FastAPI, managed with `uv`. It follows a ports-and-adapters layout and has 60 unit tests that run on in-memory fakes.

- `backend/schemas.md`: the API spec, the data model, the architecture and its rules. Read it fully. The three rules that bind you: services never import FastAPI or an SDK, adapters hold no business logic, routers only translate HTTP to service calls.
- `backend/app/ports.py`: the interfaces (`Database`, `ChatModel`, `WeatherProvider`, `SocialSource` and others).
- `backend/app/adapters/`: the real implementations. `featherless.py` is the LLM client (OpenAI SDK pointed at Featherless), `web.py` has `OpenMeteoWeather` (daily values only), `supabase.py` is the database, `apify.py` runs actors.
- `backend/app/services/stylist.py`: every prompt. `daily_outfit(weather, event, wardrobe, colors, recent)` is the current outfit picker.
- `backend/app/services/outfits.py`: `OutfitService.daily()` is the current flow behind `POST /users/{uid}/outfits/daily`.
- `backend/app/container.py`: where adapters are wired to services.
- `backend/app/config.py`: settings and secrets (environment variable first, then macOS Keychain).
- `backend/tests/`: `fakes.py` and `conftest.py` show how to test without the network.

How the outfit is chosen today: the caller types the event as a string ("office"), the backend fetches the daily weather for the user's city, and one prompt picks items from the owned wardrobe. The model never sees the calendar, the venue or the commute, and it cannot ask for anything.

Useful things Dan has already built that the agent should use:

- Wardrobe items have `status` (owned or wanted) and `availability` (available, laundry, lent, stored). Only owned and available items may be recommended.
- `users.style_profile` holds a style summary built from the user's Instagram (`style_tags`, `preferred_colors`, `preferred_fit`, `avoid_tags`, `typical_formality_1to5`). `users.color_profile` holds the selfie colour analysis.

### Where your code goes

Follow Dan's layout so he can merge it without rework:

| New file | What it is |
|---|---|
| `backend/mcp_server.py` | Our MCP server, a standalone process. It may reuse Dan's adapters for database and weather access. |
| `backend/app/ports.py` (add one Protocol) | `ToolSource`: `list_tools()` and `call_tool(name, args)`. |
| `backend/app/adapters/mcp_tools.py` | The MCP client that implements `ToolSource`. All `mcp` SDK imports stay in here. |
| `backend/app/services/agent.py` | The agent loop. Depends only on `ChatModel`, `ToolSource` and existing services. |
| `backend/app/api/routers/outfits.py` (add one route) | `POST /today`, a thin call into the service. |
| `backend/app/container.py` (small edit) | Wire the new adapter and service. |
| `backend/tests/test_agent.py` | A fake `ToolSource` and the scripted chat fake already in `tests/fakes.py`. Test the tool-call limit, the wardrobe-only rule and the fallback. |

## The mission

Turn the outfit picker into an agent: the LLM gets tools, decides which ones to call, and reasons from what they return. The target behaviour, in the words of the team:

> Today is rainy, they are going to a luxury restaurant and they will take the metro, so they need to wear that kind of thing today.

The tools reach the LLM through **MCP**, a standard way to hand tools to a model. Two MCP servers:

1. **Our own server**, which you build. Small Python file, exposes our data as tools.
2. **Apify's hosted server** at `https://mcp.apify.com`, which already exists. It exposes Apify actors as tools. We use it for one thing: looking up what kind of place an event is at.

### Target design

```
PWA ──HTTP──> FastAPI backend (Dan)
                 │
                 └─ agent loop (new: backend/app/services/agent.py)
                      │  LLM on Featherless decides which tool to call next
                      ├── MCP ──> our server (new: backend/mcp_server.py)
                      │             get_calendar_events   Google Calendar via secret iCal link
                      │             get_weather           Open-Meteo, hourly
                      │             get_commute           user's usual transport + distance
                      │             get_wardrobe          Supabase, the user's clothes
                      │             get_recent_outfits    Supabase, to avoid repeats
                      └── MCP ──> https://mcp.apify.com
                                    compass/crawler-google-places   venue category
```

### Tools on our server

| Tool | Input | Returns | Source |
|---|---|---|---|
| `get_calendar_events` | `date` (optional, default today) | `[{title, start_time, end_time, location}]` | iCal link in `CALENDAR_ICS_URL` |
| `get_weather` | `city`, `date` (optional) | current values plus `hourly: [{time, temperature_c, feels_like_c, rain_probability}]`, with `rain_probability` from 0 to 1 | Open-Meteo. Dan's `OpenMeteoWeather.daily()` returns daily values only, so add an hourly method or a small function of your own rather than changing his. Request `hourly=temperature_2m,apparent_temperature,precipitation_probability` |
| `get_commute` | `user_id`, `destination` (optional) | `{mode, distance_km, outdoor_minutes_estimate}` | `mode` is read from the user's `fit_prefs.commute_mode` (metro, bike, walk, car; default metro). Distance is straight-line from the user's city centre to the destination, geocoded with Open-Meteo's geocoding API. This is an estimate and the tool's description must say so. Real transit routing needs a paid Google key and is out of scope. |
| `get_wardrobe` | `user_id` | items with `status=owned` and `availability=available`: `id, category, subtype, colors, pattern, material, fit, formality, warmth` | Supabase table `wardrobe_items` |
| `get_style_profile` | `user_id` | the user's `style_profile` and `color_profile` | Supabase table `users` |
| `set_item_availability` | `user_id`, `item_id`, `availability` | the updated item. Lets the agent act on a note like "those pants are in the laundry" before choosing again | Supabase table `wardrobe_items` |
| `get_recent_outfits` | `user_id` | item ids worn in the last 3 outfits | Supabase table `outfits` |

Write each tool's description as if briefing a stylist: what it returns and when it is worth calling. The model chooses tools from those descriptions.

### The new endpoint

`POST /users/{uid}/outfits/today`, body `{ "date": optional, "note": optional free text such as "those pants are in the laundry" }`.

It returns what `/outfits/daily` returns today (`id, item_ids, explanation, missing_item_tip, weather, items[]` with signed image URLs), plus two fields the PWA needs:

```json
{
  "context": {
    "events": [{ "title": "", "start_time": "19:00", "location": "", "place_category": "Fine dining restaurant" }],
    "weather": { "temperature_c": 8.2, "feels_like_c": 3.6, "rain_probability": 0.7 },
    "commute": { "mode": "metro", "outdoor_minutes_estimate": 12 }
  },
  "steps": [
    { "tool": "get_calendar_events", "summary": "2 events today" },
    { "tool": "compass/crawler-google-places", "summary": "Café Savoy is a fine dining restaurant" }
  ],
  "from_fallback": false
}
```

`steps` is the list of tool calls the agent made, in order, each with a one-line human-readable summary. The PWA shows it as "how I decided". It is also our proof to the judges that this is an agent.

Leave `/outfits/daily` exactly as it is. It is the safety net.

### Rules the agent must follow

- Only items returned by `get_wardrobe` may be recommended. After the model answers, drop any id not in the wardrobe, the way `daily()` already does.
- At most 8 tool calls and 60 seconds per request. When either limit is hit, the model must answer with what it has.
- If the agent loop fails for any reason, call the existing `Stylist.daily_outfit()` with whatever context was gathered and set `from_fallback: true`. The endpoint must never return a 500 during the demo.
- The final explanation is two or three plain sentences that name the actual reasons (rain, the venue, the metro). No fashion jargon.

## Order of work

Times are targets. If a step runs 20 minutes over, tell the human and cut scope using the "If time runs short" list.

### Step 0: talk to Dan (do this before any code)

Tell the human to go to Dan now with these five points:

1. "I am adding an agent that picks the outfit using MCP tools, following your ports-and-adapters layout: a new `ToolSource` port, an MCP adapter, an agent service, an MCP server file, and one new endpoint `POST /users/{uid}/outfits/today`. Your `/outfits/daily` stays untouched. Shall I work on a branch and open a pull request, or push to main?"
2. "I need these secrets to run the backend on my machine: `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `FEATHERLESS_API_KEY`, `APIFY_TOKEN`." Hand them over in person or through a password manager, never in chat. The config reads environment variables first, so a local `.env` loaded into the shell works on any OS. `.env` is already in `.gitignore`.
3. "Does the text model on Featherless support tool calling? If you know one that does, which?" The default text model is `zai-org/GLM-5.3-Flash`.
4. "Which user id is the demo user, and does it have wardrobe items yet?"
5. "The PWA runs in a browser on another origin. `backend/app/main.py` has no CORS middleware yet. Will you add it or shall I?" This blocks the PWA, so settle it now.

### Step 1: run the backend locally (by 15:20)

`uv sync`, export the secrets, then `uv run uvicorn backend.app.main:app --reload --port 8000`. Confirm `GET /health` and `GET /users/{uid}/wardrobe` for the demo user return real data.

### Step 2: check tool calling on Featherless (by 15:30)

Write a ten-line script using the `openai` client configured the way `adapters/featherless.py` configures it, which sends one chat completion with a single dummy tool in the `tools` parameter and prints whether the response contains `tool_calls`. Try `TEXT_MODEL` first, then any model Dan suggested.

- If a model returns proper tool calls: the agent loop uses native tool calling with that model.
- If none does: the agent loop uses a JSON protocol. The system prompt lists the tools and the model replies with either `{"tool": "...", "args": {...}}` or `{"final": {...}}`, parsed with `parse_json()` from `services/stylist.py`. It is still the model choosing the tools, and still MCP executing them.

Do not spend more than ten minutes here. Pick and move on.

### Step 3: our MCP server (by 16:00)

- Add the official `mcp` Python package with `uv add mcp`. It includes `FastMCP`, where a tool is a decorated Python function. Check the installed version's README for the current import paths and the streamable HTTP transport before writing code; do not rely on memory.
- For the calendar, add `icalendar` and `recurring-ical-events`. Fetch `CALENDAR_ICS_URL`, return the given day's events in the Europe/Prague timezone, sorted by start. Expand recurring events. Skip all-day and cancelled events.
- Build the tools from the table above in `backend/mcp_server.py`. Reuse Dan's Supabase adapter and the secret loading in `config.py`.
- Human step, calendar link: in Google Calendar on a computer, gear icon → Settings → click the calendar's name in the left column → "Integrate calendar" → copy "Secret address in iCal format" (it ends in `/basic.ics`). Put it in the environment as `CALENDAR_ICS_URL`. It must be the calendar of the person whose day we demo. Anyone with this link can read the whole calendar, so treat it like a password. If the field is missing, it is a work account with the feature disabled: use a personal Gmail calendar.
- Test every tool on its own with real inputs and show the output. The MCP Inspector (`npx @modelcontextprotocol/inspector`) is the quickest way to click through them.

### Step 4: the agent loop and the endpoint (by 16:40)

- `backend/app/adapters/mcp_tools.py` connects to our MCP server and implements `ToolSource`. `backend/app/services/agent.py` lists the tools, runs the loop from step 2 until the model gives a final answer or a limit is hit, and records every call in `steps`.
- Add the `POST /today` route in `api/routers/outfits.py` and wire everything in `container.py`. Save the result to the `outfits` table the same way `OutfitService.daily()` does, and return the shape described above. The `outfits` table has no columns for `context` and `steps`; return them in the response without storing them, unless Dan prefers to add a column.
- Test with the demo user. Then add an evening event at a restaurant to the calendar, wait for it to appear, call again and confirm the outfit and the explanation change.
- As soon as the endpoint returns a correct shape, tell the human to tell the PWA developer. They are waiting on it.

### Step 5: Apify MCP for the venue (by 17:10, only if step 4 works)

- Connect the agent to `https://mcp.apify.com` as a second MCP server, authenticated with `Authorization: Bearer <APIFY_TOKEN>`. Read https://docs.apify.com/platform/integrations/mcp for how to restrict the server to specific actors; we want only `compass/crawler-google-places`. Do not guess the URL parameters or the tool's input fields: list the tools from the server and read the schema it returns.
- In the system prompt, tell the model to look up a venue only when an event has a location and the title alone does not make the dress code obvious, and to request a single result.
- Each lookup can take 20 to 60 seconds and costs credits. Cache results by location string in `cache/places.json` (the `cache/` folder is already git-ignored) so a venue is never looked up twice. Before the demo, run the endpoint once with the demo calendar so the cache is warm.
- A failed or slow lookup must never fail the request. Time it out at 45 seconds and let the model continue without it.

### Step 6: freeze at 17:15

Stop adding. Run the endpoint five times in a row with the demo user and confirm five good answers. Fix only what that reveals. Run `uv run pytest`. Update `backend/schemas.md` with the new endpoint and the new environment variable.

## If time runs short

Cut in this order, and tell the human each time:

1. Drop step 5. The agent still reads calendar, weather, commute and wardrobe through our own MCP server.
2. Drop `get_commute`'s distance and return only the transport mode.
3. Replace the model-driven loop with a fixed sequence: the backend calls all tools through MCP itself, then makes one LLM call with everything. Say honestly in the demo that the tool order is fixed.

## Things already checked, so you do not repeat them

- Open-Meteo needs no key and returns hourly temperature, feels-like and rain probability for Prague.
- There is no Google Calendar actor on Apify. The iCal link is the fast route; Google's own Calendar API needs an OAuth setup that will not fit in the time left.
- Edits in Google Calendar can take a few minutes to show in the iCal file. For the live "change something and watch the outfit change" moment in the demo, the `note` field on the endpoint is the instant path; a new calendar event must be added a few minutes before going on stage.
- `apify/e-commerce-scraping-tool` is already used by Dan for products. `compass/crawler-google-places` is the main Google Maps actor on Apify (about 696k users). It returns places, not routes.
- All of these Apify actors charge per result. Dan's Apify adapter caps the cost per run; keep a cap on anything you add.
- Vision calls must use `VISION_MODEL`. The text model ignores images on Featherless.

## Glossary for the human

- **API:** a URL that code requests and that answers with data (JSON) instead of a web page.
- **Endpoint:** one such URL on our own backend, for example `POST /users/{uid}/outfits/today`.
- **LLM tool calling:** instead of only writing text, the model can answer "call this function with these arguments". Our code runs the function, gives the result back, and the model continues. Repeating that is an agent loop.
- **MCP (Model Context Protocol):** a standard plug for tools. An MCP server offers a list of tools with descriptions; an MCP client (our backend) connects, reads the list and passes it to the model. The benefit is that tools built by others, like Apify's, plug in the same way as ours.
- **iCal / .ics:** a plain text calendar format. Google can publish a calendar as an .ics file at a secret URL, which lets us read events without a login flow.
- **Apify:** a platform hosting ready-made scrapers. Each scraper is an **actor**. You send it input, it runs in Apify's cloud, and you read its results.
- **Supabase:** the hosted Postgres database Dan uses for users, wardrobe and outfits.
- **Featherless:** the sponsor that hosts the open-source models we call. It speaks the same API as OpenAI, which is why the code uses the `openai` package.
- **CORS:** a browser rule that blocks a web page from calling a server on a different address unless that server explicitly allows it.
