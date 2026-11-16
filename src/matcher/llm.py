"""One optional LLM call with a cache. With LLM_PROVIDER=none it always returns None."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from .config import PATHS
from .privacy import assert_no_pii

DEFAULT_MODELS = {"openai": "gpt-4o-mini", "gemini": "gemini-2.0-flash", "anthropic": "claude-haiku-4-5"}
_cache: dict[str, dict] | None = None


def provider() -> str:
    from . import settings  # importing settings reads .env once (never in tests)
    settings.load_env_file()
    return os.environ.get("LLM_PROVIDER", "none").strip().lower() or "none"


def _model(prov: str) -> str:
    return os.environ.get("LLM_MODEL", "").strip() or DEFAULT_MODELS.get(prov, "")


def _load_cache(path: Path) -> dict[str, dict]:
    global _cache
    if _cache is None:
        _cache = {}
        if path.exists():
            for line in path.read_text().splitlines():
                try:
                    rec = json.loads(line)
                    _cache[rec["key"]] = rec["response"]
                except Exception:
                    continue
    return _cache


def _known_names() -> list[str]:
    p = PATHS["contacts"]
    if not Path(p).exists():
        return []
    import pandas as pd
    return pd.read_csv(p)["name"].dropna().tolist()


def _call(prov: str, model: str, system: str, user: str) -> str:
    if prov == "openai":
        from openai import OpenAI
        r = OpenAI().chat.completions.create(
            model=model, temperature=0, response_format={"type": "json_object"},
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}])
        return r.choices[0].message.content
    if prov == "gemini":
        from google import genai
        client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
        r = client.models.generate_content(
            model=model, contents=user,
            config={"system_instruction": system, "temperature": 0, "response_mime_type": "application/json"})
        return r.text
    if prov == "anthropic":
        import anthropic
        r = anthropic.Anthropic().messages.create(
            model=model, max_tokens=512, temperature=0, system=system,
            messages=[{"role": "user", "content": user}])
        return r.content[0].text
    raise ValueError(f"unknown provider {prov}")


def complete_json(system: str, user: str, schema_hint: dict, known_names: list[str] | None = None) -> dict | None:
    prov = provider()
    if prov == "none":
        return None
    names = known_names if known_names is not None else _known_names()
    assert_no_pii(user, names)  # raises before anything leaves the machine
    model = _model(prov)
    key = hashlib.sha256(f"{prov}|{model}|{system}|{user}".encode()).hexdigest()
    cache_path = Path(PATHS["llm_cache"])
    cache = _load_cache(cache_path)
    if key in cache:
        return cache[key]
    try:
        text = _call(prov, model, system + "\nSchema: " + json.dumps(schema_hint), user)
        text = text.strip()
        if text.startswith("```"):
            text = text.strip("`").removeprefix("json").strip()
        data = json.loads(text)
        if not isinstance(data, dict):
            return None
    except Exception:
        return None
    cache[key] = data
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    with cache_path.open("a") as f:
        f.write(json.dumps({"key": key, "response": data}) + "\n")
    return data
