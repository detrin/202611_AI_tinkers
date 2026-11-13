"""Settings and secret loading: env var first, macOS Keychain as local-dev fallback."""
import os
import subprocess
from dataclasses import dataclass


def read_secret(name: str) -> str:
    if value := os.environ.get(name):
        return value
    out = subprocess.run(
        ["security", "find-generic-password", "-a", os.environ.get("USER", ""), "-s", name, "-w"],
        capture_output=True, text=True,
    ).stdout.strip()
    if not out:
        raise RuntimeError(f"Missing secret {name} (set env var or Keychain item)")
    return out


# OpenAI-compatible LLM backends: (base_url, key secret, vision model, text model, text provider order)
LLM_PROVIDERS = {
    # DEFAULT. Text on Groq (any TEXT_MODEL is routed to Groq first); vision on OpenRouter because Groq serves no
    # vision models. Measured 2026-11-13 on the real prompts: ~1.2 s per photo, product ranking ~4.5 s.
    "openrouter": ("https://openrouter.ai/api/v1", "OPENROUTER_API_KEY", "google/gemini-3.1-flash-lite",
                   "openai/gpt-oss-120b", ["groq"]),
    # OPT-IN (LLM_PROVIDER=featherless): ~18 s per photo; GLM ranking returned no JSON after ~75 s.
    "featherless": ("https://api.featherless.ai/v1", "FEATHERLESS_API_KEY", "Qwen/Qwen3-VL-30B-A3B-Instruct",
                    "zai-org/GLM-5.3-Flash", []),
}


@dataclass(frozen=True)
class Settings:
    supabase_url: str
    supabase_key: str
    llm_key: str
    apify_token: str
    llm_provider: str = "openrouter"        # LLM_PROVIDER=openrouter|featherless, see LLM_PROVIDERS
    vision_model: str = LLM_PROVIDERS["openrouter"][2]
    text_model: str = LLM_PROVIDERS["openrouter"][3]
    taste_model: str = "claude-opus-5-5"  # via `claude -p`
    bucket: str = "images"
    signed_url_ttl: int = 3600
    job_workers: int = 4
    calendar_ics_url: str | None = None
    calendar_demo_user_id: str | None = None
    outfit_timezone: str = "Europe/Prague"
    apify_venue_lookup: bool = False
    today_api_token: str | None = None
    calendar_demo: bool = False

    @classmethod
    def load(cls, secret=read_secret) -> "Settings":
        provider = os.environ.get("LLM_PROVIDER", cls.llm_provider)
        if provider not in LLM_PROVIDERS:
            raise RuntimeError(f"LLM_PROVIDER must be one of {sorted(LLM_PROVIDERS)}")
        return cls(
            supabase_url=secret("SUPABASE_URL"),
            supabase_key=secret("SUPABASE_SERVICE_KEY"),
            llm_key=secret(LLM_PROVIDERS[provider][1]),
            apify_token=secret("APIFY_TOKEN"),
            llm_provider=provider,
            vision_model=os.environ.get("VISION_MODEL", LLM_PROVIDERS[provider][2]),
            text_model=os.environ.get("TEXT_MODEL", LLM_PROVIDERS[provider][3]),
            taste_model=os.environ.get("TASTE_MODEL", cls.taste_model),
            calendar_ics_url=os.environ.get("CALENDAR_ICS_URL"),
            calendar_demo_user_id=os.environ.get("CALENDAR_DEMO_USER_ID"),
            outfit_timezone=os.environ.get("OUTFIT_TIMEZONE", cls.outfit_timezone),
            apify_venue_lookup=os.environ.get("APIFY_VENUE_LOOKUP") == "1",
            today_api_token=os.environ.get("TODAY_API_TOKEN"),
            calendar_demo=os.environ.get("CALENDAR_DEMO") == "1",
        )
