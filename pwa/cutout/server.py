# /// script
# requires-python = ">=3.11,<3.13"
# dependencies = ["rembg[cpu]", "pillow", "numpy", "scipy", "fastapi", "uvicorn", "python-multipart"]
# ///
"""Cuts the garment out of a photo and returns a transparent PNG.

    uv run pwa/cutout/server.py          # http://localhost:8010, first start downloads two models (~350 MB)

POST /cutout (multipart `file`) -> image/png. The PWA calls this before it uploads a wardrobe photo, so the
closet and the outfit board show the garment alone: no person, no room.

How: a clothing segmentation model (u2net_cloth_seg) finds upper-body, lower-body and full-body garments, and the
largest one is kept. If it finds no clothing (shoes, bags, a flat product shot it does not recognise), a general
background-removal model is used instead. Runs on CPU in about a second per photo.
"""
import io

import numpy as np
import uvicorn
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import Response
from PIL import Image, ImageOps
from rembg import new_session, remove
from scipy import ndimage

MAX_INPUT, MAX_OUTPUT = 1024, 720
MIN_CLOTH_COVERAGE = 0.03   # below this share of the photo, the clothing model found nothing usable
DOUBT_COVERAGE = 0.25       # below this, double-check against plain background removal

cloth = new_session("u2net_cloth_seg")
general = new_session("isnet-general-use")
app = FastAPI(title="Garment cutout")


def clean(alpha: np.ndarray) -> np.ndarray:
    """Keep the main blob and anything at least a tenth of its size; drops stray specks."""
    labels, n = ndimage.label(alpha > 128)
    if n <= 1:
        return alpha
    sizes = ndimage.sum(alpha > 128, labels, range(1, n + 1))
    keep = np.isin(labels, [i + 1 for i, s in enumerate(sizes) if s >= sizes.max() * 0.1])
    return np.where(keep, alpha, 0).astype(np.uint8)


def cut(image: Image.Image) -> tuple[Image.Image, str]:
    image = ImageOps.exif_transpose(image).convert("RGB")
    image.thumbnail((MAX_INPUT, MAX_INPUT))
    stacked = remove(image, session=cloth)                       # upper, lower, full: stacked top to bottom
    panels = [np.asarray(stacked.crop((0, i * image.height, image.width, (i + 1) * image.height)))[..., 3]
              for i in range(3)]
    alpha = max(panels, key=lambda a: (a > 128).mean())
    method = "clothing"
    coverage = (alpha > 128).mean()
    if coverage < DOUBT_COVERAGE:
        # Small result: either there is no clothing (shoes, bags) or the model only caught a fragment of a
        # close-up. Compare with plain background removal and prefer it when it kept far more of the subject.
        whole = np.asarray(remove(image, session=general))[..., 3]
        if coverage < MIN_CLOTH_COVERAGE or coverage < 0.4 * (whole > 128).mean():
            alpha, method = whole, "background"
    alpha = clean(alpha)
    if not (alpha > 128).any():
        raise ValueError("Nothing recognisable in the photo")
    out = image.convert("RGBA")
    out.putalpha(Image.fromarray(alpha))
    out = out.crop(Image.fromarray(alpha > 128).getbbox())
    out.thumbnail((MAX_OUTPUT, MAX_OUTPUT))
    return out, method


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/cutout")
async def cutout(file: UploadFile = File(...)):
    try:
        result, method = cut(Image.open(io.BytesIO(await file.read())))
    except Exception as e:  # noqa: BLE001 - the app falls back to the original photo
        raise HTTPException(422, f"Could not cut out the garment: {e}") from None
    buffer = io.BytesIO()
    result.save(buffer, "PNG", optimize=True)
    return Response(buffer.getvalue(), media_type="image/png", headers={"X-Cutout-Method": method})


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8010, log_level="warning")
