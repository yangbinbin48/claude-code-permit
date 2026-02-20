"""
OpenAI API provider — uses OPENAI_API_KEY.

Env vars:
  OPENAI_API_KEY       — required
  OPENAI_MODEL         — optional (default: gpt-4o-mini)
  OPENAI_BASE_URL      — optional (default: https://api.openai.com/v1/chat/completions)
                         Set this to use compatible APIs (e.g. DeepSeek, local models).
"""

import json
import os
import urllib.request
import urllib.error


def review(prompt: str, timeout: int = 25) -> str:
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set")

    model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1/chat/completions")

    request_body = json.dumps({
        "model": model,
        "max_tokens": 200,
        "messages": [{"role": "user", "content": prompt}]
    }).encode("utf-8")

    req = urllib.request.Request(
        base_url,
        data=request_body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("choices", [{}])[0].get("message", {}).get("content", "")
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode("utf-8")[:200]
        except Exception:
            body = ""
        raise RuntimeError(f"HTTP {e.code}: {body}")
