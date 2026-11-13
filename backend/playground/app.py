"""Backend playground: poke every endpoint as the seeded test user.

Run (backend must be running):  uv run streamlit run backend/playground/app.py
"""
import datetime as dt
import json

import streamlit as st

from api import Api, test_user_id

st.set_page_config(page_title="Stylist playground", page_icon="🧥", layout="wide")

TEST_UID = test_user_id()
API_PRESETS = ["http://localhost:8000", "https://goodenough.hermandaniel.com/api"]

# ---------------------------------------------------------------- sidebar / session


def api() -> Api:
    if "api" not in st.session_state:
        st.session_state.api = Api(API_PRESETS[0])
    return st.session_state.api


with st.sidebar:
    st.title("🧥 Playground")
    base = st.selectbox("API", API_PRESETS, accept_new_options=True)
    api().base = base
    uid = st.text_input("user_id", value=st.session_state.get("uid", TEST_UID))
    st.session_state.uid = uid
    if uid == TEST_UID:
        st.caption("Shared seeded **test user**. Don't delete its items.")
    allow_destructive = st.toggle("Allow deletes", value=False,
                                  help="Delete buttons stay disabled until this is on.")
    status, health = api().get("/health")
    if status == 200:
        st.success(f"backend up · {base}")
    else:
        st.error(f"backend down: {health}")
    if uid:
        s, u = api().get(f"/users/{uid}")
        if s == 200:
            st.markdown(f"**{u.get('name')}** · {u.get('city') or '–'} · budget {u.get('budget')} {u.get('currency')}")
        else:
            st.warning(f"user not found ({s})")

U = f"/users/{uid}"

# ---------------------------------------------------------------- helpers


def ok(status, body, quiet=False) -> bool:
    """Show errors; returns True on 2xx."""
    if status and 200 <= status < 300:
        return True
    detail = body.get("detail") if isinstance(body, dict) else body
    if not quiet:
        st.error(f"{status or 'no response'}: {detail}")
    return False


def raw(body, label="raw JSON"):
    with st.expander(label):
        st.json(body, expanded=False)


def run_job(status, body) -> dict | None:
    """Poll a job with a live status box; returns the finished job."""
    if not ok(status, body):
        return None
    with st.status(f"job {body['job_id']} queued…", expanded=False) as box:
        job = api().wait_job(body["job_id"],
                             on_tick=lambda j, t: box.update(label=f"job {j['status']} · {t:.0f}s"))
        state = "complete" if job.get("status") == "done" else "error"
        box.update(label=f"job {job.get('status')}", state=state)
        st.json(job, expanded=False)
    if job.get("status") == "failed":
        st.error(job.get("error"))
    return job


def chips(values) -> str:
    return " ".join(f"`{v}`" for v in values or [])


def image(url, **kw):
    if url:
        st.image(url, use_container_width=True, **kw)
    else:
        st.caption("(no image)")


def image_inputs(key: str):
    files = st.file_uploader("photos", accept_multiple_files=True, type=["jpg", "jpeg", "png", "webp"], key=f"{key}_f")
    urls = st.text_area("…or image URLs (one per line)", key=f"{key}_u")
    multipart = [("files", (f.name, f.getvalue(), f.type)) for f in files or []]
    data = {"image_urls": [u.strip() for u in urls.splitlines() if u.strip()]}
    return multipart, data


def grid(rows, render, cols=4):
    for i in range(0, len(rows), cols):
        for col, row in zip(st.columns(cols), rows[i:i + cols]):
            with col, st.container(border=True):
                render(row)


def need_user() -> bool:
    if not uid:
        st.info("Set a user_id in the sidebar.")
        return False
    return True


# ---------------------------------------------------------------- pages


def page_user():
    if not need_user():
        return
    s, user = api().get(U)
    if ok(s, user):
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("Profile")
            st.json(user, expanded=1)
        with c2:
            st.subheader("Edit")
            with st.form("patch_user"):
                name = st.text_input("name", user.get("name") or "")
                city = st.text_input("city", user.get("city") or "")
                budget = st.number_input("budget", value=float(user.get("budget") or 0))
                sizes = st.text_area("sizes (JSON)", json.dumps(user.get("sizes") or {}))
                fit = st.text_area("fit_prefs (JSON)", json.dumps(user.get("fit_prefs") or {}))
                if st.form_submit_button("PATCH user"):
                    body = {"name": name, "city": city, "budget": budget,
                            "sizes": json.loads(sizes or "{}"), "fit_prefs": json.loads(fit or "{}")}
                    s2, b2 = api().patch(U, json=body)
                    if ok(s2, b2):
                        st.success("saved")
                        st.rerun()
            st.subheader("Selfie → colour profile")
            f = st.file_uploader("selfie", type=["jpg", "jpeg", "png", "webp"])
            url = st.text_input("…or selfie image URL")
            if st.button("Analyse selfie", disabled=not (f or url)):
                kw = {"files": [("file", (f.name, f.getvalue(), f.type))]} if f else {"data": {"image_url": url}}
                with st.spinner("vision model…"):
                    s3, b3 = api().post(f"{U}/selfie", **kw)
                if ok(s3, b3):
                    st.json(b3)

    st.divider()
    st.subheader("Create a scratch user (safe place for destructive experiments)")
    with st.form("new_user"):
        c1, c2, c3 = st.columns(3)
        name = c1.text_input("name", "Playground user")
        city = c2.text_input("city", "Prague")
        budget = c3.number_input("budget", value=200.0)
        if st.form_submit_button("POST /users"):
            s, b = api().post("/users", json={"name": name, "city": city, "budget": budget})
            if ok(s, b):
                st.session_state.uid = b["id"]
                st.success(f"created {b['id']}, switched to it")
                st.rerun()


def item_card(item):
    image(item.get("image_url"))
    st.markdown(f"**{item.get('subtype') or item.get('category')}** · {item.get('status')}")
    st.caption(f"{chips(item.get('colors'))} {item.get('material') or ''} · formality {item.get('formality')} · "
               f"warmth {item.get('warmth')} · {item.get('availability') or ''}")
    if item.get("style_tags"):
        st.caption(chips(item["style_tags"]))
    with st.popover("details / edit"):
        if item.get("description"):
            st.write(item["description"])
        st.json(item, expanded=False)
        with st.form(f"edit_{item['id']}"):
            desc = st.text_area("description", item.get("description") or "")
            avail = st.selectbox("availability", ["available", "laundry", "lent", "stored"],
                                 index=["available", "laundry", "lent", "stored"].index(item.get("availability") or "available"))
            tags = st.text_input("style_tags (comma)", ", ".join(item.get("style_tags") or []))
            if st.form_submit_button("PATCH"):
                s, b = api().patch(f"{U}/wardrobe/{item['id']}", json={
                    "description": desc, "availability": avail,
                    "style_tags": [t.strip() for t in tags.split(",") if t.strip()]})
                if ok(s, b):
                    st.rerun()
        c1, c2 = st.columns(2)
        if item.get("status") == "wanted" and c1.button("Mark bought", key=f"buy_{item['id']}"):
            if ok(*api().post(f"{U}/wardrobe/{item['id']}/buy")):
                st.rerun()
        if c2.button("Delete", key=f"del_{item['id']}", disabled=not allow_destructive, type="primary"):
            if ok(*api().delete(f"{U}/wardrobe/{item['id']}")):
                st.rerun()


def page_wardrobe():
    if not need_user():
        return
    c1, c2, c3, c4 = st.columns([1, 1, 1, 1])
    status = c1.segmented_control("status", ["owned", "wanted", "all"], default="owned") or "owned"
    category = c2.text_input("category filter")
    color = c3.text_input("color filter")
    cols = c4.slider("columns", 2, 8, 5)
    params = {"status": status, **({"category": category} if category else {}), **({"color": color} if color else {})}
    s, items = api().get(f"{U}/wardrobe", params=params)
    if ok(s, items):
        st.caption(f"{len(items)} items")
        grid(items, item_card, cols)
        raw(items)

    st.divider()
    st.subheader("Add items")
    files, data = image_inputs("wardrobe")
    add_status = st.radio("as", ["owned", "wanted"], horizontal=True)
    if st.button("Upload + tag", disabled=not (files or data["image_urls"])):
        with st.spinner("vision tagging…"):
            s, b = api().post(f"{U}/wardrobe", files=files or None, data={**data, "status": add_status})
        if ok(s, b):
            st.success(f"added {len(b)}")
            grid(b, item_card, 4)


def page_inspirations():
    if not need_user():
        return
    s, looks = api().get(f"{U}/inspirations")

    def card(look):
        image(look.get("image_url"))
        st.markdown(f"**{look.get('vibe') or ''}** · formality {look.get('formality')}")
        st.caption(chips(look.get("style_tags")))
        st.caption("palette: " + chips(look.get("palette")))
        with st.popover("details"):
            for p in look.get("pieces") or []:
                st.write(f"- {p.get('subtype') or p.get('category')} {chips(p.get('colors'))}")
            st.json(look, expanded=False)
            if st.button("Delete", key=f"dl_{look['id']}", disabled=not allow_destructive, type="primary"):
                if ok(*api().delete(f"{U}/inspirations/{look['id']}")):
                    st.rerun()

    if ok(s, looks):
        st.caption(f"{len(looks)} looks")
        grid(looks, card, 4)
        raw(looks)
    st.divider()
    st.subheader("Add looks")
    files, data = image_inputs("insp")
    if st.button("Upload looks", disabled=not (files or data["image_urls"])):
        with st.spinner("vision tagging…"):
            s, b = api().post(f"{U}/inspirations", files=files or None, data=data)
        if ok(s, b):
            grid(b, card, 4)


def page_imports():
    if not need_user():
        return
    with st.form("import"):
        url = st.text_input("URL", placeholder="product page, image URL, Instagram profile/post or @handle")
        c1, c2, c3 = st.columns(3)
        kind = c1.selectbox("kind", ["auto", "product", "instagram"])
        max_posts = c2.number_input("max_posts (IG)", 1, 30, 12)
        import_items = c3.checkbox("import_items (IG)")
        go = st.form_submit_button("Start import job")
    if go and url:
        job = run_job(*api().post(f"{U}/imports", json={"url": url, "kind": kind, "max_posts": max_posts,
                                                         "import_items": import_items}))
        if job and job.get("status") == "done":
            st.json(job.get("result"))
    st.subheader("Instagram imports")
    s, b = api().get(f"{U}/imports")
    if ok(s, b):
        for imp in b:
            with st.expander(f"{imp.get('created_at', '')[:16]} · {imp.get('source') or imp.get('url') or imp.get('id')}"):
                st.json(imp, expanded=1)


def page_outfits():
    if not need_user():
        return
    with st.form("daily"):
        c1, c2, c3 = st.columns(3)
        event = c1.text_input("event", "office day")
        city = c2.text_input("city (blank = user's)")
        date = c3.date_input("date", dt.date.today())
        go = st.form_submit_button("Suggest outfit")
    if go:
        with st.spinner("styling…"):
            s, o = api().post(f"{U}/outfits/daily", json={"event": event, "city": city or None,
                                                          "date": date.isoformat()})
        if ok(s, o):
            st.session_state.last_outfit = o
    o = st.session_state.get("last_outfit")
    if o:
        show_outfit(o)

    st.divider()
    st.subheader("History")
    s, hist = api().get(f"{U}/outfits")
    if ok(s, hist):
        for h in hist:
            with st.expander(f"{h.get('created_at', '')[:16]} · {h.get('event')} · rating {h.get('rating')}"):
                show_outfit(h)


def show_outfit(o):
    w = o.get("weather") or {}
    if w:
        st.caption(" · ".join(f"{k}: {v}" for k, v in w.items() if not isinstance(v, (dict, list))))
    st.write(o.get("explanation"))
    if o.get("missing_item_tip"):
        st.info(f"Missing: {o['missing_item_tip']}")
    items = o.get("items") or []
    if items:
        for col, it in zip(st.columns(max(len(items), 1)), items):
            with col:
                image(it.get("image_url"))
                st.caption(it.get("subtype") or it.get("category"))
    if o.get("id"):
        with st.form(f"fb_{o['id']}"):
            c1, c2, c3 = st.columns([1, 1, 3])
            worn = c1.checkbox("worn", value=bool(o.get("worn")))
            rating = c2.slider("rating", 1, 5, o.get("rating") or 3)
            comment = c3.text_input("comment", o.get("comment") or "")
            if st.form_submit_button("Send feedback"):
                ok(*api().post(f"{U}/outfits/{o['id']}/feedback",
                               json={"worn": worn, "rating": rating, "comment": comment or None}))
    raw(o)


def page_taste():
    if not need_user():
        return
    c1, c2 = st.columns([1, 1])
    if c1.button("Rebuild taste profile (Opus job, ~10–60 s)"):
        run_job(*api().post(f"{U}/taste-profile"))
    s, tp = api().get(f"{U}/taste-profile")
    if not ok(s, tp):
        return
    p = tp.get("profile") or {}
    st.header(p.get("headline", ""))
    st.caption(f"model {tp.get('model')} · confidence {p.get('confidence')} · evidence {tp.get('evidence_counts')}")
    cur, asp = st.columns(2)
    for col, key, title in ((cur, "current_style", "Current"), (asp, "aspirational_style", "Aspirational")):
        sec = p.get(key) or {}
        with col, st.container(border=True):
            st.subheader(title)
            st.write(sec.get("summary"))
            mix = sec.get("style_mix") or []
            if mix:
                st.bar_chart({m["style"]: m["percent"] for m in mix}, horizontal=True)
            for k in ("palette", "silhouettes", "key_pieces"):
                if sec.get(k):
                    st.markdown(f"**{k}:** {chips(sec[k]) if isinstance(sec[k], list) else sec[k]}")
            st.markdown(f"**formality:** {sec.get('formality_range')}")
    gap = p.get("gap") or {}
    st.subheader("Gap")
    st.write(gap.get("summary"))
    for m in gap.get("moves") or []:
        st.markdown(f"- **{m.get('action')}** — {m.get('why')}")
    c1, c2 = st.columns(2)
    c1.markdown("**wear more:** " + chips((p.get("colors") or {}).get("wear_more")))
    c1.markdown("**avoid colours:** " + chips((p.get("colors") or {}).get("avoid")))
    c2.markdown("**shop queries:** " + chips(p.get("shop_queries")))
    c2.markdown("**missing evidence:** " + chips(p.get("missing_evidence")))
    raw(tp, "full taste profile")
    if c2.button("Load evidence pack (no LLM)"):
        s, ev = api().get(f"{U}/taste-profile/evidence")
        if ok(s, ev):
            st.json(ev["counts"])
            raw(ev["evidence"], "evidence")


def page_styles():
    t1, t2, t3, t4, t5, t6 = st.tabs(["Swipe deck", "Style beliefs", "Boards", "Pinterest styles",
                                      "Style library & trends", "Style recs"])
    with t1:
        if need_user():
            swipe_deck()
    with t2:
        if need_user():
            style_beliefs()
    with t3:
        if need_user():
            swipe_boards()
    with t4:
        s, styles = api().get("/styles")
        if ok(s, styles):
            names = {f"{x.get('name')} ({x.get('id', '')[:8]})": x["id"] for x in styles}
            pick = st.selectbox("style", list(names)) if names else None
            if pick:
                s, st_ = api().get(f"/styles/{names[pick]}")
                if ok(s, st_):
                    st.write(st_.get("summary") or st_.get("description"))
                    grid(st_.get("pins") or [], lambda p: image(p.get("image_url"), caption=p.get("title")), 6)
                    raw(st_)
        c1, c2 = st.columns(2)
        with c1, st.form("refresh_styles"):
            q = st.text_input("queries (comma)", "old money outfit, gorpcore outfit")
            n = st.number_input("pins_per_style", 1, 50, 12)
            if st.form_submit_button("Refresh styles (Apify job, 1–3 min)"):
                run_job(*api().post("/styles/refresh", json={"queries": [x.strip() for x in q.split(",") if x.strip()],
                                                             "pins_per_style": n}))
        with c2, st.form("fill_pins"):
            per = st.number_input("per_style", 1, 50, 12)
            only_missing = st.checkbox("only_missing", value=True)
            if st.form_submit_button("Fill pins for library styles (paid Apify job)"):
                run_job(*api().post("/styles/pins/fill", json={"per_style": per, "only_missing": only_missing}))
    with t5:
        style_library()
    with t6:
        if need_user():
            n = st.slider("n", 1, 15, 5)
            s, recs = api().get(f"{U}/style-recommendations", params={"n": n})
            if ok(s, recs):
                for r in recs if isinstance(recs, list) else recs.get("recommendations", []):
                    style = r.get("style") or r
                    with st.container(border=True):
                        st.markdown(f"**{style.get('name')}** · score {r.get('score')} · {style.get('lifecycle', '')}")
                        st.write(r.get("reason") or style.get("definition"))
                        c1, c2, _ = st.columns([1, 1, 6])
                        sid = style.get("id") or r.get("style_id")
                        if c1.button("👍", key=f"si_{sid}"):
                            ok(*api().post(f"{U}/style-recommendations/{sid}/feedback", json={"interested": True}))
                        if c2.button("👎", key=f"sn_{sid}"):
                            ok(*api().post(f"{U}/style-recommendations/{sid}/feedback", json={"interested": False}))
                raw(recs)
            st.divider()
            st.subheader("Next styles (pins tuned for the recommendation page)")
            st.caption("⚠️ Pins served here are marked seen for this user and won't come back.")
            c1, c2 = st.columns(2)
            k = c1.slider("k", 1, 20, 6)
            ex = c2.slider("explore ", 0.0, 1.0, 0.2, 0.05)
            if st.button("Deal next styles"):
                s, nxt = api().get(f"{U}/next-styles", params={"k": k, "explore": ex})
                if ok(s, nxt):
                    st.session_state.next_styles = nxt
            nxt = st.session_state.get("next_styles") or []
            grid(nxt, lambda p: pin_card(p, source="recommendations"), 6)


def pin_meta(pin):
    mode = pin.get("mode")
    badge = {"explore": "🧭 explore", "exploit": "🎯 exploit"}.get(mode, mode or "")
    st.markdown(f"**{pin.get('style_name') or pin.get('style_id')}** · {badge}")
    bits = [f"p_like {pin['p_like']:.2f}" if isinstance(pin.get("p_like"), (int, float)) else None,
            f"± {pin['uncertainty']:.2f}" if isinstance(pin.get("uncertainty"), (int, float)) else None]
    if any(bits):
        st.caption(" ".join(b for b in bits if b))
    if pin.get("reason"):
        st.caption(pin["reason"])


def pin_card(pin, source="deck"):
    image(pin.get("image_url"))
    pin_meta(pin)
    c1, c2 = st.columns(2)
    if c1.button("👍", key=f"pl_{source}_{pin['id']}"):
        ok(*api().post(f"{U}/swipes", json=[{"pin_id": pin["id"], "liked": True, "source": source}]))
    if c2.button("👎", key=f"pd_{source}_{pin['id']}"):
        ok(*api().post(f"{U}/swipes", json=[{"pin_id": pin["id"], "liked": False, "source": source}]))


def swipe_deck():
    st.caption("⚠️ Every pin the deck serves is marked seen for this user and is never served again. "
               "On the shared test user that uses up its deck for everyone, so deal small batches or use a scratch user.")
    c1, c2, c3, c4 = st.columns([2, 1, 1, 1])
    explore = c1.slider("explore (share of slots spent learning taste)", 0.0, 1.0, 0.5, 0.05)
    n = c2.number_input("n", 1, 100, 8)
    seed = c3.text_input("seed (optional)")
    c4.write("")
    if c4.button("Deal pins", type="primary", use_container_width=True):
        params = {"n": n, "explore": explore, **({"seed": int(seed)} if seed.strip().isdigit() else {})}
        s, deck = api().get(f"{U}/swipe-deck", params=params)
        st.session_state.deck = {"uid": uid, "pins": deck if ok(s, deck) else []}
    state = st.session_state.get("deck")
    deck = state["pins"] if state and state.get("uid") == uid else []
    if not deck:
        st.info("No pins dealt yet. Press **Deal pins**. An empty result means no unseen pins are left (fill pins on the Pinterest styles tab).")
        return
    pin = deck[0]
    c1, c2 = st.columns([2, 3])
    with c1:
        image(pin.get("image_url"))
    with c2:
        pin_meta(pin)
        st.write(pin.get("title") or "")
        modes = [p.get("mode") for p in deck]
        st.caption(f"{len(deck)} left in this batch · {modes.count('explore')} explore / {modes.count('exploit')} exploit")
        b1, b2, b3 = st.columns(3)
        for col, label, liked in ((b1, "👎 nope", False), (b2, "👍 like", True)):
            if col.button(label, use_container_width=True):
                ok(*api().post(f"{U}/swipes", json=[{"pin_id": pin["id"], "liked": liked, "source": "deck"}]))
                deck.pop(0)
                st.rerun()
        if b3.button("⭐ save as inspiration", use_container_width=True):
            ok(*api().post(f"{U}/inspirations/from-pin", json={"pin_id": pin["id"]}))
            deck.pop(0)
            st.rerun()
        raw(pin, "pin")


def style_beliefs():
    s, beliefs = api().get(f"{U}/style-beliefs")
    if not ok(s, beliefs):
        return
    st.caption("The model's per-style belief that this user likes it. The prior comes from the evidence listed in prior_from; swipes update it.")
    rows = [{"style": b.get("name"), "p_like": b.get("p_like"), "uncertainty": b.get("uncertainty"),
             "likes": b.get("likes"), "dislikes": b.get("dislikes"), "prior": b.get("prior"),
             "unseen_pins": b.get("unseen_pins"), "prior_from": ", ".join(b.get("prior_from") or [])} for b in beliefs]
    st.dataframe(rows, use_container_width=True, hide_index=True, column_config={
        "p_like": st.column_config.ProgressColumn("p_like", min_value=0, max_value=1, format="%.2f"),
        "prior": st.column_config.ProgressColumn("prior", min_value=0, max_value=1, format="%.2f"),
        "uncertainty": st.column_config.NumberColumn(format="%.3f")})
    raw(beliefs)


def swipe_boards():
    which = st.segmented_control("board", ["interested", "not interested", "all"], default="interested") or "interested"
    params = {"interested": {"liked": "true"}, "not interested": {"liked": "false"}}.get(which, {})
    s, board = api().get(f"{U}/swipes", params=params)
    if not ok(s, board):
        return
    st.caption(f"{len(board)} swipes")

    def card(r):
        image(r.get("image_url"))
        st.markdown(f"{'👍' if r.get('liked') else '👎'} **{r.get('style_name') or ''}**")
        st.caption(f"{r.get('mode') or ''} · {r.get('source') or ''} · {(r.get('created_at') or '')[:16]}")

    grid(board, card, 6)
    raw(board)


def style_library():
    c1, c2, c3 = st.columns(3)
    with c1.popover("Seed library (Opus job)"):
        names = st.text_input("names (comma, blank = built-in ~40)")
        if st.button("Run seed"):
            run_job(*api().post("/style-library/seed", json={"names": [n.strip() for n in names.split(",") if n.strip()] or None}))
    with c2.popover("Refresh trends (Apify job)"):
        geo = st.text_input("geo (ISO, blank = worldwide)")
        if st.button("Run trends refresh"):
            run_job(*api().post("/style-library/trends/refresh", json={"geo": geo}))
    with c3.popover("Discover new styles (job)"):
        mx = st.number_input("max_new", 1, 20, 5)
        if st.button("Run discover"):
            run_job(*api().post("/style-library/discover", json={"max_new": mx}))
    view = st.segmented_control("view", ["library", "trending", "rising queries"], default="library") or "library"
    if view == "library":
        s, lib = api().get("/style-library")
        if ok(s, lib):
            st.caption(f"{len(lib)} active styles")
            q = st.text_input("filter")
            for x in lib:
                if q and q.lower() not in json.dumps(x).lower():
                    continue
                with st.expander(f"{x.get('name')} · {x.get('lifecycle') or '–'}"):
                    st.write(x.get("definition"))
                    st.markdown("**key pieces:** " + chips(x.get("key_pieces")))
                    st.markdown("**palette:** " + chips(x.get("palette")))
                    st.json(x, expanded=False)
    elif view == "trending":
        stage = st.selectbox("stage", ["", "emerging", "rising", "peak", "declining", "stable"])
        s, tr = api().get("/style-library/trending", params={"limit": 50, **({"stage": stage} if stage else {})})
        if ok(s, tr):
            st.dataframe(tr, use_container_width=True)
    else:
        s, rq = api().get("/style-library/rising-queries", params={"limit": 100})
        if ok(s, rq):
            st.dataframe(rq, use_container_width=True)


def page_shopping():
    if not need_user():
        return
    t1, t2, t3 = st.tabs(["Profile", "Recommendations", "Check a link"])
    with t1:
        if st.button("Compute profile (LLM)"):
            with st.spinner("computing…"):
                ok(*api().post(f"{U}/profile/compute"))
        s, p = api().get(f"{U}/profile")
        if ok(s, p, quiet=s == 404):
            st.write(p.get("taste_summary"))
            if p.get("style_mix"):
                st.bar_chart({m["style"]: m["percent"] for m in p["style_mix"]}, horizontal=True)
            for g in p.get("gaps") or []:
                st.markdown(f"- **{g.get('item')}** — {g.get('why')}")
            st.markdown("**queries:** " + chips(p.get("queries")))
            raw(p)
        elif s == 404:
            st.info("No profile yet.")
    with t2:
        with st.form("recs"):
            c1, c2, c3 = st.columns(3)
            n = c1.number_input("n", 1, 20, 5)
            per_q = c2.number_input("per_query", 1, 30, 6)
            mk = c3.text_input("marketplaces (comma)", "www.etsy.com")
            queries = st.text_input("queries (comma, blank = from profile)")
            go = st.form_submit_button("Get recommendations (Apify job, 1–3 min)")
        if go:
            job = run_job(*api().post(f"{U}/recommendations", json={
                "n": n, "per_query": per_q, "marketplaces": [m.strip() for m in mk.split(",") if m.strip()],
                "queries": [q.strip() for q in queries.split(",") if q.strip()] or None}))
            if job and job.get("status") == "done":
                st.session_state.rec_set = job["result"]["rec_set_id"]
        set_id = st.text_input("rec_set_id", st.session_state.get("rec_set", ""))
        if set_id:
            s, recs = api().get(f"{U}/recommendations/{set_id}")
            if ok(s, recs):
                grid(recs, rec_card, 4)
                raw(recs)
    with t3:
        url = st.text_input("product URL")
        if st.button("Check link (job)", disabled=not url):
            job = run_job(*api().post(f"{U}/links", json={"url": url}))
            if job and job.get("status") == "done":
                st.json(job.get("result"))
        s, links = api().get(f"{U}/links")
        if ok(s, links):
            st.subheader("History")
            for ln in links:
                with st.expander(f"{ln.get('score_1to10', '?')}/10 · {ln.get('url') or ln.get('id')}"):
                    st.json(ln, expanded=1)


def rec_card(r):
    pr = r.get("products") or {}
    image(pr.get("image_url"))
    st.markdown(f"**#{r.get('rank')} [{pr.get('name', '')[:60]}]({pr.get('url')})**  \n{pr.get('price')} {pr.get('currency') or ''}")
    st.caption(r.get("reason"))
    c1, c2, c3 = st.columns(3)
    pid = pr.get("id")
    if c1.button("👍", key=f"pl_{pid}"):
        ok(*api().post(f"{U}/products/{pid}/feedback", json={"liked": True}))
    if c2.button("👎", key=f"pd_{pid}"):
        ok(*api().post(f"{U}/products/{pid}/feedback", json={"liked": False}))
    if c3.button("bought", key=f"pb_{pid}"):
        ok(*api().post(f"{U}/products/{pid}/feedback", json={"bought": True}))


def page_raw():
    st.caption("Any endpoint. `{uid}` in the path is replaced with the sidebar user. Swagger: "
               f"[{api().base}/docs]({api().base}/docs)")
    c1, c2 = st.columns([1, 5])
    method = c1.selectbox("method", ["GET", "POST", "PATCH", "DELETE"])
    path = c2.text_input("path", "/users/{uid}/wardrobe?status=all")
    body = st.text_area("JSON body", "", height=150)
    if method == "DELETE" and not allow_destructive:
        st.warning("Turn on 'Allow deletes' in the sidebar.")
    if st.button("Send", type="primary", disabled=method == "DELETE" and not allow_destructive):
        kw = {"json": json.loads(body)} if body.strip() else {}
        s, b = api().request(method, path.replace("{uid}", uid), **kw)
        st.markdown(f"**{s}**")
        if isinstance(b, dict) and "job_id" in b and st.session_state.get("autopoll", True):
            run_job(s, b)
        else:
            st.json(b) if isinstance(b, (dict, list)) else st.code(b)
    st.checkbox("auto-poll jobs", value=True, key="autopoll")
    c1, c2 = st.columns([3, 1])
    job_id = c1.text_input("poll a job_id")
    if c2.button("Poll", disabled=not job_id):
        run_job(202, {"job_id": job_id})


def page_log():
    log = api().log
    if st.button("Clear"):
        log.clear()
    for c in log:
        icon = "✅" if c.status and c.status < 300 else "❌"
        with st.expander(f"{icon} {c.method} {c.path} → {c.status} · {c.ms} ms"):
            st.markdown("request")
            st.json(c.request, expanded=False)
            st.markdown("response")
            st.json(c.response, expanded=False) if isinstance(c.response, (dict, list)) else st.code(str(c.response))


pg = st.navigation([
    st.Page(page_user, title="User", icon="👤", default=True),
    st.Page(page_wardrobe, title="Wardrobe", icon="👕", url_path="wardrobe"),
    st.Page(page_inspirations, title="Inspirations", icon="✨", url_path="inspirations"),
    st.Page(page_imports, title="Imports", icon="📥", url_path="imports"),
    st.Page(page_outfits, title="Daily outfit", icon="🌤️", url_path="outfits"),
    st.Page(page_taste, title="Taste profile", icon="🧠", url_path="taste"),
    st.Page(page_styles, title="Styles & swipes", icon="🎨", url_path="styles"),
    st.Page(page_shopping, title="Shopping", icon="🛍️", url_path="shopping"),
    st.Page(page_raw, title="Raw request", icon="🔧", url_path="raw"),
    st.Page(page_log, title="Request log", icon="📜", url_path="log"),
])
pg.run()
