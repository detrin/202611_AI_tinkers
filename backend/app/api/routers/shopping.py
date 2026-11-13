from fastapi import APIRouter

from ..deps import Services
from ..schemas import JobRef, LinkIn, ProductFeedbackIn, RecommendationsIn

router = APIRouter(prefix="/users/{uid}", tags=["profile & shopping"])


@router.post("/profile/compute")
def compute_profile(uid: str, c: Services):
    return c.profiles.compute(uid)


@router.get("/profile")
def get_profile(uid: str, c: Services):
    return c.profiles.get(uid)


@router.post("/recommendations", response_model=JobRef)
def create_recommendations(uid: str, body: RecommendationsIn, c: Services):
    queries = c.recommendations.queries_for(uid, body.queries)
    return c.jobs.submit("recommendations", uid, body.model_dump(), lambda: c.recommendations.create(
        uid, queries, body.n, body.per_query, body.marketplaces))


@router.get("/recommendations/{set_id}")
def get_recommendations(uid: str, set_id: str, c: Services):
    return c.recommendations.get(uid, set_id)


@router.post("/products/{product_id}/feedback")
def product_feedback(uid: str, product_id: str, body: ProductFeedbackIn, c: Services):
    return c.feedback.record(uid, product_id, body.liked, body.bought)


@router.post("/links", response_model=JobRef)
def check_link(uid: str, body: LinkIn, c: Services):
    c.links.ensure_user(uid)
    return c.jobs.submit("link_check", uid, body.model_dump(), lambda: c.links.check(uid, body.url))


@router.get("/links")
def list_links(uid: str, c: Services):
    return c.links.list(uid)
