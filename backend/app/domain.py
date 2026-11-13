"""Plain value objects passed between adapters and services."""
import base64
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ImageInput:
    content: bytes
    mime: str = "image/jpeg"
    source_url: str | None = None

    @property
    def data_url(self) -> str:
        return f"data:{self.mime};base64," + base64.b64encode(self.content).decode()

    @property
    def extension(self) -> str:
        return {"image/png": "png", "image/webp": "webp"}.get(self.mime, "jpg")


@dataclass(frozen=True)
class Pin:
    url: str | None
    image_url: str
    title: str | None = None


@dataclass(frozen=True)
class Product:
    url: str
    name: str | None = None
    description: str | None = None
    price: float | None = None
    currency: str | None = None
    image_url: str | None = None
    marketplace: str | None = None
    raw: dict = field(default_factory=dict)


@dataclass(frozen=True)
class SocialPost:
    url: str
    image_urls: tuple[str, ...]
    caption: str | None = None
    timestamp: str | None = None


def sniff_mime(content: bytes, default: str = "image/jpeg") -> str:
    """Best-effort image type from magic bytes (shops often serve png/webp behind .jpg URLs)."""
    if content.startswith(b"\x89PNG"):
        return "image/png"
    if content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "image/webp"
    if content[:3] == b"GIF":
        return "image/gif"
    return default
