"""
OpenAI API provider — uses OPENAI_API_KEY.

Env vars:
  OPENAI_API_KEY       — required
  OPENAI_MODEL         — optional (default: gpt-4o-mini)
  OPENAI_BASE_URL      — optional (default: https://api.openai.com/v1/chat/completions)
                         Set this to use compatible APIs (e.g. DeepSeek, local models).
"""

from __future__ import annotations

import json
import os
import platform
import sys
import urllib.request
import urllib.error

_ROO_CODE_VERSION = "3.53.0"
_ROO_NODE_VERSION = "v20.19.2"
_OPENAI_SDK_VERSION = "5.12.2"


def _stainless_headers() -> dict:
    return {
        "X-Stainless-Lang": "js",
        "X-Stainless-Package-Version": _OPENAI_SDK_VERSION,
        "X-Stainless-OS": _normalize_os(platform.system()),
        "X-Stainless-Arch": _normalize_arch(platform.machine().lower()),
        "X-Stainless-Runtime": "node",
        "X-Stainless-Runtime-Version": _ROO_NODE_VERSION,
        "X-Stainless-Retry-Count": "0",
    }


def review(prompt: str, timeout: int = 25, *, _config: dict | None = None) -> str:
    if _config:
        api_key = _config.get("api_key", "")
        if not api_key:
            raise RuntimeError("api_key not set in config")
        model = _config.get("model", "gpt-4o-mini")
        base_url = _config.get("base_url", "https://api.openai.com/v1/chat/completions")
    else:
        api_key = os.environ.get("OPENAI_API_KEY", "")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY not set")
        model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
        base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1/chat/completions")

    body = {
        "model": model,
        "max_tokens": 512,
        "messages": [{"role": "user", "content": prompt}],
        "thinking": {"type": "disabled"},
    }
    request_body = json.dumps(body).encode("utf-8")

    req = urllib.request.Request(
        base_url,
        data=request_body,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {api_key}",
            "HTTP-Referer": "https://github.com/RooVetGit/Roo-Cline",
            "X-Title": "Roo Code",
            "User-Agent": f"RooCode/{_ROO_CODE_VERSION}",
            **_stainless_headers(),
        }
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            message = data.get("choices", [{}])[0].get("message", {})
            content = message.get("content", "")
            if not content:
                content = message.get("reasoning_content", "")
            return content
    except urllib.error.HTTPError as e:
        try:
            body = e.read().decode("utf-8")[:200]
        except Exception:
            body = ""
        raise RuntimeError(f"HTTP {e.code}: {body}")


def _normalize_os(system: str) -> str:
    s = system.lower()
    if s == "darwin":
        return "MacOS"
    if s == "linux":
        return "Linux"
    if s == "windows" or s.startswith("win"):
        return "Windows"
    if s == "freebsd":
        return "FreeBSD"
    if s == "openbsd":
        return "OpenBSD"
    return f"Other:{system}"


def _normalize_arch(machine: str) -> str:
    if machine in ("x86_64", "x64", "amd64"):
        return "x64"
    if machine in ("arm64", "aarch64"):
        return "arm64"
    if machine == "arm":
        return "arm"
    if machine and sys.maxsize <= 2**32:
        return "x32"
    if machine:
        return f"other:{machine}"
    return "unknown"
