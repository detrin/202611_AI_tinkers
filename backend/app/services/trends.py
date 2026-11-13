"""Style momentum (Google Trends) and discovery of new style names from rising related queries.

Google Trends values are relative to each term's own 12-month peak (0-100), so we compare a style with its own
past, never volumes across styles.
"""
from __future__ import annotations

import json
from statistics import mean

from ..domain import TrendSeries
from ..ports import Database, Row, StructuredModel, TrendSource
from .base import latest
from .style_library import StyleLibraryService

WINDOW = 8          # weeks
MIN_NONZERO = 0.5   # share of non-zero weeks (last 2 windows) below which Google has too little data
PRIOR_FLOOR = 5     # avoid "+2000%" growth from a near-zero baseline
STAGE_BONUS = {"emerging": 0.15, "rising": 0.10, "peak": 0.05, "stable": 0.0, "fading": -0.05, "low_volume": 0.0,
               "unknown": 0.0}

DISCOVER = """These search queries are rising on Google Trends around known fashion styles.
KNOWN STYLES (do not repeat, including aliases): {known}
RISING QUERIES [query, growth %, seen next to style]: {rising}
Pick at most {n} queries that name a NEW wearable fashion style/aesthetic (not a brand, celebrity, how-to or a
known style). Give each a canonical name and the evidence."""

DISCOVER_SCHEMA = {"type": "object", "required": ["new_styles"], "properties": {"new_styles": {"type": "array", "items": {
    "type": "object", "required": ["name", "evidence"],
    "properties": {"name": {"type": "string"}, "evidence": {"type": "string"}}}}}}


def lifecycle(points: list[tuple[str, int]] | tuple, window: int = WINDOW) -> Row:
    """Stage from the last `window` weeks vs the `window` before: emerging / rising / peak / stable / fading,
    or low_volume when Google mostly reports zeros (the term is too niche to judge)."""
    values = [v for _, v in points]
    if len(values) < 2 * window or max(values) == 0:
        return {"stage": "unknown", "recent": None, "prior": None, "growth": None}
    recent, prior = mean(values[-window:]), mean(values[-2 * window:-window])
    nonzero = sum(v > 0 for v in values[-2 * window:]) / (2 * window)
    if nonzero < MIN_NONZERO:
        return {"stage": "low_volume", "recent": round(recent, 1), "prior": round(prior, 1), "growth": None,
                "nonzero_weeks": round(nonzero, 2)}
    growth = (recent - prior) / max(prior, PRIOR_FLOOR)
    if growth >= 0.5 and recent < 50:
        stage = "emerging"
    elif growth >= 0.15:
        stage = "rising"
    elif growth <= -0.15:
        stage = "fading"
    elif recent >= 70:
        stage = "peak"
    else:
        stage = "stable"
    return {"stage": stage, "recent": round(recent, 1), "prior": round(prior, 1), "growth": round(growth, 3)}


class TrendService:
    def __init__(self, db: Database, source: TrendSource, library: StyleLibraryService, model: StructuredModel):
        self._db, self._source, self._library, self._model = db, source, library, model

    def refresh(self, geo: str = "") -> Row:
        styles = {(s.get("search_term") or s["name"]).lower(): s for s in self._library.active()}
        stages: dict[str, int] = {}
        for series in self._source.interest(list(styles), geo):
            if not (style := styles.get(series.term.lower())):
                continue
            metrics = lifecycle(series.points)
            self._snapshot(style, series, geo, metrics)
            self._db.update("styles", {"id": style["id"]}, {"lifecycle": metrics["stage"], "trend": metrics})
            stages[metrics["stage"]] = stages.get(metrics["stage"], 0) + 1
        return {"styles": len(styles), "stages": stages}

    def _snapshot(self, style: Row, series: TrendSeries, geo: str, metrics: Row) -> None:
        self._db.insert("style_trend_snapshots", {
            "style_id": style["id"], "term": series.term, "geo": geo, "points": [list(p) for p in series.points],
            "rising": [list(r) for r in series.rising], "metrics": metrics})

    def rising_queries(self) -> list[Row]:
        out = []
        for style in self._library.active():
            if snap := latest(self._db, "style_trend_snapshots", style_id=style["id"]):
                out += [{"query": q, "growth": g, "near": style["name"]} for q, g in snap.get("rising") or []]
        return sorted(out, key=lambda r: -r["growth"])

    def discover(self, max_new: int = 5) -> Row:
        rising = self.rising_queries()
        if not rising:
            return {"new_styles": []}
        known = sorted(self._library.known_names())
        picks = self._model.generate(DISCOVER.format(known=json.dumps(known), n=max_new,
                                                     rising=json.dumps([[r["query"], r["growth"], r["near"]] for r in rising[:150]])),
                                     DISCOVER_SCHEMA)["new_styles"][:max_new]
        fresh = [p for p in picks if p["name"].lower() not in known]
        rows = self._library.define([p["name"] for p in fresh], source="trends_discovery",
                                    context={p["name"]: p["evidence"] for p in fresh}) if fresh else []
        return {"new_styles": [{"id": r["id"], "name": r["name"], "definition": r["definition"]} for r in rows]}

    def trending(self, stage: str | None = None, limit: int = 20) -> list[Row]:
        styles = [s for s in self._library.active() if s.get("trend") and (not stage or s.get("lifecycle") == stage)]
        growth = lambda s: s["trend"]["growth"] if s["trend"].get("growth") is not None else float("-inf")
        return sorted(styles, key=growth, reverse=True)[:limit]
