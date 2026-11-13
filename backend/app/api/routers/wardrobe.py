from fastapi import APIRouter, File, Form, UploadFile

from ..deps import Services
from ..schemas import ItemPatch
from .users import collect_images

router = APIRouter(prefix="/users/{uid}/wardrobe", tags=["wardrobe"])


@router.post("")
async def add_items(uid: str, c: Services, files: list[UploadFile] | None = File(None),
                    image_urls: list[str] | None = Form(None)):
    return c.wardrobe.add(uid, await collect_images(c.images, files, image_urls))


@router.get("")
def list_items(uid: str, c: Services, category: str | None = None, color: str | None = None):
    return c.wardrobe.list(uid, category, color)


@router.get("/{item_id}")
def get_item(uid: str, item_id: str, c: Services):
    return c.wardrobe.get(uid, item_id)


@router.patch("/{item_id}")
def update_item(uid: str, item_id: str, body: ItemPatch, c: Services):
    return c.wardrobe.update(uid, item_id, body.changes())


@router.delete("/{item_id}")
def delete_item(uid: str, item_id: str, c: Services):
    c.wardrobe.delete(uid, item_id)
    return {"deleted": item_id}
