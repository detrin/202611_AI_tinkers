"""All LLM reasoning lives here: prompts in, parsed JSON out. Depends only on the ChatModel port."""
import json
import re
from collections.abc import Sequence

from ..ports import ChatModel

TAG = """Identify the single main clothing item, shoe or accessory in this photo. Return ONLY JSON:
{"category":"top|bottom|outerwear|shoes|dress|accessory","subtype":"","colors":[],"pattern":"","material":"",
 "formality_1to5":0,"warmth_1to5":0,"style_tags":[]}"""

COLOR = """Do a seasonal colour analysis of this person (skin undertone, hair, eyes, contrast). Return ONLY JSON:
{"season":"e.g. Soft Autumn","undertone":"warm|cool|neutral","contrast":"low|medium|high",
 "best_colors":[],"avoid_colors":[],"notes":""}"""

STYLE = """These are Pinterest reference images for the style "{name}".
Return ONLY JSON: {{"key_items":[],"palette":[],"materials":[],"formality_1to5":0,"vibe":"one sentence"}}"""

PROFILE = """You are a personal stylist. Build the user's style profile from this context:
{context}
Return ONLY JSON:
{{"style_mix":[{{"style":"name from library","percent":0,"why":""}}],"taste_summary":"2 sentences",
  "wardrobe_gaps":[{{"item":"","why":""}}],"shop_queries":["3-5 short product search queries filling the gaps"]}}"""

RANK = """User profile: {profile}
Wardrobe: {wardrobe}
Candidate products: {candidates}
Pick the {n} best candidates for this user (skip irrelevant ones). Return ONLY JSON list:
[{{"id":0,"reason":"one sentence","pairs_with":["wardrobe ids"]}}]"""

VERDICT = """Product: {product}
User profile: {profile}
Wardrobe: {wardrobe}
Judge whether this product suits the user. Return ONLY JSON:
{{"score_1to10":0,"pairs_with":["wardrobe ids"],"redundant_with":["wardrobe ids"],"verdict":"2 sentences"}}"""

OUTFIT = """Weather: {weather}. Event: {event}. Colour profile: {colors}.
Recently worn item ids (avoid repeating): {recent}
Wardrobe: {wardrobe}
Build the best outfit ONLY from these items. Return ONLY JSON:
{{"item_ids":[],"explanation":"2-3 sentences","missing_item_tip":""}}"""


def parse_json(text: str):
    text = re.sub(r"^```(?:json)?|```$", "", text.strip(), flags=re.M).strip()
    match = re.search(r"[\[{].*[\]}]", text, re.S)
    return json.loads(match.group(0) if match else text)


def _dump(x) -> str:
    return json.dumps(x, default=str, ensure_ascii=False)


class Stylist:
    def __init__(self, model: ChatModel, retries: int = 1):
        self._model, self._retries = model, retries

    def _ask(self, prompt: str, images: Sequence[str] = ()):
        for attempt in range(self._retries + 1):
            try:
                return parse_json(self._model.complete(prompt, images))
            except ValueError:  # JSONDecodeError is a ValueError
                if attempt == self._retries:
                    raise

    def tag_item(self, image_url: str) -> dict:
        return self._ask(TAG, [image_url])

    def color_analysis(self, image_url: str) -> dict:
        return self._ask(COLOR, [image_url])

    def summarise_style(self, name: str, image_urls: list[str]) -> dict:
        return self._ask(STYLE.format(name=name), image_urls[:3])

    def profile(self, context: dict) -> dict:
        return self._ask(PROFILE.format(context=_dump(context)))

    def rank_products(self, profile: dict, wardrobe: list[dict], candidates: list[dict], n: int) -> list[dict]:
        return self._ask(RANK.format(profile=_dump(profile), wardrobe=_dump(wardrobe), candidates=_dump(candidates), n=n))

    def link_verdict(self, product: dict, profile: dict, wardrobe: list[dict], image_url: str | None) -> dict:
        prompt = VERDICT.format(product=_dump(product), profile=_dump(profile), wardrobe=_dump(wardrobe))
        return self._ask(prompt, [image_url] if image_url else [])

    def daily_outfit(self, weather: dict, event: str, wardrobe: list[dict], colors: dict | None, recent: list) -> dict:
        return self._ask(OUTFIT.format(weather=_dump(weather), event=event, colors=_dump(colors),
                                       recent=_dump(recent), wardrobe=_dump(wardrobe)))
