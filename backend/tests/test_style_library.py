import pytest

from backend.app.adapters.apify import to_trend
from backend.app.adapters.fandom import clean_markup, fashion_section, parse_infobox
from backend.app.domain import ImageInput
from backend.app.errors import NotFound
from backend.app.services.style_recs import coverage, head, similarity, tokens
from backend.app.services.trends import lifecycle

from .fakes_styles import series

WIKITEXT = """{{Good Article|Feb}}
{{Aesthetic
|title1=Dark Academia
|other_names=Academia
|key_colours=Black, brown<br>[[Burgundy|dark red]]
|related_aesthetics=[[Light Academia]]<br>[[Old Money]]
|preceded_by=x}}
'''Dark Academia''' is an aesthetic about [[literature]].<ref>cite</ref>
==History==
old stuff
==Fashion==
Tweed blazers and {{tpl|x}} pleated skirts.
===Shoes===
Oxford shoes.
==Media==
films"""


# ---------- pure parsers ----------
def test_parse_infobox_cleans_links_and_breaks():
    box = parse_infobox(WIKITEXT)
    assert box["key_colours"] == "Black, brown, dark red"
    assert box["related_aesthetics"] == "Light Academia, Old Money"
    assert box["other_names"] == "Academia"


def test_fashion_section_includes_subsections_and_stops_at_next_section():
    text = fashion_section(WIKITEXT)
    assert "Tweed blazers" in text and "Oxford shoes" in text and "Shoes:" in text
    assert "films" not in text and "{{" not in text


def test_fashion_section_falls_back_to_lead():
    assert fashion_section("{{Aesthetic|x=1}}\nLead about [[coats]].\n==History==\nold") == "Lead about coats."


def test_clean_markup_nested_templates_and_refs():
    assert clean_markup("a {{x|{{y}}}} b<ref name=r/> [[File:a.jpg]]'''c'''") == "a b c"


def test_to_trend_parses_timeline_and_rising():
    t = to_trend({"searchTerm": "gorpcore", "interestOverTime_timelineData": [
        {"time": "1762646400", "value": [73]}, {"time": "1763251200", "value": [67]}],
        "relatedQueries_rising": [{"query": "quiet luxury", "value": 550}]})
    assert t.points == (("2025-11-09", 73), ("2025-11-16", 67)) and t.rising == (("quiet luxury", 550),)
    assert to_trend({"searchTerm": "x", "interestOverTime_timelineData": []}) is None


@pytest.mark.parametrize("values, stage", [
    ([10] * 44 + [20] * 8, "emerging"),
    ([0] * 40 + [0, 0, 0, 3, 0, 0, 0, 0] + [0, 0, 40, 0], "low_volume"),
    ([4] * 44 + [9] * 8, "emerging"),                 # prior floored at 5 → growth 1.0, not 1.25
    ([40] * 44 + [55] * 8, "rising"),
    ([80] * 44 + [50] * 8, "fading"),
    ([80] * 52, "peak"),
    ([40] * 52, "stable"),
    ([0] * 52, "unknown"),
    ([50] * 5, "unknown"),
])
def test_lifecycle_stages(values, stage):
    assert lifecycle(series(values)[0])["stage"] == stage


def test_lifecycle_floors_the_prior():
    assert lifecycle(series([4] * 44 + [9] * 8)[0])["growth"] == pytest.approx(1.0)


def test_tokens_and_similarity():
    assert tokens("Penny Loafers") == {"penny", "loafer"} and tokens("dress") == {"dress"}
    assert similarity("Old Money", "old money aesthetic") == 1.0 and similarity("a", "") == 0.0


@pytest.mark.parametrize("garment, expected", [
    ("tweed blazer", "blazer"), ("dress shirt", "shirt"), ("satin slip dress", "dress"), ("long-sleeve t-shirt", "t-shirt"),
    ("Chinos", "trouser"), ("pleated wool trousers", "trouser"), ("straight-leg jeans", "jeans"), ("penny loafers", "loafer"),
    ("white leather sneakers", "sneaker"), ("", None),
])
def test_head_noun_with_synonyms(garment, expected):
    assert head(garment) == expected


def test_coverage_matches_head_nouns_once_per_item():
    owned = [{"id": "1", "subtype": "chino trousers"}, {"id": "2", "subtype": "dress shirt"}]
    have, missing = coverage(["oxford shirt", "flannel shirt", "pleated trousers", "slip dress", "tweed blazer"], owned)
    assert [(h["piece"], h["item_id"]) for h in have] == [("oxford shirt", "2"), ("pleated trousers", "1")]
    assert missing == ["flannel shirt", "slip dress", "tweed blazer"]       # shirt used once; dress ≠ dress shirt


# ---------- library ----------
def test_seed_grounds_in_wiki_filters_non_fashion_and_is_idempotent(env):
    env.taste_model.not_fashion = {"Vaporwave"}
    res = env.c.library.seed(["Old Money", "Gorpcore", "Office Siren", "Vaporwave"])
    assert res == {"defined": 3, "grounded_in_wiki": 2}
    env.c.library.seed(["Old Money"])
    styles = {s["name"]: s for s in env.c.library.active()}
    assert set(styles) == {"Old Money", "Gorpcore", "Office Siren"}
    assert styles["Old Money"]["source_url"] == "https://wiki/Old Money" and styles["Office Siren"]["source_url"] is None
    assert styles["Gorpcore"]["search_term"] == "gorpcore aesthetic" and styles["Gorpcore"]["status"] == "active"


def test_seed_batches_requests(env):
    env.c.library.seed([f"S{i}" for i in range(23)])
    assert [len(c) for c in env.aesthetics.calls] == [10, 10, 3]


# ---------- trends ----------
def test_refresh_snapshots_and_sets_lifecycle(env):
    env.c.library.seed(["Old Money", "Gorpcore"])
    env.trends.by_term["gorpcore aesthetic"] = series([40] * 44 + [55] * 8, [("blokecore", 900), ("arcteryx", 300)])
    res = env.c.trends.refresh("CZ")
    assert res["styles"] == 2 and res["stages"] == {"stable": 1, "rising": 1}
    assert env.trends.calls[0][1] == "CZ"
    gorp = next(s for s in env.c.library.active() if s["name"] == "Gorpcore")
    assert gorp["lifecycle"] == "rising" and gorp["trend"]["growth"] > 0.15
    assert len(env.db.tables["style_trend_snapshots"]) == 2
    assert env.c.trends.rising_queries()[0] == {"query": "blokecore", "growth": 900, "near": "Gorpcore"}
    assert [s["name"] for s in env.c.trends.trending()] == ["Gorpcore", "Old Money"]
    assert [s["name"] for s in env.c.trends.trending(stage="rising")] == ["Gorpcore"]


def test_discover_defines_only_new_styles(env):
    env.c.library.seed(["Gorpcore"])
    env.trends.by_term["gorpcore aesthetic"] = series([50] * 52, [("blokecore", 900)])
    env.c.trends.refresh()
    env.taste_model.discover_answer = {"new_styles": [{"name": "Blokecore", "evidence": "+900% next to gorpcore"},
                                                      {"name": "gorpcore", "evidence": "dup"}]}
    out = env.c.trends.discover(5)
    assert [s["name"] for s in out["new_styles"]] == ["Blokecore"]
    blok = next(s for s in env.c.library.active() if s["name"] == "Blokecore")
    assert blok["source"] == "trends_discovery"
    assert "+900% next to gorpcore" in env.taste_model.prompts[-1]          # evidence passed as context


def test_discover_without_snapshots_is_noop(env):
    assert env.c.trends.discover() == {"new_styles": []}


# ---------- style recommendations ----------
def _user_with_wardrobe(env, subtypes):
    uid = env.user()["id"]
    for st in subtypes:
        env.chat.answers["tag"] = {**env.chat.answers["tag"], "subtype": st}
        env.items(uid, 1)
    return uid


def test_recommend_uses_coverage_aspiration_and_penalises_current_style(env):
    env.taste_model.overrides = {
        "Old Money": {"key_pieces": ["oxford shirt", "chinos", "loafers", "cashmere sweater"]},
        "Gorpcore": {"key_pieces": ["fleece", "trail runners", "shell jacket"], "palette": ["neon"]},
        "Preppy": {"key_pieces": ["oxford shirt", "chinos"]}}
    env.c.library.seed(["Old Money", "Gorpcore", "Preppy"])
    uid = _user_with_wardrobe(env, ["Oxford shirt", "chino trousers"])
    env.taste_model.answer = {**env.taste_model.answer,
                              "current_style": {**env.taste_model.answer["current_style"], "style_mix": [{"style": "Preppy", "percent": 100}]},
                              "aspirational_style": {**env.taste_model.answer["aspirational_style"], "style_mix": [{"style": "old money", "percent": 80}]}}
    env.c.taste.build(uid)
    cards = env.c.style_recs.recommend(uid, 3)
    assert cards[0]["name"] == "Old Money"
    assert cards[0]["components"]["coverage"] == 0.5 and cards[0]["missing_pieces"] == ["loafers", "cashmere sweater"]
    assert cards[0]["audience"] == "unisex"
    assert any("own 2 of 4" in r for r in cards[0]["reasons"])
    preppy = next(c for c in cards if c["name"] == "Preppy")
    assert preppy["components"]["already_wears"] == 1.0


def test_recommend_without_taste_profile_falls_back_to_inspirations(env):
    env.c.library.seed(["Old Money", "Gorpcore"])
    uid = env.user()["id"]
    env.c.inspirations.add(uid, [ImageInput(b"look")])            # fake look → style_tags ["old money"]
    assert env.c.style_recs.recommend(uid, 1)[0]["name"] == "Old Money"


def test_audience_filter(env):
    env.taste_model.overrides = {"Mob Wife": {"audience": "womenswear"}, "Black Ivy": {"audience": "menswear"}}
    env.c.library.seed(["Mob Wife", "Black Ivy", "Gorpcore"])
    menswear = env.user(fit_prefs={"audience": "menswear"})["id"]
    anyone = env.user()["id"]
    assert {c["name"] for c in env.c.style_recs.recommend(menswear, 5)} == {"Black Ivy", "Gorpcore"}
    assert len(env.c.style_recs.recommend(anyone, 5)) == 3


def test_rejected_styles_are_excluded(env):
    env.c.library.seed(["Old Money", "Gorpcore"])
    uid = env.user()["id"]
    old = next(s for s in env.c.library.active() if s["name"] == "Old Money")
    env.c.style_recs.feedback(uid, old["id"], interested=False)
    assert [c["name"] for c in env.c.style_recs.recommend(uid, 5)] == ["Gorpcore"]


def test_diversity_penalises_related_styles(env):
    env.taste_model.overrides = {"Old Money": {"related": ["Quiet Luxury"]}, "Quiet Luxury": {"aliases": ["old money"]}}
    env.c.library.seed(["Old Money", "Quiet Luxury", "Gorpcore"])
    uid = env.user()["id"]
    env.c.inspirations.add(uid, [ImageInput(b"look")])            # aspiration → "old money" (both styles match)
    cards = env.c.style_recs.recommend(uid, 3)
    assert [c["name"] for c in cards] == ["Old Money", "Quiet Luxury", "Gorpcore"]
    assert cards[1]["score"] == pytest.approx(cards[0]["score"] - 0.10)   # same base score, minus diversity


def test_feedback_unknown_user(env):
    with pytest.raises(NotFound):
        env.c.style_recs.feedback("nope", "x", True)


# ---------- API ----------
def test_api_library_trends_discover_and_recommendations(client, env):
    job = client.post("/style-library/seed", json={"names": ["Old Money", "Gorpcore"]}).json()
    assert client.get(f"/jobs/{job['job_id']}").json()["result"] == {"defined": 2, "grounded_in_wiki": 2}
    assert len(client.get("/style-library").json()) == 2
    env.trends.by_term["gorpcore aesthetic"] = series([40] * 44 + [55] * 8, [("blokecore", 900)])
    assert client.get(f"/jobs/{client.post('/style-library/trends/refresh', json={}).json()['job_id']}").json()["status"] == "done"
    assert client.get("/style-library/trending?stage=rising").json()[0]["name"] == "Gorpcore"
    assert client.get("/style-library/rising-queries").json()[0]["query"] == "blokecore"
    env.taste_model.discover_answer = {"new_styles": [{"name": "Blokecore", "evidence": "x"}]}
    d = client.get(f"/jobs/{client.post('/style-library/discover', json={'max_new': 2}).json()['job_id']}").json()
    assert d["result"]["new_styles"][0]["name"] == "Blokecore"
    uid = client.post("/users", json={"name": "Dan"}).json()["id"]
    cards = client.get(f"/users/{uid}/style-recommendations?n=2").json()
    assert len(cards) == 2 and {"score", "components", "owned_pieces", "missing_pieces", "reasons"} <= set(cards[0])
    r = client.post(f"/users/{uid}/style-recommendations/{cards[0]['id']}/feedback", json={"interested": False})
    assert r.json() == {"ok": True}
    assert cards[0]["id"] not in {c["id"] for c in client.get(f"/users/{uid}/style-recommendations?n=5").json()}
