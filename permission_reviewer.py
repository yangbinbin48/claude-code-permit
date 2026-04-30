#!/usr/bin/env python3
"""
PermissionRequest Hook: AI-powered permission review + session permission granting.

When a permission dialog is about to appear, this hook:
1. Calls the configured LLM provider(s) to review the tool call
2. If approved → grants permission + writes session-level permission
   (equivalent to user selecting "Yes, don't ask again")
3. If denied / timeout / error → exit 1, shows normal permission dialog

Provider selection:
  - Env var mode: PERMIT_PROVIDER env var -> single provider (backward compatible)
  - Config file mode: ~/.claude-auto-permit/*.json -> multi-provider with priority failover
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from providers import (
    get_active_providers,
    mark_provider_unavailable,
    is_provider_unavailable,
)


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

_SERVICE_SIGNALS = [
    "401", "403", "429", "500", "502", "503",
    "unauthorized", "quota", "billing",
]


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


def parse_decision(response: str) -> tuple[str, str]:
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

    if tool_name == "AskUserQuestion":
        write_log(cwd, tool_name, "manual(deny)", "AskUserQuestion must be answered by user", detail)
        print("[Reviewer denied] AskUserQuestion requires manual user interaction", file=sys.stderr)
        sys.exit(1)

    active_providers = get_active_providers()
    if not active_providers:
        write_log(cwd, tool_name, "manual(no-provider)", "No providers configured", detail)
        print("No providers configured. Set PERMIT_PROVIDER or create ~/.claude-auto-permit/*.json", file=sys.stderr)
        sys.exit(1)

    input_str = json.dumps(tool_input, ensure_ascii=False, indent=2)
    if len(input_str) > 3000:
        input_str = input_str[:3000] + "\n... (truncated)"

    prompt = REVIEW_PROMPT_TEMPLATE.format(
        tool_name=tool_name,
        tool_input=input_str
    )

    last_error = None

    for provider_name, model_name, review_fn in active_providers:
        label = f"{provider_name}/{model_name}" if model_name else provider_name
        unavail_reason = is_provider_unavailable(provider_name, model_name)
        if unavail_reason:
            write_log(cwd, tool_name, "skip", f"{label}: {unavail_reason}", detail)
            last_error = f"{label}: {unavail_reason}"
            continue

        max_attempts = 2

        for attempt in range(max_attempts):
            if attempt > 0:
                time.sleep(1)
            try:
                response = review_fn(prompt, timeout=25)
                decision, reason = parse_decision(response)

                if decision == "approve":
                    write_log(cwd, tool_name, "allow+session", f"[{label}] {reason}", detail)
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
                    sys.exit(0)
                else:
                    write_log(cwd, tool_name, "manual(deny)", f"[{label}] {reason}", detail)
                    print(f"[Reviewer denied] {reason}", file=sys.stderr)
                    sys.exit(1)

            except subprocess.TimeoutExpired:
                last_error = f"{label}: Timeout"
                write_log(cwd, tool_name, f"retry({label},{attempt+1}/{max_attempts})", "Timeout", detail)
            except RuntimeError as e:
                err_msg = str(e)[:200]
                last_error = f"{label}: {err_msg}"
                if any(s in err_msg.lower() for s in _SERVICE_SIGNALS):
                    mark_provider_unavailable(provider_name, err_msg, model_name)
                    write_log(cwd, tool_name, "down", f"{label}: {err_msg}", detail)
                    break
                write_log(cwd, tool_name, f"retry({label},{attempt+1}/{max_attempts})", err_msg, detail)
            except Exception as e:
                last_error = f"{label}: {str(e)[:200]}"
                write_log(cwd, tool_name, f"retry({label},{attempt+1}/{max_attempts})", last_error, detail)

    write_log(cwd, tool_name, "manual(error)", last_error, detail)
    print(f"[Reviewer] All providers failed: {last_error}", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
