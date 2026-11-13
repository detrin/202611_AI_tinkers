"""Request bodies (pydantic). Responses are plain rows from the services."""
import datetime as dt

from pydantic import BaseModel, Field


class Patch(BaseModel):
    def changes(self) -> dict:
        return self.model_dump(exclude_none=True)


class UserIn(BaseModel):
    name: str
    city: str | None = None
    budget: float | None = None
    currency: str = "EUR"
    fit_prefs: dict = {}
    sizes: dict = {}


class UserPatch(Patch):
    name: str | None = None
    city: str | None = None
    budget: float | None = None
    currency: str | None = None
    fit_prefs: dict | None = None
    sizes: dict | None = None


class ItemPatch(Patch):
    category: str | None = None
    subtype: str | None = None
    colors: list[str] | None = None
    pattern: str | None = None
    material: str | None = None
    formality: int | None = Field(None, ge=1, le=5)
    warmth: int | None = Field(None, ge=1, le=5)
    style_tags: list[str] | None = None


class StylesRefresh(BaseModel):
    queries: list[str] = Field(min_length=1)
    pins_per_style: int = Field(12, ge=1, le=50)


class Swipe(BaseModel):
    pin_id: str
    liked: bool


class RecommendationsIn(BaseModel):
    n: int = Field(5, ge=1, le=20)
    per_query: int = Field(6, ge=1, le=30)
    marketplaces: list[str] = ["www.etsy.com"]
    queries: list[str] | None = None


class ProductFeedbackIn(BaseModel):
    liked: bool | None = None
    bought: bool = False


class LinkIn(BaseModel):
    url: str


class DailyIn(BaseModel):
    event: str = "casual day"
    city: str | None = None
    date: dt.date | None = None


class OutfitFeedbackIn(Patch):
    worn: bool | None = None
    rating: int | None = Field(None, ge=1, le=5)
    comment: str | None = None


class JobRef(BaseModel):
    job_id: str
    status: str
