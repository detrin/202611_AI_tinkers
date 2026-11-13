import datetime as dt

from fastapi import APIRouter

from ..deps import Services

router = APIRouter(tags=["system"])


@router.get("/health")
def health():
    return {"ok": True}


@router.get("/jobs/{job_id}")
def get_job(job_id: str, c: Services):
    return c.jobs.get(job_id)


@router.get("/weather")
def weather(city: str, c: Services, date: dt.date | None = None):
    return c.weather.daily(city, date)
