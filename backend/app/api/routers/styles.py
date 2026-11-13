from fastapi import APIRouter

from ..deps import Services
from ..schemas import JobRef, StylesRefresh, Swipe

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


@router.get("/users/{uid}/swipe-deck")
def swipe_deck(uid: str, c: Services, n: int = 20):
    return c.preferences.deck(uid, n)


@router.post("/users/{uid}/swipes")
def swipes(uid: str, body: list[Swipe], c: Services):
    return {"saved": c.preferences.record(uid, [s.model_dump() for s in body])}
