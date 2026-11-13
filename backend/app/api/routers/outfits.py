from fastapi import APIRouter

from ..deps import Services
from ..schemas import DailyIn, OutfitFeedbackIn

router = APIRouter(prefix="/users/{uid}/outfits", tags=["outfits"])


@router.post("/daily")
def daily(uid: str, body: DailyIn, c: Services):
    return c.outfits.daily(uid, body.event, body.city, body.date)


@router.get("")
def list_outfits(uid: str, c: Services):
    return c.outfits.list(uid)


@router.post("/{outfit_id}/feedback")
def feedback(uid: str, outfit_id: str, body: OutfitFeedbackIn, c: Services):
    return c.outfits.feedback(uid, outfit_id, body.changes())
