"""
Codex CLI provider — uses ChatGPT subscription, no API key needed.

Requires: `codex` CLI installed and logged in (`codex login`).
"""

import os
import subprocess
import tempfile


def review(prompt: str, timeout: int = 25, *, _config: dict | None = None) -> str:
    out_file = os.path.join(tempfile.gettempdir(), "codex_review_out.txt")

    result = subprocess.run(
        [
            "codex", "exec",
            "--skip-git-repo-check",
            "--full-auto",
            "-o", out_file,
            prompt
        ],
        capture_output=True,
        text=True,
        timeout=timeout
    )

    _check_service_error(result)

    response = ""
    if os.path.exists(out_file):
        with open(out_file, "r") as f:
            response = f.read().strip()

    if not response:
        raise RuntimeError("Codex returned no output")

    return response


def _check_service_error(result: subprocess.CompletedProcess):
    stderr = (result.stderr or "").lower()
    stdout = (result.stdout or "").lower()
    combined = stderr + stdout

    signals = [
        "rate limit", "rate_limit", "too many requests", "429",
        "unauthorized", "401", "auth", "login",
        "session expired", "token expired",
        "quota", "billing", "exceeded",
        "503", "service unavailable",
    ]

    for signal in signals:
        if signal in combined:
            raise RuntimeError(f"Service error: '{signal}'")

    if result.returncode != 0 and not result.stdout.strip():
        raise RuntimeError(f"Exit code {result.returncode}")
