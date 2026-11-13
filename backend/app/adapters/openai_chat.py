"""ChatModel over any OpenAI-compatible API (OpenRouter, Featherless). Routes to the vision model only when
images are given. On OpenRouter a model can be pinned to providers (e.g. Groq for fast text)."""
from collections.abc import Sequence

from openai import OpenAI


class OpenAIChat:
    def __init__(self, client: OpenAI, vision_model: str, text_model: str, max_tokens: int = 8000,
                 providers: dict[str, list[str]] | None = None):
        """max_tokens is generous because reasoning models (gpt-oss, GLM) spend ~2k tokens thinking first.
        providers: {model: [provider, ...]} → OpenRouter `provider.order` with fallbacks allowed."""
        self._client, self._vision, self._text, self._max_tokens = client, vision_model, text_model, max_tokens
        self._providers = providers or {}

    @classmethod
    def create(cls, base_url: str, api_key: str, vision_model: str, text_model: str,
               providers: dict[str, list[str]] | None = None) -> "OpenAIChat":
        return cls(OpenAI(base_url=base_url, api_key=api_key), vision_model, text_model, providers=providers)

    def complete(self, prompt: str, images: Sequence[str] = ()) -> str:
        content = [{"type": "text", "text": prompt}]
        content += [{"type": "image_url", "image_url": {"url": u}} for u in images]
        model = self._vision if images else self._text
        extra = {"provider": {"order": self._providers[model]}} if model in self._providers else None
        r = self._client.chat.completions.create(
            model=model, max_tokens=self._max_tokens, temperature=0.3,
            messages=[{"role": "user", "content": content}], extra_body=extra,
        )
        return r.choices[0].message.content or ""
