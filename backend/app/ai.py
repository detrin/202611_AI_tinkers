"""Prompts + AI steps. Each function returns plain dicts."""
import json

from .core import ask_json

TAG_PROMPT = """Identify the single main clothing item, shoe or accessory in this photo. Return ONLY JSON:
{"category":"top|bottom|outerwear|shoes|dress|accessory","subtype":"","colors":[],"pattern":"","material":"",
 "formality_1to5":0,"warmth_1to5":0,"style_tags":[]}"""

COLOR_PROMPT = """Do a seasonal colour analysis of this person (skin undertone, hair, eyes, contrast). Return ONLY JSON:
{"season":"e.g. Soft Autumn","undertone":"warm|cool|neutral","contrast":"low|medium|high",
 "best_colors":["8-12 colour names"],"avoid_colors":["3-6 colour names"],"notes":""}"""

STYLE_PROMPT = """These are Pinterest reference images for the style "{name}".
Return ONLY JSON: {{"key_items":[],"palette":[],"materials":[],"formality_1to5":0,"vibe":"one sentence"}}"""


def tag_item(image_url: str) -> dict:
    return ask_json(TAG_PROMPT, [image_url])


def color_analysis(image_url: str) -> dict:
    return ask_json(COLOR_PROMPT, [image_url])


def summarise_style(name: str, image_urls: list[str]) -> dict:
    return ask_json(STYLE_PROMPT.format(name=name), image_urls[:3])


def compute_profile(user: dict, wardrobe: list[dict], styles: list[dict], liked: list[dict], disliked: list[dict],
                    links: list[dict]) -> dict:
    return ask_json(f"""You are a personal stylist. Build the user's style profile.
USER: {json.dumps({k: user.get(k) for k in ['city', 'budget', 'currency', 'fit_prefs', 'color_profile']})}
WARDROBE: {json.dumps(wardrobe)}
STYLE LIBRARY: {json.dumps(styles)}
LIKED PINS (style, title): {json.dumps(liked)}
DISLIKED PINS: {json.dumps(disliked)}
PRODUCT LINKS THE USER SAVED: {json.dumps(links)}
Return ONLY JSON:
{{"style_mix":[{{"style":"name from library","percent":0,"why":""}}],
  "taste_summary":"2 sentences",
  "wardrobe_gaps":[{{"item":"","why":""}}],
  "shop_queries":["3-5 short product search queries that fill the gaps, match the style and the colour palette"]}}""")


def rank_products(profile: dict, wardrobe: list[dict], products: list[dict], n: int) -> list[dict]:
    cands = [{"id": i, "name": p["name"], "price": p.get("price"), "currency": p.get("currency")} for i, p in enumerate(products)]
    wd = [{"id": w["id"], "item": f"{w.get('subtype')} ({', '.join(w.get('colors') or [])})"} for w in wardrobe]
    return ask_json(f"""User style mix: {json.dumps(profile.get('style_mix'))}. Taste: {profile.get('taste_summary')}
Wardrobe gaps: {json.dumps(profile.get('gaps'))}
Wardrobe: {json.dumps(wd)}
Candidates: {json.dumps(cands)}
Pick the {n} best candidates (skip irrelevant ones). Return ONLY JSON list:
[{{"id":0,"reason":"one sentence why it fits","pairs_with":["wardrobe ids it combines with"]}}]""")


def link_verdict(product: dict, profile: dict | None, wardrobe: list[dict], image_url: str | None) -> dict:
    wd = [{"id": w["id"], "item": w.get("subtype"), "colors": w.get("colors")} for w in wardrobe]
    return ask_json(f"""Product: {product.get('name')} — price {product.get('price')} {product.get('currency')}
Description: {(product.get('description') or '')[:800]}
User style mix: {json.dumps((profile or {}).get('style_mix'))}. Wardrobe: {json.dumps(wd)}
{"Look at the product photo. " if image_url else ""}Return ONLY JSON:
{{"score_1to10":0,"pairs_with":["wardrobe ids"],"verdict":"2 sentences","redundant_with":["wardrobe ids it duplicates"]}}""",
                    [image_url] if image_url else [])


def daily_outfit(weather: dict, event: str, wardrobe: list[dict], color_profile: dict | None, recent: list) -> dict:
    wd = [{k: w.get(k) for k in ['id', 'category', 'subtype', 'colors', 'pattern', 'material', 'formality', 'warmth']}
          for w in wardrobe]
    return ask_json(f"""Weather today: {json.dumps(weather)}. Event: {event}.
Colour profile: {json.dumps(color_profile)}. Recently worn item ids (avoid repeating): {json.dumps(recent)}
Wardrobe: {json.dumps(wd)}
Build the best outfit ONLY from these items (use their ids). Return ONLY JSON:
{{"item_ids":[],"explanation":"2-3 sentences","missing_item_tip":"one item that would improve this outfit, or empty"}}""")
