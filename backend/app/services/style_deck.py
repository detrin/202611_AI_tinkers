"""Next-k style pins: a Beta-Bernoulli bandit over styles, served as particular unseen Pinterest pins.

For every style we keep a belief p(like) ~ Beta(a, b):
  prior  = everything the user told us before swiping (taste profile, Instagram style, inspiration looks,
           wishlist/owned item tags, explicit style feedback), squashed to a prior mean m in (0, 1) and
           worth PRIOR_STRENGTH pseudo-swipes;
  update = +1 a per liked pin of that style, +1 b per disliked pin.

Each of the k slots is EXPLORE with probability `explore` (default 0.5), else EXPLOIT:
  explore → the style with the highest posterior variance (the swipe we learn most from), random unseen pin;
  exploit → the style with the highest posterior mean (most likely useful), its pin closest to liked pins.
Styles already picked in this batch are penalised so one batch spans several styles.

Pure functions only (no I/O) — PreferenceService feeds them rows and logs what was served.
"""
from __future__ import annotations

import math
import random
import re
from dataclasses import dataclass, field

from ..ports import Row

PRIOR_STRENGTH = 4.0          # the pre-swipe evidence is worth this many swipes
EXPLOIT_REPEAT_PENALTY = 0.15  # per pin of the same style already in this batch
STOP = {"a", "an", "the", "and", "or", "with", "of", "in", "style", "aesthetic", "core", "look", "looks", "outfit",
        "outfits", "fashion", "inspo", "inspiration", "wear", "for", "men", "women", "mens", "womens"}

# Positive sources have a weight BUDGET shared by all their terms (a user with 40 wardrobe tags must not drown out
# 4 inspiration looks); style mixes share it by percent. Avoid terms are deliberate negatives, so they count per term.
B_TASTE_ASPIRATION, B_TASTE_CURRENT, B_INSTAGRAM = 2.0, 1.0, 1.0
B_INSPIRATION, B_WANTED, B_OWNED = 1.5, 0.8, 0.6
W_TASTE_AVOID, W_INSTAGRAM_AVOID = -0.8, -0.5
DESC_MATCH = 0.3   # max credit when a term only hits a style's description/key pieces, not its name


def tokens(text) -> set[str]:
    words = re.findall(r"[a-z]+", str(text or "").lower())
    return {w[:-1] if len(w) > 3 and w.endswith("s") and not w.endswith("ss") else w for w in words} - STOP


@dataclass
class StyleBelief:
    style_id: str
    name: str
    prior_mean: float = 0.5
    likes: int = 0
    dislikes: int = 0
    evidence: list[str] = field(default_factory=list)   # human-readable prior reasons

    @property
    def a(self) -> float:
        return 1 + PRIOR_STRENGTH * self.prior_mean + self.likes

    @property
    def b(self) -> float:
        return 1 + PRIOR_STRENGTH * (1 - self.prior_mean) + self.dislikes

    @property
    def mean(self) -> float:
        return self.a / (self.a + self.b)

    @property
    def variance(self) -> float:
        s = self.a + self.b
        return self.a * self.b / (s * s * (s + 1))


def style_terms(style: Row) -> tuple[list[set[str]], set[str]]:
    """(token set per name/alias, descriptive tokens from definition/key pieces/summary)."""
    names = [t for t in map(tokens, [style.get("name"), *(style.get("aliases") or [])]) if t]
    summary = style.get("summary") or {}
    desc = set().union(*map(tokens, [style.get("definition"), *(style.get("key_pieces") or []),
                                     *(summary.get("key_items") or []), summary.get("vibe")]))
    return names, desc - set().union(*names)


def match(style: Row, term: str) -> float:
    """How much an evidence term (e.g. 'old money', 'minimal', 'tweed blazer') points at a style, 0..1."""
    t = tokens(term)
    if not t:
        return 0.0
    names, desc = style_terms(style)
    by_name = max((len(t & n) / len(t | n) for n in names), default=0.0)
    by_desc = DESC_MATCH * len(t & desc) / len(t)
    return max(by_name, by_desc)


def _shared(terms: list[str], budget: float, source: str) -> list[tuple[str, float, str]]:
    return [(t, budget / len(terms), source) for t in terms] if terms else []


def evidence_terms(ctx: Row) -> list[tuple[str, float, str]]:
    """(term, weight, source) from everything the user provided. `ctx` keys are all optional."""
    out: list[tuple[str, float, str]] = []
    taste = ctx.get("taste") or {}
    for view, budget in (("aspirational_style", B_TASTE_ASPIRATION), ("current_style", B_TASTE_CURRENT)):
        for m in (taste.get(view) or {}).get("style_mix") or []:
            out.append((m.get("style", ""), budget * (m.get("percent") or 50) / 100, f"taste profile ({view.split('_')[0]})"))
    out += [(t, W_TASTE_AVOID, "taste profile (avoid)") for t in taste.get("avoid") or []]
    ig = ctx.get("instagram") or {}
    out += _shared(ig.get("style_tags") or [], B_INSTAGRAM, "Instagram")
    out += [(t, W_INSTAGRAM_AVOID, "Instagram (avoid)") for t in ig.get("avoid_tags") or []]
    out += _shared([t for look in ctx.get("inspirations") or [] for t in look.get("style_tags") or []],
                   B_INSPIRATION, "inspiration looks")
    out += _shared([t for i in ctx.get("wanted") or [] for t in i.get("style_tags") or []], B_WANTED, "wishlist")
    out += _shared([t for i in ctx.get("owned") or [] for t in i.get("style_tags") or []], B_OWNED, "wardrobe")
    return out


def prior(style: Row, terms: list[tuple[str, float, str]], feedback: bool | None) -> tuple[float, list[str]]:
    """Prior mean in (0.05, 0.95) plus the sources that moved it. Explicit style feedback dominates."""
    if feedback is not None:
        return (0.9, ["you marked this style as interesting"]) if feedback else (0.08, ["you said not interested"])
    raw, why = 0.0, {}
    for term, weight, source in terms:
        if (m := match(style, term)) > 0:
            raw += weight * m
            why[source] = why.get(source, 0) + weight * m
    mean = 0.5 + 0.45 * math.tanh(raw)
    return mean, [s for s, v in sorted(why.items(), key=lambda kv: -abs(kv[1])) if abs(v) >= 0.05]


def beliefs(styles: list[Row], pins: dict[str, Row], swipes: list[Row], ctx: Row) -> dict[str, StyleBelief]:
    terms = evidence_terms(ctx)
    feedback = ctx.get("style_feedback") or {}
    out = {}
    for s in styles:
        mean, why = prior(s, terms, feedback.get(s["id"]))
        out[s["id"]] = StyleBelief(s["id"], s["name"], mean, evidence=why)
    for sw in swipes:
        if (pin := pins.get(sw["pin_id"])) and (b := out.get(pin["style_id"])):
            if sw["liked"]:
                b.likes += 1
            else:
                b.dislikes += 1
    return out


def reason(b: StyleBelief, mode: str) -> str:
    seen = b.likes + b.dislikes
    if mode == "explore":
        return (f"Exploring {b.name}: {seen} swipe{'s' * (seen != 1)} so far, "
                f"we're unsure ({b.mean:.0%} chance you like it)")
    if seen:
        return f"You liked {b.likes} of {seen} {b.name} looks"
    if b.evidence:
        return f"{b.name} matches your " + " and ".join(b.evidence[:2])
    return f"A starting point: no signal about {b.name} yet"


def pick_pin(candidates: list[Row], mode: str, liked_terms: set[str], rng: random.Random) -> Row:
    if mode == "explore" or not liked_terms:
        return rng.choice(candidates)
    return max(candidates, key=lambda p: (len(tokens(p.get("title")) & liked_terms), rng.random()))


def next_pins(beliefs_by_style: dict[str, StyleBelief], unseen: dict[str, list[Row]], k: int, explore: float,
              liked_terms: set[str], rng: random.Random) -> list[Row]:
    """Choose k unseen pins. Each slot: explore (max variance) with prob `explore`, else exploit (max mean)."""
    pools = {sid: list(p) for sid, p in unseen.items() if p and sid in beliefs_by_style}
    in_batch: dict[str, int] = {}
    out = []
    while len(out) < k and pools:
        mode = "explore" if rng.random() < explore else "exploit"

        def value(sid: str) -> float:
            b, n = beliefs_by_style[sid], in_batch.get(sid, 0)
            return b.variance / (1 + n) if mode == "explore" else b.mean - EXPLOIT_REPEAT_PENALTY * n

        sid = max(pools, key=lambda s: (value(s), rng.random()))
        pin = pick_pin(pools[sid], mode, liked_terms, rng)
        pools[sid].remove(pin)
        if not pools[sid]:
            del pools[sid]
        in_batch[sid] = in_batch.get(sid, 0) + 1
        b = beliefs_by_style[sid]
        out.append({**pin, "style_name": b.name, "mode": mode, "p_like": round(b.mean, 3),
                    "uncertainty": round(math.sqrt(b.variance), 3), "reason": reason(b, mode)})
    return out
