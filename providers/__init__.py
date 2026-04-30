"""
LLM providers for permission review.

Each provider implements: review(prompt: str, timeout: int) -> str

Selection modes:
  1. Env var mode (backward compatible): PERMIT_PROVIDER env var -> single provider
  2. Config file mode: ~/.claude-auto-permit/*.json -> multi-provider with priority
     Supports "models" array for multiple models per provider.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import time

from providers.codex import review as _codex_review
from providers.anthropic_api import review as _anthropic_review
from providers.openai_api import review as _openai_review

PROVIDERS = {
    "codex": _codex_review,
    "anthropic": _anthropic_review,
    "openai": _openai_review,
}

CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".claude-auto-permit")
UNAVAILABLE_TTL = 600


def _unavailable_flag_path(provider_name: str, model_name: str = "") -> str:
    safe = provider_name.replace("/", "_").replace("\\", "_")
    if model_name:
        msafe = model_name.replace("/", "_").replace("\\", "_")
        safe += f"__{msafe}"
    return os.path.join(tempfile.gettempdir(), f"claude_permit_unavailable_{safe}.flag")


def mark_provider_unavailable(provider_name: str, reason: str, model_name: str = ""):
    try:
        with open(_unavailable_flag_path(provider_name, model_name), "w") as f:
            f.write(reason)
    except Exception:
        pass


def is_provider_unavailable(provider_name: str, model_name: str = "") -> str | None:
    try:
        path = _unavailable_flag_path(provider_name, model_name)
        if not os.path.exists(path):
            return None
        age = time.time() - os.path.getmtime(path)
        if age > UNAVAILABLE_TTL:
            os.remove(path)
            return None
        with open(path, "r") as f:
            return f.read().strip() or "Provider unavailable"
    except Exception:
        return None


def _create_openai_review(config: dict):
    def review(prompt: str, timeout: int = 25) -> str:
        return _openai_review(prompt, timeout=timeout, _config=config)
    return review


def _create_anthropic_review(config: dict):
    def review(prompt: str, timeout: int = 25) -> str:
        return _anthropic_review(prompt, timeout=timeout, _config=config)
    return review


_PROVIDER_FACTORIES = {
    "openai": _create_openai_review,
    "anthropic": _create_anthropic_review,
    "codex": lambda config: _codex_review,
}


def _clamp_priority(value) -> int:
    if not isinstance(value, int) or value < 0:
        return 5
    return min(value, 10)


def _extract_model_entries(config: dict, provider_priority: int):
    """Extract (model_priority, model_name, model_config) entries from a config.

    Supports two formats:
      - Single model: {"model": "glm-4.7"} -> one entry with default priority
      - Multi model:  {"models": [{"model": "glm-4.7", "priority": 3}, ...]} -> multiple entries
    """
    models = config.get("models")
    if isinstance(models, list) and models:
        entries = []
        for m in models:
            if not isinstance(m, dict) or "model" not in m:
                continue
            mp = _clamp_priority(m.get("priority", 5))
            model_name = m["model"]
            model_config = {k: v for k, v in config.items() if k not in ("models", "model", "priority")}
            model_config["model"] = model_name
            entries.append((mp, model_name, model_config))
        if entries:
            return entries

    model_name = config.get("model", "")
    model_config = {k: v for k, v in config.items() if k not in ("models", "priority")}
    return [(5, model_name, model_config)]


def load_provider_configs() -> list[tuple[int, int, str, str, object]]:
    """Load provider configs from ~/.claude-auto-permit/*.json.

    Returns: list of (provider_priority, model_priority, provider_name, model_name, review_fn)
    """
    if not os.path.isdir(CONFIG_DIR):
        return []

    entries = []
    for filename in os.listdir(CONFIG_DIR):
        if not filename.endswith(".json"):
            continue
        provider_name = filename[:-5]
        filepath = os.path.join(CONFIG_DIR, filename)

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                config = json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            print(f"[Config] Skipping invalid {filename}: {e}", file=sys.stderr)
            continue

        if not isinstance(config, dict):
            print(f"[Config] Skipping {filename}: not a JSON object", file=sys.stderr)
            continue

        pp = _clamp_priority(config.get("priority", 5))
        type_name = config.get("provider", provider_name)
        factory = _PROVIDER_FACTORIES.get(type_name)
        if not factory:
            if type_name in PROVIDERS:
                factory = PROVIDERS[type_name]
            else:
                print(f"[Config] Unknown provider: {type_name} in {filename}", file=sys.stderr)
                continue

        for mp, model_name, model_config in _extract_model_entries(config, pp):
            review_fn = factory(model_config)
            entries.append((pp, mp, provider_name, model_name, review_fn))

    entries.sort(key=lambda x: (x[0], x[1]))
    return entries


def get_active_providers() -> list[tuple[str, str, object]]:
    """Get active providers as [(provider_name, model_name, review_fn)].

    Config file mode: expanded from models arrays, sorted by (provider_priority, model_priority).
    Env var mode: returns [(name, "", review_fn)] for backward compat.
    """
    if os.path.isdir(CONFIG_DIR):
        loaded = load_provider_configs()
        if loaded:
            return [(name, model, fn) for (_, _, name, model, fn) in loaded]

    provider_name = os.environ.get("PERMIT_PROVIDER", "codex")
    review_fn = PROVIDERS.get(provider_name)
    if review_fn:
        return [(provider_name, "", review_fn)]

    return []
