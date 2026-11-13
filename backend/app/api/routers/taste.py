from fastapi import APIRouter

from ..deps import Services
from ..schemas import JobRef

router = APIRouter(prefix="/users/{uid}/taste-profile", tags=["taste profile"])


@router.post("", response_model=JobRef)
def build_taste_profile(uid: str, c: Services):
    """Job: gather all evidence → Claude Opus (`claude -p`) → stored taste profile. Takes ~10-60 s."""
    c.taste.ensure_enough(uid)
    return c.jobs.submit("taste_profile", uid, {}, lambda: c.taste.build(uid))


@router.get("")
def get_taste_profile(uid: str, c: Services):
    return c.taste.get(uid)


@router.get("/evidence")
def taste_evidence(uid: str, c: Services):
    """Exactly what would be sent to the model (debugging / notebooks), plus counts."""
    ev = c.taste.evidence(uid)
    return {"counts": c.taste.counts(ev), "evidence": ev}
