"""ChatModel over Featherless' OpenAI-compatible API. Routes to the vision model only when images are given."""
from collections.abc import Sequence

from openai import OpenAI


class FeatherlessChat:
    BASE_URL = "https://api.featherless.ai/v1"

    def __init__(self, client: OpenAI, vision_model: str, text_model: str, max_tokens: int = 2000):
        self._client, self._vision, self._text, self._max_tokens = client, vision_model, text_model, max_tokens

    @classmethod
    def create(cls, api_key: str, vision_model: str, text_model: str) -> "FeatherlessChat":
        return cls(OpenAI(base_url=cls.BASE_URL, api_key=api_key), vision_model, text_model)

    def complete(self, prompt: str, images: Sequence[str] = ()) -> str:
        content = [{"type": "text", "text": prompt}]
        content += [{"type": "image_url", "image_url": {"url": u}} for u in images]
        r = self._client.chat.completions.create(
            model=self._vision if images else self._text, max_tokens=self._max_tokens, temperature=0.3,
            messages=[{"role": "user", "content": content}],
        )
        return r.choices[0].message.content or ""
