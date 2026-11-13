from fastapi import APIRouter

from ..deps import Services
from ..schemas import ImportIn, JobRef

router = APIRouter(prefix="/users/{uid}/imports", tags=["imports"])


@router.post("", response_model=JobRef)
def create_import(uid: str, body: ImportIn, c: Services):
    """Product page / image URL → wardrobe item; Instagram profile, post or @handle → style profile (+ items)."""
    kind, url = c.imports.prepare(uid, body.url, body.kind)
    work = ((lambda: c.imports.instagram(uid, url, body.max_posts, body.import_items)) if kind == "instagram"
            else (lambda: c.imports.product(uid, url)))
    return c.jobs.submit(f"import_{kind}", uid, body.model_dump() | {"kind": kind, "url": url}, work)


@router.get("")
def list_imports(uid: str, c: Services):
    """Instagram imports (per-post analyses + style profile), newest first."""
    return c.imports.list(uid)
