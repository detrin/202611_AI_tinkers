from secrets import compare_digest
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException

from ..deps import Services
from ..schemas import DailyIn, OutfitFeedbackIn, TodayIn

router = APIRouter(prefix="/users/{uid}/outfits", tags=["outfits"])


@router.post("/daily")
def daily(uid: str, body: DailyIn, c: Services):
    return c.outfits.daily(uid, body.event, body.city, body.date)


@router.post("/today")
async def today(uid: str, body: TodayIn, c: Services, authorization: Annotated[str | None, Header()] = None):
    if not c.today_api_token:
        raise HTTPException(status_code=503, detail="Today is not configured")
    expected = f"Bearer {c.today_api_token}".encode()
    if not compare_digest((authorization or "").encode(), expected):
        raise HTTPException(status_code=401, detail="Invalid credentials", headers={"WWW-Authenticate": "Bearer"})
    return await c.today.today(uid, body.date, body.note)


@router.get("")
def list_outfits(uid: str, c: Services):
    return c.outfits.list(uid)


@router.post("/{outfit_id}/feedback")
def feedback(uid: str, outfit_id: str, body: OutfitFeedbackIn, c: Services):
    return c.outfits.feedback(uid, outfit_id, body.changes())
