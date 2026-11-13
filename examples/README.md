# Wardrobe stylist PoC

`poc.ipynb` is a single notebook that runs the whole flow end to end:

1. **Wardrobe:** garment photos are tagged into JSON (category, colours, material, formality, warmth) by a vision model.
2. **Style library:** Pinterest pins for a few styles are fetched with the Apify `epctex/pinterest-scraper` Actor, and the vision model summarises each style.
3. **Profile:** the LLM matches the wardrobe to the styles and returns a style mix, wardrobe gaps and shop search queries.
4. **Shop:** Etsy products are found with the Apify `apify/e-commerce-scraping-tool` Actor, then the LLM picks the top 5 with reasons.
5. **Pasted link:** a product URL is scraped and the model gives a fit score and a verdict.
6. **Daily outfit:** Open-Meteo weather plus an event produce an outfit built only from the wardrobe.

The wardrobe photos come from Wikimedia Commons and stand in for user uploads.

## Setup

You need macOS (keys are read from the Keychain), [uv](https://docs.astral.sh/uv/), a Featherless AI key and an Apify token.

Apify note: the account must be allowed to run public Store Actors. A developer-only plan returns `public-actor-disabled`.

```bash
# 1. Store the keys once in the Keychain. Read them silently so they stay out of shell history.
read -s "FL?Featherless key: " && security add-generic-password -U -a "$USER" -s FEATHERLESS_API_KEY -w "$FL"; unset FL
read -s "AP?Apify token: "     && security add-generic-password -U -a "$USER" -s APIFY_TOKEN -w "$AP"; unset AP

# 2. Install the dependencies (run from the repo root)
uv sync
```

The notebook reads the keys straight from the Keychain. For shell use, `source env.sh` exports them in the current terminal only.

## Run

```bash
# interactive
uv run jupyter lab examples/poc.ipynb

# or headless, end to end
uv run jupyter nbconvert --to notebook --execute --inplace --ExecutePreprocessor.timeout=900 examples/poc.ipynb
```

The first run takes about 5–10 minutes because each Apify run takes 1–3 minutes. Every Actor result is cached in `cache/`, keyed by its input, so later runs are fast. Delete `cache/` to scrape fresh data.

## Customise

These are edited in the notebook cells:

| What | Where |
|---|---|
| Wardrobe photos | `WARDROBE_QUERIES` (or replace `wardrobe_urls` with your own image URLs) |
| Styles to compare | `STYLES` (Pinterest search terms) |
| Product link to check | `PASTED_URL` |
| City and event | `CITY`, `EVENT` |
| Models | `VISION`, `TEXT` |

`build_poc.py` is the source that generates the notebook. Edit it, then run `uv run python examples/build_poc.py`.

## Models (Featherless, OpenAI-compatible API)

- Vision: `Qwen/Qwen3-VL-30B-A3B-Instruct` takes about 13 s per image and is accurate. `google/gemma-4-31B-it` is also accurate but slower.
- Text: `zai-org/GLM-5.3-Flash`. **Don't use it for images.** On Featherless it ignores the image and invents a description.

## Cost (approximate)

| Service | Price |
|---|---|
| Pinterest search | ~$0.0015 per pin |
| E-commerce tool | ~$0.006 per product on the FREE tier |
| Featherless | fractions of a cent per call |
| Open-Meteo | free |

A full first run costs well under $0.50.
