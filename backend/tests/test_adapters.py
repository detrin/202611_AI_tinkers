"""Pure adapter logic only (normalisers, model routing) — no network."""
from types import SimpleNamespace

from backend.app.adapters.apify import to_pin, to_product
from backend.app.adapters.featherless import FeatherlessChat
from backend.app.domain import ImageInput


def test_to_pin_automation_lab_format_skips_videos():
    pin = to_pin({"url": "u", "title": "", "altText": "white oxford", "imageUrl": "https://i.pinimg.com/originals/a/b.jpg"})
    assert (pin.image_url, pin.title) == ("https://i.pinimg.com/originals/a/b.jpg", "white oxford")   # 474x not reliable
    assert to_pin({"url": "u", "imageUrl": "x.jpg", "isVideo": True}) is None


def test_to_pin_uses_474_image_and_skips_imageless():
    pin = to_pin({"url": "u", "grid_title": "t", "images": {"474x": {"url": "i"}}})
    assert (pin.url, pin.image_url, pin.title) == ("u", "i", "t")
    assert to_pin({"url": "u", "images": {}}) is None


def test_to_product_reads_offer_list_and_bad_price():
    p = to_product({"url": "u", "name": "n", "image": "i", "offers": [{"price": "12.5", "priceCurrency": "EUR"}]})
    assert (p.price, p.currency, p.image_url) == (12.5, "EUR", "i")
    assert to_product({"url": "u", "offers": {"price": "n/a"}}).price is None
    assert to_product({"name": "no url"}) is None


def test_to_product_ignores_non_string_image():
    assert to_product({"url": "u", "image": ["a", "b"]}).image_url is None


def test_featherless_routes_to_vision_model_only_with_images():
    sent = []
    fake = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kw: sent.append(kw) or
        SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))]))))
    chat = FeatherlessChat(fake, vision_model="V", text_model="T")
    assert chat.complete("hi") == "ok"
    chat.complete("look", ["data:x"])
    assert [s["model"] for s in sent] == ["T", "V"]
    assert sent[1]["messages"][0]["content"][1] == {"type": "image_url", "image_url": {"url": "data:x"}}


def test_image_input_data_url_and_extension():
    img = ImageInput(b"\x00", "image/png")
    assert img.data_url == "data:image/png;base64,AA==" and img.extension == "png"
    assert ImageInput(b"").extension == "jpg"
