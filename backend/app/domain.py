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
