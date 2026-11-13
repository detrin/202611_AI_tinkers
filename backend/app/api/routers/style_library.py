"""Style library (grounded definitions), trends (lifecycle + discovery) and personal style recommendations."""
from fastapi import APIRouter
from pydantic import BaseModel, Field

from ..deps import Services
from ..schemas import JobRef

router = APIRouter(tags=["style library & trends"])


class SeedIn(BaseModel):
    names: list[str] | None = Field(None, description="style names to define; default: built-in seed list (~40)")


class TrendsIn(BaseModel):
    geo: str = Field("", description="ISO country code, '' = worldwide")


class DiscoverIn(BaseModel):
    max_new: int = Field(5, ge=1, le=20)


class StyleFeedbackIn(BaseModel):
    interested: bool


@router.get("/style-library")
def library(c: Services):
    return c.library.active()


@router.post("/style-library/seed", response_model=JobRef)
def seed(body: SeedIn, c: Services):
    """Job: Aesthetics Wiki pages → Opus → normalised style records (upsert by name)."""
    return c.jobs.submit("style_library_seed", None, body.model_dump(), lambda: c.library.seed(body.names))


@router.post("/style-library/trends/refresh", response_model=JobRef)
def refresh_trends(body: TrendsIn, c: Services):
    """Job: Google Trends (12 months, weekly) for every active style → lifecycle stage + snapshot."""
    return c.jobs.submit("style_trends_refresh", None, body.model_dump(), lambda: c.trends.refresh(body.geo))


@router.post("/style-library/discover", response_model=JobRef)
def discover(body: DiscoverIn, c: Services):
    """Job: rising related queries from the latest snapshots → Opus picks new style names → defined + added."""
    return c.jobs.submit("style_discover", None, body.model_dump(), lambda: c.trends.discover(body.max_new))


@router.get("/style-library/trending")
def trending(c: Services, stage: str | None = None, limit: int = 20):
    return c.trends.trending(stage, limit)


@router.get("/style-library/rising-queries")
def rising_queries(c: Services, limit: int = 50):
    return c.trends.rising_queries()[:limit]


@router.get("/users/{uid}/style-recommendations")
def style_recommendations(uid: str, c: Services, n: int = 5):
    return c.style_recs.recommend(uid, n)


@router.post("/users/{uid}/style-recommendations/{style_id}/feedback")
def style_feedback(uid: str, style_id: str, body: StyleFeedbackIn, c: Services):
    return c.style_recs.feedback(uid, style_id, body.interested)
