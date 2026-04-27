# claude-code-permit

> AI-powered permission auto-review hook for [Claude Code](https://docs.anthropic.com/en/docs/claude-code).

[English](README.md) | [中文](README_CN.md)

Tired of clicking "Allow" hundreds of times per session? **claude-code-permit** uses a secondary LLM to automatically review permission requests — approving safe operations with session-level persistence, and falling back to manual confirmation for anything risky.

## Features

- **Zero-latency local checks** — Internal tools, in-project file ops, safe Bash commands, and read-only MCP tools are auto-approved instantly, no network needed
- **AI-powered review** — Unrecognized Bash commands, external file access, web fetches, etc. are evaluated by a secondary LLM
- **AskUserQuestion protection** — Always falls back to manual confirmation; the AI will never auto-approve user-facing prompts
- **Session-level permissions** — Once approved, the same type of operation won't be asked again in the current session (equivalent to "Yes, don't ask again")
- **Graceful degradation** — If the LLM provider is down (rate limit, auth expired, timeout), falls back to manual confirmation instead of blocking. Retries up to 3 times with backoff for transient errors
- **Pluggable providers** — Ships with Codex CLI (ChatGPT subscription), Anthropic API, and OpenAI API. Easy to add your own
- **SDK fingerprint masking** — Anthropic and OpenAI providers send Roo Code-style Stainless SDK headers to blend in with official SDK traffic
- **No dependencies** — Pure Python stdlib, no pip install needed

## Architecture

```
Tool call
  |
  v
+----------------------------------+
|  PreToolUse (local_check.py)     |  Fast, no network
|  - Internal tools -> allow       |
|  - File ops in cwd -> allow      |
|  - Safe Bash commands -> allow   |
|  - Read-only MCP tools -> allow  |
|  - AskUserQuestion -> ask        |
|  - Everything else -> ask        |
+----------------+-----------------+
                 | "ask"
                 v
+----------------------------------+
|  Claude Code Permission System   |  Checks existing session
|                                  |  permissions -> allow
+----------------+-----------------+
                 | no session permission found
                 v
+----------------------------------+
|  PermissionRequest               |  Calls LLM provider
|  (permission_reviewer.py)        |
|  - AskUserQuestion -> deny       |
|  - Approve -> allow +            |
|    grant session permission      |
|  - Deny -> manual dialog         |
|  - Error/timeout -> retry ->     |
|    manual dialog                 |
+----------------------------------+
```

## Quick Start

### 1. Clone

```bash
git clone https://github.com/ltz1990/claude-code-permit.git
cd claude-code-permit
```

### 2. Choose an LLM Provider

<details>
<summary><b>Codex CLI</b> (default) — ChatGPT subscription, no API key</summary>

```bash
npm install -g @openai/codex
codex login
```

</details>

<details>
<summary><b>Anthropic API</b></summary>

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
export PERMIT_PROVIDER="anthropic"
# Optional: export ANTHROPIC_MODEL="claude-sonnet-4-5-20250514"
```

</details>

<details>
<summary><b>OpenAI API</b></summary>

```bash
export OPENAI_API_KEY="sk-..."
export PERMIT_PROVIDER="openai"
# Optional: export OPENAI_MODEL="gpt-4o-mini"
```

</details>

<details>
<summary><b>OpenAI-compatible APIs</b> (DeepSeek, local models, etc.)</summary>

```bash
export OPENAI_API_KEY="your-key"
export OPENAI_BASE_URL="https://api.deepseek.com/v1/chat/completions"
export OPENAI_MODEL="deepseek-chat"
export PERMIT_PROVIDER="openai"
```

</details>

### 3. Configure Claude Code Hooks

Add to `~/.claude/settings.json` (global) or `.claude/settings.json` (project-level):

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": ".*",
        "hooks": [
          {
            "type": "command",
            "command": "python3 /path/to/claude-code-permit/local_check.py",
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
            "command": "python3 /path/to/claude-code-permit/permission_reviewer.py",
            "timeout": 30
          }
        ]
      }
    ]
  }
}
```

> Replace `/path/to/claude-code-permit/` with the actual clone path.

That's it. Start a Claude Code session and permissions will be auto-reviewed.

## Configuration

### Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `PERMIT_PROVIDER` | No | `codex` | Provider: `codex`, `anthropic`, or `openai` |
| `ANTHROPIC_API_KEY` | For `anthropic` | — | Anthropic API key |
| `ANTHROPIC_MODEL` | No | `claude-sonnet-4-5-20250514` | Anthropic model ID |
| `OPENAI_API_KEY` | For `openai` | — | OpenAI API key |
| `OPENAI_MODEL` | No | `gpt-4o-mini` | OpenAI model ID |
| `OPENAI_BASE_URL` | No | OpenAI default | Custom endpoint for compatible APIs |

### What Gets Auto-Approved Locally (no LLM call)

#### Internal Tools (always allow)

`Task`, `WebSearch`, `Agent`, `TaskCreate`, `TaskUpdate`, `TaskGet`, `TaskList`, `TaskStop`, `EnterPlanMode`, `ExitPlanMode`, `EnterWorktree`, `Skill`, `TaskOutput`, `SendMessage`, `CronCreate`, `CronDelete`, `CronList`, `ScheduleWakeup`, etc.

> **Note:** `AskUserQuestion` is explicitly excluded — it always requires manual user interaction.

#### File Operations Within CWD

`Read`, `Write`, `Edit`, `Glob`, `Grep`, `NotebookEdit` — when the target path is inside the current working directory.

#### Safe Bash Commands

The following commands (and pipes/chains of them) are auto-approved:

| Category | Commands |
|---|---|
| File viewing | `ls`, `cat`, `tree`, `head`, `tail`, `less`, `more`, `file`, `stat` |
| Search | `grep`, `egrep`, `fgrep`, `find`, `rg`, `ag`, `ack`, `which`, `whereis` |
| Text processing (read-only) | `wc`, `sort`, `uniq`, `cut`, `tr`, `awk`, `sed`, `diff`, `comm` |
| Output | `echo`, `printf` |
| Git (all subcommands) | `git` |
| Version check | `python3`, `python`, `node`, `npm`, `pnpm`, `npx`, `go`, `rustc`, `cargo` |
| System info (read-only) | `ps`, `pgrep`, `netstat`, `ss`, `lsof`, `ip`, `uname`, `hostname`, `whoami`, `id`, `env`, `printenv`, `date`, `uptime` |
| Package management (read-only) | `pip`, `pip3`, `dpkg`, `rpm`, `dnf` |
| Shell builtins | `cd`, `pwd`, `export`, `source`, `bash`, `sh`, `zsh` |
| Build/run tools | `make`, `cmake`, `docker`, `kubectl`, `helm`, `yarn`, `bun`, `deno` |
| Other safe | `jq`, `yq`, `xargs`, `tee`, `mkdir`, `test`, `touch`, `cp`, `mv`, `chmod`, `chown`, `curl`, `wget`, `tar`, `unzip`, `gzip` |

#### Dangerous Patterns (always blocked locally)

These patterns trigger an `ask` decision even if the base command is in the safe list:

- `rm -rf /` — destructive root deletion
- `sudo rm` — privileged deletion
- `> /etc/` — writing to system config
- `chmod 777` — overly permissive
- `git push --force` — force push
- `curl ... | sh` / `wget ... | sh` — piped remote execution

#### Read-only MCP Tools

MCP tools matching these prefixes are auto-approved:

- `mcp__plugin_claude-mem_mcp-search__` — code search
- `mcp__web-search-prime__` — web search
- `mcp__web-reader__` / `mcp__web_reader__` — web reader
- `mcp__4_5v_mcp__` — image analysis
- `mcp__zread__` — GitHub read-only
- `mcp__zai-mcp-server__` — AI data analysis
- `mcp__plugin_playwright_playwright__` — browser automation
- `mcp__plugin_superpowers-chrome_chrome__` — Chrome browser

### What Gets AI-Reviewed

Everything that doesn't match the local rules — unrecognized Bash commands, file operations outside the project, MCP write tools, etc. The LLM reviewer follows these rules:

| Decision | When |
|---|---|
| **APPROVE** | Build/test/lint, git operations, package management, dev servers, doc site fetches |
| **DENY** | `rm -rf /`, `git push --force` to main, secret access, suspicious network, system config changes |
| **Default** | When unsure, approve — you're working on your own machine |

Customize rules by editing `REVIEW_PROMPT_TEMPLATE` in `permission_reviewer.py`.

## Error Handling & Retry

The permission reviewer has a built-in retry mechanism:

- **Transient errors** (timeout, network) — retries up to 3 times with delays (0s, 1s, 2s)
- **Service errors** (401, 403, 500, quota, billing) — marks the provider as unavailable and falls back to manual immediately
- **Provider cooldown** — once marked unavailable, skips LLM calls for 10 minutes (configurable via `UNAVAILABLE_TTL` in source)

## Logging

All decisions are logged to `.claude_permission.log` in your project directory:

```
[2026-04-27 09:15:00] tool=Edit decision=allow reason=Target within cwd detail=src/main.py
[2026-04-27 09:15:10] tool=Bash decision=allow reason=Known safe command detail=npm run build
[2026-04-27 09:15:20] tool=Bash decision=allow+session reason=Standard build detail=npm install
[2026-04-27 09:15:30] tool=Bash decision=manual(deny) reason=Destructive op detail=rm -rf /
[2026-04-27 09:15:40] tool=Bash decision=retry(2/3) reason=Timeout detail=some command
```

This file is in `.gitignore` and won't be committed.

## Project Structure

```
claude-code-permit/
├── local_check.py           # PreToolUse hook — fast local decisions
├── permission_reviewer.py   # PermissionRequest hook — AI review + retry
├── providers/
│   ├── __init__.py          # Provider registry
│   ├── codex.py             # Codex CLI (ChatGPT subscription)
│   ├── anthropic_api.py     # Anthropic API (stdlib + Roo Code headers)
│   └── openai_api.py        # OpenAI API (+ compatible APIs + Roo Code headers)
└── .gitignore
```

## Adding a Custom Provider

1. Create `providers/my_provider.py`:

```python
def review(prompt: str, timeout: int = 25) -> str:
    """
    Send the review prompt to your LLM and return the raw response text.
    Response must contain JSON: {"decision": "approve"|"deny", "reason": "..."}

    Raises RuntimeError on service errors, subprocess.TimeoutExpired on timeout.
    """
    ...
```

2. Register in `providers/__init__.py`:

```python
from providers.my_provider import review as my_review

PROVIDERS = {
    ...
    "my_provider": my_review,
}
```

3. Set `PERMIT_PROVIDER=my_provider`.

## Requirements

- Python 3.10+
- No external dependencies (stdlib only)
- One configured LLM provider

## Limitations

- Session permissions reset when Claude Code restarts
- Provider unavailability cooldown: 10 minutes (configurable via `UNAVAILABLE_TTL`)
- Large tool inputs are truncated to 3000 characters for the review prompt

## License

MIT

## Contributing

Issues and PRs welcome at [github.com/ltz1990/claude-code-permit](https://github.com/ltz1990/claude-code-permit).
