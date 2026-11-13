from fastapi import APIRouter, File, Form, UploadFile

from ...services.good_enough import Location
from ..deps import Services
from .users import collect_images

router = APIRouter(prefix="/users/{uid}", tags=["good-enough"])


@router.post("/is-it-good-enough")
async def is_it_good_enough(
    uid: str, c: Services,
    file: UploadFile | None = File(None), image_url: str | None = Form(None),
    latitude: float | None = Form(None, ge=-90, le=90), longitude: float | None = Form(None, ge=-180, le=180),
    city: str | None = Form(None), use_saved_city: bool = Form(False),
    include_wardrobe: bool = Form(False), occasion: str | None = Form(None, max_length=300),
):
    """Photo of the current look → `verdict` "hell yeah" | "hell nah" + `explanation`.

    Weather is fetched only when a location is attached: `latitude`+`longitude` (current position) win over
    `city`; `use_saved_city=true` falls back to the user's saved city. No location → `weather: null`.
    `include_wardrobe=true` opts in to wardrobe context (enables `swap_item_ids`); off by default."""
    image = (await collect_images(c.images, [file] if file else None, [image_url] if image_url else None))[0]
    return c.good_enough.check(uid, image, Location(latitude, longitude, city), use_saved_city,
                               include_wardrobe, occasion)
