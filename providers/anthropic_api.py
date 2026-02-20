"""
Anthropic API provider — uses ANTHROPIC_API_KEY.

Env vars:
  ANTHROPIC_API_KEY    — required
  ANTHROPIC_MODEL      — optional (default: claude-sonnet-4-5-20250514)
"""

import json
import os
import urllib.request
import urllib.error


def review(prompt: str, timeout: int = 25) -> str:
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")

    model = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-5-20250514")

    request_body = json.dumps({
        "model": model,
        "max_tokens": 200,
        "messages": [{"role": "user", "content": prompt}]
    }).encode("utf-8")

    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages",
        data=request_body,
        headers={
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01"
        }
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("content", [{}])[0].get("text", "")
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode("utf-8")[:200]
        except Exception:
            body = ""
        raise RuntimeError(f"HTTP {e.code}: {body}")
