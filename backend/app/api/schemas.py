"""Request bodies (pydantic). Responses are plain rows from the services."""
import datetime as dt
from typing import Literal

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


ItemStatus = Literal["owned", "wanted"]


class ItemPatch(Patch):
    status: ItemStatus | None = None
    category: str | None = None
    subtype: str | None = None
    colors: list[str] | None = None
    pattern: str | None = None
    material: str | None = None
    fit: str | None = None
    description: str | None = Field(None, max_length=1000)
    formality: int | None = Field(None, ge=1, le=5)
    warmth: int | None = Field(None, ge=1, le=5)
    style_tags: list[str] | None = None
    availability: Literal["available", "laundry", "lent", "stored"] | None = None


class FromPin(BaseModel):
    pin_id: str


class StylesRefresh(BaseModel):
    queries: list[str] = Field(min_length=1)
    pins_per_style: int = Field(12, ge=1, le=50)


class PinsFill(BaseModel):
    per_style: int = Field(12, ge=1, le=50)
    only_missing: bool = True
    style_ids: list[str] | None = None


class Swipe(BaseModel):
    pin_id: str
    liked: bool
    source: Literal["deck", "recommendations"] | None = Field(None, description="where it was swiped; default deck")


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


class ImportIn(BaseModel):
    url: str = Field(description="Product page URL, direct image URL, Instagram profile/post URL or @handle")
    kind: Literal["auto", "product", "instagram"] = "auto"
    max_posts: int = Field(12, ge=1, le=30, description="Instagram only")
    import_items: bool = Field(False, description="Instagram only: also add detected garments to the wardrobe")


class DailyIn(BaseModel):
    event: str = "casual day"
    city: str | None = None
    date: dt.date | None = None


class TodayIn(BaseModel):
    date: dt.date | None = None
    note: str | None = Field(None, max_length=500)


class OutfitFeedbackIn(Patch):
    worn: bool | None = None
    rating: int | None = Field(None, ge=1, le=5)
    comment: str | None = None


class JobRef(BaseModel):
    job_id: str
    status: str
