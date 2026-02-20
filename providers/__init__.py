"""
LLM providers for permission review.

Each provider implements: review(prompt: str, timeout: int) -> str
- Input: the review prompt text
- Output: raw LLM response text (will be parsed as JSON by the caller)
- Raises: RuntimeError on failure, subprocess.TimeoutExpired on timeout

Select provider via PERMIT_PROVIDER env var (default: "codex").
"""

from providers.codex import review as codex_review
from providers.anthropic_api import review as anthropic_review
from providers.openai_api import review as openai_review

PROVIDERS = {
    "codex": codex_review,
    "anthropic": anthropic_review,
    "openai": openai_review,
}
