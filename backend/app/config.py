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


@dataclass(frozen=True)
class Settings:
    supabase_url: str
    supabase_key: str
    featherless_key: str
    apify_token: str
    vision_model: str = "Qwen/Qwen3-VL-30B-A3B-Instruct"  # GLM-5.3-Flash ignores images on Featherless
    text_model: str = "zai-org/GLM-5.3-Flash"
    taste_model: str = "claude-opus-5-5"  # via `claude -p`
    bucket: str = "images"
    signed_url_ttl: int = 3600
    job_workers: int = 4
    calendar_ics_url: str | None = None
    calendar_demo_user_id: str | None = None
    outfit_timezone: str = "Europe/Prague"
    apify_venue_lookup: bool = False
    today_api_token: str | None = None

    @classmethod
    def load(cls, secret=read_secret) -> "Settings":
        return cls(
            supabase_url=secret("SUPABASE_URL"),
            supabase_key=secret("SUPABASE_SERVICE_KEY"),
            featherless_key=secret("FEATHERLESS_API_KEY"),
            apify_token=secret("APIFY_TOKEN"),
            vision_model=os.environ.get("VISION_MODEL", cls.vision_model),
            text_model=os.environ.get("TEXT_MODEL", cls.text_model),
            taste_model=os.environ.get("TASTE_MODEL", cls.taste_model),
            calendar_ics_url=os.environ.get("CALENDAR_ICS_URL"),
            calendar_demo_user_id=os.environ.get("CALENDAR_DEMO_USER_ID"),
            outfit_timezone=os.environ.get("OUTFIT_TIMEZONE", cls.outfit_timezone),
            apify_venue_lookup=os.environ.get("APIFY_VENUE_LOOKUP") == "1",
            today_api_token=os.environ.get("TODAY_API_TOKEN"),
        )
