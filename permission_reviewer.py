#!/usr/bin/env python3
"""
PermissionRequest Hook: AI-powered permission review + session permission granting.

When a permission dialog is about to appear, this hook:
1. Calls the configured LLM provider to review the tool call
2. If approved → grants permission + writes session-level permission
   (equivalent to user selecting "Yes, don't ask again")
3. If denied / timeout / error → exit 1, shows normal permission dialog

Provider selection via PERMIT_PROVIDER env var:
  - "codex"     — Codex CLI, uses ChatGPT subscription (default)
  - "anthropic"  — Anthropic API, requires ANTHROPIC_API_KEY
  - "openai"     — OpenAI API, requires OPENAI_API_KEY
                   (also supports compatible APIs via OPENAI_BASE_URL)
"""

import json
import os
import re
import subprocess
import sys
import tempfile
import time
from datetime import datetime

# Add project root to path so providers can be imported
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from providers import PROVIDERS


REVIEW_PROMPT_TEMPLATE = """You are a security reviewer for a Claude Code session.
Evaluate this tool call and decide: approve or deny.

Tool: {tool_name}
Input:
```json
{tool_input}
```

Rules:
1. APPROVE normal dev work: build, test, lint, format, compile
2. APPROVE routine git: status, diff, add, commit, log, branch, checkout
3. APPROVE package management: npm install, pip install, cargo build, etc.
4. APPROVE dev servers: npm run dev, python manage.py runserver, etc.
5. APPROVE project build tools: xcodebuild, make, cmake, gradle, etc.
6. APPROVE web fetches to documentation sites, package registries, Stack Overflow, GitHub
7. DENY destructive ops: rm -rf /, git push --force to main, DROP TABLE
8. DENY access to secrets: cat ~/.ssh/id_rsa, reading password files
9. DENY suspicious network: uploading data to unknown hosts, wget executables, fetching suspicious URLs
10. DENY system-level danger: modifying /etc, sudo rm, system config changes
11. DENY reading/writing sensitive files outside the project directory
12. When unsure, APPROVE — developer is working on their own machine

Reply with ONLY a JSON object, no other text:
{{"decision": "approve" or "deny", "reason": "brief reason"}}"""


LOG_FILE_NAME = ".claude_permission.log"

UNAVAILABLE_FLAG = os.path.join(tempfile.gettempdir(), "claude_permit_unavailable.flag")
UNAVAILABLE_TTL = 600


def write_log(cwd: str, tool_name: str, decision: str, reason: str, detail: str = ""):
    try:
        log_path = os.path.join(cwd, LOG_FILE_NAME)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        detail_short = detail[:80] + "..." if len(detail) > 80 else detail
        parts = [f"[{timestamp}]", f"tool={tool_name}", f"decision={decision}", f"reason={reason}"]
        if detail_short:
            parts.append(f"detail={detail_short}")
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(" ".join(parts) + "\n")
    except Exception:
        pass


def mark_unavailable(reason: str):
    try:
        with open(UNAVAILABLE_FLAG, "w") as f:
            f.write(reason)
    except Exception:
        pass


def is_unavailable() -> str | None:
    try:
        if not os.path.exists(UNAVAILABLE_FLAG):
            return None
        age = time.time() - os.path.getmtime(UNAVAILABLE_FLAG)
        if age > UNAVAILABLE_TTL:
            os.remove(UNAVAILABLE_FLAG)
            return None
        with open(UNAVAILABLE_FLAG, "r") as f:
            return f.read().strip() or "Provider unavailable"
    except Exception:
        return None


def parse_decision(response: str) -> tuple[str, str]:
    """Parse LLM response to extract decision JSON."""
    clean = response
    if "```" in clean:
        match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', clean, re.DOTALL)
        if match:
            clean = match.group(1)
    start = clean.find("{")
    end = clean.rfind("}") + 1
    if start >= 0 and end > start:
        clean = clean[start:end]

    data = json.loads(clean)
    decision = data.get("decision", "approve").lower().strip()
    reason = data.get("reason", "No reason provided")
    return decision, reason


def main():
    input_data = json.loads(sys.stdin.read())

    cwd = input_data.get("cwd", "")
    tool_name = input_data.get("tool_name", "unknown")
    tool_input = input_data.get("tool_input", {})
    permission_suggestions = input_data.get("permission_suggestions", [])

    detail = tool_input.get("command", "") or tool_input.get("file_path", "") or tool_input.get("url", "")

    # AskUserQuestion 必须由用户手动回答，不能自动批准
    if tool_name == "AskUserQuestion":
        write_log(cwd, tool_name, "manual(deny)", "AskUserQuestion must be answered by user", detail)
        print("[Reviewer denied] AskUserQuestion requires manual user interaction", file=sys.stderr)
        sys.exit(1)

    # Select provider
    provider_name = os.environ.get("PERMIT_PROVIDER", "codex")
    review_fn = PROVIDERS.get(provider_name)
    if not review_fn:
        write_log(cwd, tool_name, "manual(bad-provider)", f"Unknown provider: {provider_name}", detail)
        print(f"Unknown provider: {provider_name}. Available: {', '.join(PROVIDERS.keys())}", file=sys.stderr)
        sys.exit(1)

    # Provider unavailable → exit 1, show normal dialog
    unavailable_reason = is_unavailable()
    if unavailable_reason:
        write_log(cwd, tool_name, "manual(provider-down)", unavailable_reason, detail)
        print(f"[Provider unavailable] {unavailable_reason}", file=sys.stderr)
        sys.exit(1)

    # Build prompt
    input_str = json.dumps(tool_input, ensure_ascii=False, indent=2)
    if len(input_str) > 3000:
        input_str = input_str[:3000] + "\n... (truncated)"

    prompt = REVIEW_PROMPT_TEMPLATE.format(
        tool_name=tool_name,
        tool_input=input_str
    )

    # Call provider
    try:
        response = review_fn(prompt, timeout=25)
        decision, reason = parse_decision(response)

        if decision == "approve":
            write_log(cwd, tool_name, "allow+session", reason, detail)
            output = {
                "hookSpecificOutput": {
                    "hookEventName": "PermissionRequest",
                    "decision": {
                        "behavior": "allow",
                        "updatedPermissions": permission_suggestions
                    }
                }
            }
            print(json.dumps(output))
        else:
            write_log(cwd, tool_name, "manual(deny)", reason, detail)
            print(f"[Reviewer denied] {reason}", file=sys.stderr)
            sys.exit(1)

    except subprocess.TimeoutExpired:
        write_log(cwd, tool_name, "manual(timeout)", "Timeout", detail)
        print("[Reviewer] Timeout", file=sys.stderr)
        sys.exit(1)
    except RuntimeError as e:
        error_msg = str(e)[:200]
        # Service-level errors → mark unavailable
        mark_unavailable(error_msg)
        write_log(cwd, tool_name, "manual(error)", error_msg, detail)
        print(f"[Reviewer] {error_msg}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        error_msg = str(e)[:200]
        write_log(cwd, tool_name, "manual(error)", error_msg, detail)
        print(f"[Reviewer] {error_msg}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
