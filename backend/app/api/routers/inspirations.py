from fastapi import APIRouter, File, Form, UploadFile

from ..deps import Services
from ..schemas import FromPin
from .users import collect_images

router = APIRouter(prefix="/users/{uid}/inspirations", tags=["inspirations"])


@router.post("")
async def add_looks(uid: str, c: Services, files: list[UploadFile] | None = File(None),
                    image_urls: list[str] | None = Form(None)):
    """Whole-look photos (street style, screenshots, pins by URL) → tagged looks."""
    return c.inspirations.add(uid, await collect_images(c.images, files, image_urls))


@router.post("/from-pin")
def from_pin(uid: str, body: FromPin, c: Services):
    """Promote a swipe-deck pin to inspiration (also records a like)."""
    return c.inspirations.from_pin(uid, body.pin_id)


@router.get("")
def list_looks(uid: str, c: Services):
    return c.inspirations.list(uid)


@router.get("/{inspiration_id}")
def get_look(uid: str, inspiration_id: str, c: Services):
    return c.inspirations.get(uid, inspiration_id)


@router.delete("/{inspiration_id}")
def delete_look(uid: str, inspiration_id: str, c: Services):
    c.inspirations.delete(uid, inspiration_id)
    return {"deleted": inspiration_id}
