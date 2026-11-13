"""Shared clients and helpers: config, Supabase, LLM (Featherless), Apify, storage, weather."""
import base64
import json
import os
import re
import subprocess
import uuid
from datetime import timedelta
from decimal import Decimal
from functools import lru_cache

import requests
from apify_client import ApifyClient
from openai import OpenAI
from supabase import Client, create_client

VISION_MODEL = os.environ.get("VISION_MODEL", "Qwen/Qwen3-VL-30B-A3B-Instruct")  # GLM-5.3-Flash ignores images
TEXT_MODEL = os.environ.get("TEXT_MODEL", "zai-org/GLM-5.3-Flash")
BUCKET = "images"
UA = {"User-Agent": "wardrobe-stylist/0.1 (hackathon)"}


def secret(name: str) -> str:
    """Env var first (deployments), else macOS Keychain (local dev)."""
    if os.environ.get(name):
        return os.environ[name]
    out = subprocess.run(["security", "find-generic-password", "-a", os.environ.get("USER", ""), "-s", name, "-w"],
                         capture_output=True, text=True).stdout.strip()
    if not out:
        raise RuntimeError(f"Missing secret {name} (env var or Keychain)")
    return out


@lru_cache
def db() -> Client:
    return create_client(secret("SUPABASE_URL"), secret("SUPABASE_SERVICE_KEY"))


@lru_cache
def llm() -> OpenAI:
    return OpenAI(base_url="https://api.featherless.ai/v1", api_key=secret("FEATHERLESS_API_KEY"))


@lru_cache
def apify() -> ApifyClient:
    return ApifyClient(secret("APIFY_TOKEN"))


# ---------- LLM ----------
def parse_json(s: str):
    s = re.sub(r"^```(json)?|```$", "", s.strip(), flags=re.M).strip()
    m = re.search(r"[\[{].*[\]}]", s, re.S)
    return json.loads(m.group(0) if m else s)


def ask(prompt: str, images: list[str] = (), max_tokens: int = 2000) -> str:
    """images: http(s) URLs or data: URLs."""
    content = [{"type": "text", "text": prompt}] + [{"type": "image_url", "image_url": {"url": u}} for u in images]
    r = llm().chat.completions.create(model=VISION_MODEL if images else TEXT_MODEL, max_tokens=max_tokens,
                                      temperature=0.3, messages=[{"role": "user", "content": content}])
    return r.choices[0].message.content


def ask_json(prompt: str, images: list[str] = (), retries: int = 1):
    for i in range(retries + 1):
        try:
            return parse_json(ask(prompt, images))
        except (json.JSONDecodeError, ValueError):
            if i == retries:
                raise


# ---------- images / storage ----------
def fetch_bytes(url: str) -> bytes:
    r = requests.get(url, headers=UA, timeout=30)
    r.raise_for_status()
    return r.content


def data_url(b: bytes, mime: str = "image/jpeg") -> str:
    return f"data:{mime};base64," + base64.b64encode(b).decode()


def store_image(user_id: str | None, kind: str, content: bytes, mime: str = "image/jpeg",
                source_url: str | None = None) -> dict:
    ext = {"image/png": "png", "image/webp": "webp"}.get(mime, "jpg")
    path = f"{user_id or 'shared'}/{kind}/{uuid.uuid4()}.{ext}"
    db().storage.from_(BUCKET).upload(path, content, {"content-type": mime})
    return db().table("images").insert({"user_id": user_id, "kind": kind, "bucket_path": path,
                                        "source_url": source_url}).execute().data[0]


def signed_url(path: str | None, ttl: int = 3600) -> str | None:
    if not path:
        return None
    r = db().storage.from_(BUCKET).create_signed_url(path, ttl)
    return r.get("signedURL") or r.get("signedUrl") or r.get("signed_url")


# ---------- Apify ----------
def run_actor(actor: str, run_input: dict, cap_usd: str = "1") -> list[dict]:
    run = apify().actor(actor).call(run_input=run_input, max_total_charge_usd=Decimal(cap_usd),
                                    run_timeout=timedelta(minutes=8), logger=None)
    run = run if isinstance(run, dict) else run.model_dump(by_alias=True)
    if run.get("status") != "SUCCEEDED":
        raise RuntimeError(f"{actor} run {run.get('id')} ended {run.get('status')}")
    return apify().dataset(run["defaultDatasetId"]).list_items().items


def upsert_products(items: list[dict], query: str | None = None) -> list[dict]:
    rows = []
    for i in items:
        if not i.get("url"):
            continue
        o = i.get("offers") or {}
        o = o[0] if isinstance(o, list) and o else (o if isinstance(o, dict) else {})
        price = o.get("price") if o else i.get("price")
        try:
            price = float(price) if price is not None else None
        except (TypeError, ValueError):
            price = None
        rows.append({"url": i["url"], "name": i.get("name"), "description": (i.get("description") or "")[:4000],
                     "price": price, "currency": o.get("priceCurrency") or i.get("currency"),
                     "image_url": i.get("image") if isinstance(i.get("image"), str) else None,
                     "marketplace": i.get("marketplace"), "query": query or i.get("keyword"), "raw": i})
    if not rows:
        return []
    return db().table("products").upsert(rows, on_conflict="url").execute().data


# ---------- weather ----------
def weather(city: str, date: str | None = None) -> dict:
    g = requests.get("https://geocoding-api.open-meteo.com/v1/search", params={"name": city, "count": 1}, timeout=15).json()
    if not g.get("results"):
        raise ValueError(f"Unknown city {city}")
    g = g["results"][0]
    params = {"latitude": g["latitude"], "longitude": g["longitude"], "timezone": "auto",
              "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max,wind_speed_10m_max,weather_code"}
    params.update({"start_date": date, "end_date": date} if date else {"forecast_days": 1})
    d = requests.get("https://api.open-meteo.com/v1/forecast", params=params, timeout=15).json()["daily"]
    return {"city": g["name"], "country": g.get("country"), **{k: v[0] for k, v in d.items()}}
