from fastapi import APIRouter, Query

from ..deps import Services
from ..schemas import JobRef, PinsFill, StylesRefresh, Swipe

router = APIRouter(tags=["styles"])


@router.get("/styles")
def list_styles(c: Services):
    return c.styles.list()


@router.get("/styles/{style_id}")
def get_style(style_id: str, c: Services):
    return c.styles.get(style_id)


@router.post("/styles/refresh", response_model=JobRef)
def refresh_styles(body: StylesRefresh, c: Services):
    return c.jobs.submit("styles_refresh", None, body.model_dump(),
                         lambda: c.styles.refresh(body.queries, body.pins_per_style))


@router.post("/styles/pins/fill", response_model=JobRef)
def fill_pins(body: PinsFill, c: Services):
    """Job: Pinterest pins for the existing (library) styles, so the swipe deck has images to serve."""
    return c.jobs.submit("style_pins_fill", None, body.model_dump(),
                         lambda: c.styles.fill_pins(body.per_style, body.only_missing, body.style_ids))


@router.get("/users/{uid}/swipe-deck")
def swipe_deck(uid: str, c: Services, n: int = Query(20, ge=1, le=100),
               explore: float = Query(0.5, ge=0, le=1, description="share of slots spent learning the user's taste"),
               seed: int | None = None):
    """Next unseen pins: each is `explore` (style we know least about) or `exploit` (most likely liked).
    Served pins are marked seen. Each pin: id, image_url, title, style_id, style_name, mode, p_like, reason."""
    return c.preferences.deck(uid, n, explore, seed)


@router.get("/users/{uid}/next-styles")
def next_styles(uid: str, c: Services, k: int = Query(6, ge=1, le=50), explore: float = Query(0.2, ge=0, le=1),
                seed: int | None = None):
    """Same as swipe-deck, tuned for the recommendation page (mostly exploit)."""
    return c.preferences.deck(uid, k, explore, seed)


@router.get("/users/{uid}/style-beliefs")
def style_beliefs(uid: str, c: Services):
    """Per-style p(like), uncertainty, swipe counts and what the prior came from."""
    return c.preferences.beliefs(uid)


@router.post("/users/{uid}/swipes")
def swipes(uid: str, body: list[Swipe], c: Services):
    return {"saved": c.preferences.record(uid, [s.model_dump() for s in body])}


@router.get("/users/{uid}/swipes")
def swipe_board(uid: str, c: Services, liked: bool | None = None):
    """liked=true: "interested" board, liked=false: "not interested", omitted: both. Not part of the wardrobe."""
    return c.preferences.board(uid, liked)
