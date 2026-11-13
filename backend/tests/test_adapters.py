"""Pure adapter logic only (normalisers, model routing) — no network."""
from types import SimpleNamespace

from backend.app.adapters.apify import to_pin, to_product
from backend.app.adapters.openai_chat import OpenAIChat
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


def test_chat_routes_to_vision_model_only_with_images_and_pins_providers():
    sent = []
    fake = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kw: sent.append(kw) or
        SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))]))))
    chat = OpenAIChat(fake, vision_model="V", text_model="T", providers={"T": ["groq"]})
    assert chat.complete("hi") == "ok"
    chat.complete("look", ["data:x"])
    assert [s["model"] for s in sent] == ["T", "V"]
    assert sent[1]["messages"][0]["content"][1] == {"type": "image_url", "image_url": {"url": "data:x"}}
    assert sent[0]["extra_body"] == {"provider": {"order": ["groq"]}} and sent[1]["extra_body"] is None
    assert sent[0]["max_tokens"] >= 8000   # reasoning models need room before the JSON


def test_settings_pick_llm_provider(monkeypatch):
    from backend.app.config import Settings
    monkeypatch.delenv("VISION_MODEL", raising=False)
    monkeypatch.delenv("TEXT_MODEL", raising=False)
    asked = []
    secret = lambda name: asked.append(name) or "x"
    monkeypatch.setenv("LLM_PROVIDER", "featherless")
    s = Settings.load(secret)
    assert (s.llm_provider, s.text_model) == ("featherless", "zai-org/GLM-5.3-Flash") and "FEATHERLESS_API_KEY" in asked
    monkeypatch.delenv("LLM_PROVIDER")
    s = Settings.load(secret)
    assert (s.llm_provider, s.vision_model) == ("openrouter", "google/gemini-3.1-flash-lite") and "OPENROUTER_API_KEY" in asked


def test_default_routes_any_text_model_to_groq_and_featherless_has_no_pin(monkeypatch):
    from backend.app.container import _chat
    from backend.app.config import Settings
    made = []
    fake = type("C", (), {"create": staticmethod(lambda *a: made.append(a))})
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.setenv("TEXT_MODEL", "openai/gpt-oss-20b")
    _chat(Settings.load(lambda n: "k"), fake)
    assert made[-1][0] == "https://openrouter.ai/api/v1" and made[-1][4] == {"openai/gpt-oss-20b": ["groq"]}
    monkeypatch.setenv("LLM_PROVIDER", "featherless")
    monkeypatch.delenv("TEXT_MODEL")
    _chat(Settings.load(lambda n: "k"), fake)
    assert made[-1][0] == "https://api.featherless.ai/v1" and made[-1][4] is None
def test_image_input_data_url_and_extension():
    img = ImageInput(b"\x00", "image/png")
    assert img.data_url == "data:image/png;base64,AA==" and img.extension == "png"
    assert ImageInput(b"").extension == "jpg"
