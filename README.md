# claude-code-permit

AI-powered permission auto-review hook for [Claude Code](https://docs.anthropic.com/en/docs/claude-code). Uses a secondary LLM to automatically approve or escalate tool calls, with session-level permission granting to minimize repeated prompts.

## Why?

Claude Code asks for permission before running shell commands, accessing files outside the project, fetching URLs, etc. This is great for safety, but can be disruptive during focused development sessions where you're approving the same types of operations repeatedly.

**claude-code-permit** adds an AI reviewer that automatically evaluates each permission request and either approves it (with session-level "don't ask again" persistence) or falls back to the normal manual dialog.

## How It Works

The system uses two Claude Code hooks working together:

```
Tool call
  │
  ▼
┌─────────────────────────────┐
│  PreToolUse (local_check)   │  Fast, no network
│  ─────────────────────────  │
│  Internal tools → allow     │
│  File ops in cwd → allow    │
│  Everything else → ask      │
└──────────────┬──────────────┘
               │ "ask"
               ▼
┌─────────────────────────────┐
│  Claude Code Permission     │  Checks session permissions
│  System                     │  already granted → allow
└──────────────┬──────────────┘
               │ no session permission
               ▼
┌─────────────────────────────┐
│  PermissionRequest          │  Calls LLM provider
│  (permission_reviewer)      │
│  ─────────────────────────  │
│  LLM approves → allow +    │
│    grant session permission │
│  LLM denies → manual dialog│
│  Error/timeout → manual     │
└─────────────────────────────┘
```

**Key design decisions:**
- **Two-layer architecture**: Fast local checks handle the majority of tool calls with zero latency. The LLM reviewer only runs when the permission dialog would actually appear.
- **Session-level permissions**: When the LLM approves a tool call, the hook grants a session-level permission (equivalent to the user selecting "Yes, don't ask again"). This means the LLM only reviews each *type* of operation once per session.
- **Graceful degradation**: If the LLM provider is unavailable (rate limit, auth expired, timeout), the hook falls back to the normal manual permission dialog — never blocks your workflow.

## Project Structure

```
claude-code-permit/
├── local_check.py           # PreToolUse hook — fast local decisions
├── permission_reviewer.py   # PermissionRequest hook — AI review
├── providers/
│   ├── __init__.py          # Provider registry
│   ├── codex.py             # Codex CLI (ChatGPT subscription)
│   ├── anthropic_api.py     # Anthropic API
│   └── openai_api.py        # OpenAI API (+ compatible APIs)
└── .gitignore
```

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/user/claude-code-permit.git
cd claude-code-permit
```

### 2. Set up an LLM provider

Choose one of the supported providers:

#### Option A: Codex CLI (default) — uses ChatGPT subscription, no API key

```bash
# Install Codex CLI
npm install -g @anthropic-ai/codex  # or see https://github.com/openai/codex

# Log in with your ChatGPT account
codex login
```

#### Option B: Anthropic API

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
export PERMIT_PROVIDER="anthropic"
# Optional: export ANTHROPIC_MODEL="claude-sonnet-4-5-20250514"
```

#### Option C: OpenAI API

```bash
export OPENAI_API_KEY="sk-..."
export PERMIT_PROVIDER="openai"
# Optional: export OPENAI_MODEL="gpt-4o-mini"
```

#### Option D: OpenAI-compatible APIs (DeepSeek, local models, etc.)

```bash
export OPENAI_API_KEY="your-key"
export OPENAI_BASE_URL="https://api.deepseek.com/v1/chat/completions"
export OPENAI_MODEL="deepseek-chat"
export PERMIT_PROVIDER="openai"
```

### 3. Configure Claude Code hooks

Add the following to your `~/.claude/settings.json` (or project-level `.claude/settings.json`):

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": ".*",
        "hooks": [
          {
            "type": "command",
            "command": "python3 /absolute/path/to/claude-code-permit/local_check.py",
            "timeout": 5
          }
        ]
      }
    ],
    "PermissionRequest": [
      {
        "matcher": ".*",
        "hooks": [
          {
            "type": "command",
            "command": "python3 /absolute/path/to/claude-code-permit/permission_reviewer.py",
            "timeout": 30
          }
        ]
      }
    ]
  }
}
```

Replace `/absolute/path/to/claude-code-permit/` with the actual path where you cloned the repository.

## Configuration

### Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `PERMIT_PROVIDER` | No | `codex` | LLM provider: `codex`, `anthropic`, or `openai` |
| `ANTHROPIC_API_KEY` | For `anthropic` | — | Anthropic API key |
| `ANTHROPIC_MODEL` | No | `claude-sonnet-4-5-20250514` | Anthropic model ID |
| `OPENAI_API_KEY` | For `openai` | — | OpenAI API key |
| `OPENAI_MODEL` | No | `gpt-4o-mini` | OpenAI model ID |
| `OPENAI_BASE_URL` | No | `https://api.openai.com/v1/chat/completions` | Custom endpoint for compatible APIs |

### Review Rules

The LLM reviewer uses a built-in prompt with these rules:

- **APPROVE**: build/test/lint, git operations, package management, dev servers, project build tools, documentation fetches
- **DENY**: destructive operations (`rm -rf /`, `git push --force`), secret access, suspicious network activity, system-level modifications, file access outside the project
- **Default**: When unsure, approve — the developer is working on their own machine

You can customize the review rules by editing the `REVIEW_PROMPT_TEMPLATE` in `permission_reviewer.py`.

### Local Check Rules

The PreToolUse hook (`local_check.py`) auto-allows:
- Internal Claude Code tools: `Task`, `WebSearch`, `AskUserQuestion`, `EnterPlanMode`, etc.
- File operations (`Read`, `Write`, `Edit`, `Glob`, `Grep`, `NotebookEdit`) targeting paths within the current working directory

Everything else is delegated to Claude Code's permission system, which may trigger the AI reviewer.

## Logging

All permission decisions are logged to `.claude_permission.log` in the current working directory:

```
[2026-02-20 22:28:26] tool=Read decision=allow reason=Target within cwd detail=/project/src/main.py
[2026-02-20 22:28:35] tool=Bash decision=allow+session reason=Standard dev command detail=npm run build
[2026-02-20 22:28:40] tool=Bash decision=manual(deny) reason=Destructive operation detail=rm -rf /
```

This file is listed in `.gitignore` and won't be committed to your repository.

## Adding a Custom Provider

Create a new file in `providers/` implementing the `review` function:

```python
# providers/my_provider.py

def review(prompt: str, timeout: int = 25) -> str:
    """
    Send the review prompt to your LLM and return the raw response text.

    Args:
        prompt: The review prompt containing tool call details
        timeout: Maximum seconds to wait

    Returns:
        Raw LLM response text (must contain JSON with "decision" and "reason")

    Raises:
        RuntimeError: On service errors (triggers unavailability cooldown)
        subprocess.TimeoutExpired: On timeout
    """
    # Your implementation here
    ...
```

Then register it in `providers/__init__.py`:

```python
from providers.my_provider import review as my_review

PROVIDERS = {
    # ...existing providers...
    "my_provider": my_review,
}
```

Set `PERMIT_PROVIDER=my_provider` to use it.

## Requirements

- Python 3.10+ (uses `str | None` type syntax)
- No external Python dependencies (stdlib only)
- One of the supported LLM providers configured

## Limitations

- Session permissions are per-session — they reset when you restart Claude Code
- The unavailability cooldown is 10 minutes (configurable via `UNAVAILABLE_TTL` in `permission_reviewer.py`)
- The review prompt is truncated to 3000 characters for very large tool inputs

## License

MIT
