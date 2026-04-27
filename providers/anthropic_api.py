"""
Anthropic API provider — uses ANTHROPIC_API_KEY.

Env vars:
  ANTHROPIC_API_KEY    — required
  ANTHROPIC_MODEL      — optional (default: claude-sonnet-4-5-20250514)
"""

import json
import os
import platform
import sys
import urllib.request
import urllib.error

_ROO_NODE_VERSION = "v20.19.2"
_ANTHROPIC_SDK_VERSION = "0.37.0"


def _stainless_headers() -> dict:
    return {
        "X-Stainless-Lang": "js",
        "X-Stainless-Package-Version": _ANTHROPIC_SDK_VERSION,
        "X-Stainless-OS": _normalize_os(platform.system()),
        "X-Stainless-Arch": _normalize_arch(platform.machine().lower()),
        "X-Stainless-Runtime": "node",
        "X-Stainless-Runtime-Version": _ROO_NODE_VERSION,
        "X-Stainless-Retry-Count": "0",
    }


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
            "Accept": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "User-Agent": f"Anthropic/JS {_ANTHROPIC_SDK_VERSION}",
            **_stainless_headers(),
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
