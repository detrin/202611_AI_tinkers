"""AestheticSource over the Aesthetics Wiki MediaWiki API (aesthetics.fandom.com). Content is CC BY-SA."""
import re

import requests

from ..domain import AestheticPage

API = "https://aesthetics.fandom.com/api.php"
PAGE_URL = "https://aesthetics.fandom.com/wiki/"
UA = {"User-Agent": "wardrobe-stylist/0.1 (hackathon)"}
INFOBOX_FIELDS = ("other_names", "decade_of_origin", "key_motifs", "key_colours", "key_values", "related_aesthetics")
MAX_TEXT = 2500


def clean_markup(text: str) -> str:
    text = re.sub(r"<ref[^>]*?/>|<ref[^>]*>.*?</ref>", "", text, flags=re.S)
    text = re.sub(r"<br\s*/?>", ", ", text)
    text = re.sub(r"\[\[(?:File|Image):[^\]]*\]\]", "", text)
    text = re.sub(r"\[\[[^\]|]*\|([^\]]*)\]\]", r"\1", text)           # [[Target|Label]] → Label
    text = re.sub(r"\[\[([^\]]*)\]\]", r"\1", text)                    # [[Target]] → Target
    text = re.sub(r"\[https?://\S+ ([^\]]*)\]", r"\1", text)           # [url label] → label
    while re.search(r"\{\{[^{}]*\}\}", text):
        text = re.sub(r"\{\{[^{}]*\}\}", "", text)                    # templates (nested-safe)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"'{2,}", "", text)
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip(" ,\n")


def parse_infobox(wikitext: str) -> dict:
    out = {}
    for name in INFOBOX_FIELDS:
        m = re.search(rf"\|\s*{name}\s*=(.*?)(?=\n\s*\||\n\}}\}})", wikitext, re.S)
        if m and (value := clean_markup(m.group(1))):
            out[name] = value
    return out


def fashion_section(wikitext: str) -> str:
    """The level-2 'Fashion' section if present, else the lead paragraph after the infobox."""
    m = re.search(r"\n==\s*Fashion\s*==\s*\n(.*?)(?=\n==[^=]|\Z)", wikitext, re.S)
    if m:
        body = m.group(1)
    else:
        body = re.split(r"\n==[^=]", wikitext, maxsplit=1)[0]
        body = body[body.rfind("}}") + 2:] if "}}" in body else body
    return clean_markup(re.sub(r"\n=+\s*([^=]+?)\s*=+", r"\n\1:", body))[:MAX_TEXT]


class FandomAestheticSource:
    def __init__(self, session: requests.Session | None = None, batch: int = 20):
        self._s, self._batch = session or requests.Session(), batch

    def pages(self, titles: list[str]) -> list[AestheticPage]:
        out = []
        for i in range(0, len(titles), self._batch):
            out += self._fetch(titles[i:i + self._batch])
        return out

    def _fetch(self, titles: list[str]) -> list[AestheticPage]:
        data = self._s.get(API, headers=UA, timeout=30, params={
            "action": "query", "prop": "revisions", "rvprop": "content", "rvslots": "main", "redirects": 1,
            "titles": "|".join(titles), "format": "json", "formatversion": 2}).json()
        pages = []
        for p in data.get("query", {}).get("pages", []):
            if p.get("missing") or not p.get("revisions"):
                continue
            wikitext = p["revisions"][0]["slots"]["main"]["content"]
            pages.append(AestheticPage(title=p["title"], url=PAGE_URL + p["title"].replace(" ", "_"),
                                       infobox=parse_infobox(wikitext), fashion_text=fashion_section(wikitext)))
        return pages
