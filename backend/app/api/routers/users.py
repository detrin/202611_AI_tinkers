from fastapi import APIRouter, File, Form, UploadFile

from ...domain import ImageInput
from ...errors import Invalid
from ...services.images import ImageService
from ..deps import Services
from ..schemas import UserIn, UserPatch

router = APIRouter(prefix="/users", tags=["users"])


async def collect_images(images: ImageService, files: list[UploadFile] | None, urls: list[str] | None) -> list[ImageInput]:
    """Shared by every upload endpoint: multipart files and/or image URLs → ImageInput list."""
    out = [ImageInput(await f.read(), f.content_type or "image/jpeg") for f in files or []]
    out += [images.from_url(u) for u in urls or []]
    if not out:
        raise Invalid("Provide files or image_urls")
    return out


@router.post("")
def create_user(body: UserIn, c: Services):
    return c.users.create(body.model_dump())


@router.get("")
def list_users(c: Services, name: str | None = None, limit: int = 50):
    """Newest first, compact rows. `?name=` filters by case-insensitive substring."""
    return c.users.list(name, limit)


@router.get("/test-user")
def test_user(c: Services):
    """The seeded test user (latest 'Test User (seed)'): use its `id` as the default user in UIs."""
    return c.users.test_user()


@router.get("/demo-user")
def demo_user(c: Services):
    """The demo user (latest 'Demo User'): real photos of owned clothes. Use its `id` for demos."""
    return c.users.demo_user()


@router.get("/{uid}")
def get_user(uid: str, c: Services):
    return c.users.get(uid)


@router.patch("/{uid}")
def update_user(uid: str, body: UserPatch, c: Services):
    return c.users.update(uid, body.changes())


@router.post("/{uid}/selfie")
async def selfie(uid: str, c: Services, file: UploadFile | None = File(None), image_url: str | None = Form(None)):
    image = (await collect_images(c.images, [file] if file else None, [image_url] if image_url else None))[0]
    return c.users.analyse_selfie(uid, image)
