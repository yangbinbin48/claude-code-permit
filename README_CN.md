# claude-code-permit

> 为 [Claude Code](https://docs.anthropic.com/en/docs/claude-code) 打造的 AI 自动权限审核 Hook。

[English](README.md) | [中文](README_CN.md)

受够了每次会话点几百次"允许"？**claude-code-permit** 使用第二个 LLM 自动审核权限请求 —— 安全操作自动放行并授予会话级权限，危险操作降级为手动确认。

## 特性

- **零延迟本地检查** —— 内部工具和项目内文件操作即时放行，无需网络请求
- **AI 智能审核** —— Bash 命令、外部文件访问、网页抓取等由第二个 LLM 评估
- **会话级权限** —— 同类操作审核通过后，本次会话内不再重复询问（等效于"始终允许"）
- **优雅降级** —— LLM 不可用时（限流、认证过期、超时）自动降级为手动确认，不会阻断工作
- **可插拔 Provider** —— 内置 Codex CLI（ChatGPT 订阅）、Anthropic API、OpenAI API，易于扩展
- **零依赖** —— 纯 Python 标准库，无需 pip install

## 架构

```
工具调用
  |
  v
+-----------------------------+
|  PreToolUse (local_check)   |  本地快速判断，无网络请求
|  - 内部工具 -> 直接放行      |
|  - 工作目录内文件 -> 放行    |
|  - 其他 -> 交给权限系统      |
+-------------+---------------+
              | "ask"
              v
+-----------------------------+
|  Claude Code 权限系统        |  检查已有会话级权限
|                             |  有 -> 直接放行
+-------------+---------------+
              | 无会话级权限
              v
+-----------------------------+
|  PermissionRequest          |  调用 LLM 审核
|  (permission_reviewer)      |
|  - 通过 -> 放行 +           |
|    授予会话级权限            |
|  - 拒绝 -> 弹出手动确认     |
|  - 出错/超时 -> 手动确认     |
+-----------------------------+
```

## 快速开始

### 1. 克隆仓库

```bash
git clone https://github.com/ltz1990/claude-code-permit.git
cd claude-code-permit
```

### 2. 选择 LLM Provider

<details>
<summary><b>Codex CLI</b>（默认）—— ChatGPT 订阅，无需 API Key</summary>

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
# 可选：export ANTHROPIC_MODEL="claude-sonnet-4-5-20250514"
```

</details>

<details>
<summary><b>OpenAI API</b></summary>

```bash
export OPENAI_API_KEY="sk-..."
export PERMIT_PROVIDER="openai"
# 可选：export OPENAI_MODEL="gpt-4o-mini"
```

</details>

<details>
<summary><b>OpenAI 兼容 API</b>（DeepSeek、本地模型等）</summary>

```bash
export OPENAI_API_KEY="your-key"
export OPENAI_BASE_URL="https://api.deepseek.com/v1/chat/completions"
export OPENAI_MODEL="deepseek-chat"
export PERMIT_PROVIDER="openai"
```

</details>

### 3. 配置 Claude Code Hooks

在 `~/.claude/settings.json`（全局）或 `.claude/settings.json`（项目级）中添加：

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": ".*",
        "hooks": [
          {
            "type": "command",
            "command": "python3 /你的路径/claude-code-permit/local_check.py",
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
            "command": "python3 /你的路径/claude-code-permit/permission_reviewer.py",
            "timeout": 30
          }
        ]
      }
    ]
  }
}
```

> 将 `/你的路径/claude-code-permit/` 替换为实际克隆路径。

配置完成，启动 Claude Code 会话即可自动审核权限。

## 配置项

### 环境变量

| 变量 | 是否必须 | 默认值 | 说明 |
|---|---|---|---|
| `PERMIT_PROVIDER` | 否 | `codex` | Provider：`codex`、`anthropic` 或 `openai` |
| `ANTHROPIC_API_KEY` | 使用 `anthropic` 时 | — | Anthropic API Key |
| `ANTHROPIC_MODEL` | 否 | `claude-sonnet-4-5-20250514` | Anthropic 模型 ID |
| `OPENAI_API_KEY` | 使用 `openai` 时 | — | OpenAI API Key |
| `OPENAI_MODEL` | 否 | `gpt-4o-mini` | OpenAI 模型 ID |
| `OPENAI_BASE_URL` | 否 | OpenAI 默认 | 自定义端点（兼容 API） |

### 本地自动放行（不调用 LLM）

| 类别 | 示例 |
|---|---|
| 内部工具 | `Task`、`WebSearch`、`AskUserQuestion`、`EnterPlanMode`、`TaskCreate` 等 |
| 工作目录内文件操作 | `Read`、`Write`、`Edit`、`Glob`、`Grep`、`NotebookEdit` 且目标在项目内 |

### AI 审核范围

其他所有操作 —— 包括 `Bash` 命令、项目外文件操作、`WebFetch` 等。审核规则：

| 决策 | 条件 |
|---|---|
| **放行** | 构建/测试/lint、git 常规操作、包管理、开发服务器、文档网站访问 |
| **拒绝** | `rm -rf /`、`git push --force` 到 main、访问密钥、可疑网络请求、系统配置修改 |
| **默认** | 不确定时倾向放行 —— 开发者在自己的机器上工作 |

可通过编辑 `permission_reviewer.py` 中的 `REVIEW_PROMPT_TEMPLATE` 自定义规则。

## 日志

所有决策记录在项目目录下的 `.claude_permission.log`：

```
[2026-02-20 14:30:01] tool=Edit decision=allow reason=Target within cwd detail=src/main.py
[2026-02-20 14:30:15] tool=Bash decision=allow+session reason=Standard build detail=npm run build
[2026-02-20 14:30:22] tool=Bash decision=manual(deny) reason=Destructive op detail=rm -rf /
```

此文件已在 `.gitignore` 中排除，不会被提交。

## 项目结构

```
claude-code-permit/
├── local_check.py           # PreToolUse Hook — 本地快速判断
├── permission_reviewer.py   # PermissionRequest Hook — AI 审核
├── providers/
│   ├── __init__.py          # Provider 注册表
│   ├── codex.py             # Codex CLI（ChatGPT 订阅）
│   ├── anthropic_api.py     # Anthropic API（纯标准库）
│   └── openai_api.py        # OpenAI API（+ 兼容 API）
└── .gitignore
```

## 添加自定义 Provider

1. 创建 `providers/my_provider.py`：

```python
def review(prompt: str, timeout: int = 25) -> str:
    """
    将审核 prompt 发送给 LLM 并返回原始响应文本。
    响应须包含 JSON：{"decision": "approve"|"deny", "reason": "..."}

    服务错误抛出 RuntimeError，超时抛出 subprocess.TimeoutExpired。
    """
    ...
```

2. 在 `providers/__init__.py` 中注册：

```python
from providers.my_provider import review as my_review

PROVIDERS = {
    ...
    "my_provider": my_review,
}
```

3. 设置 `PERMIT_PROVIDER=my_provider`。

## 系统要求

- Python 3.10+
- 无外部依赖（纯标准库）
- 已配置至少一个 LLM Provider

## 已知限制

- 会话级权限在 Claude Code 重启后重置
- Provider 不可用冷却期：10 分钟（可通过 `UNAVAILABLE_TTL` 配置）
- 超大工具输入会被截断至 3000 字符

## 许可证

MIT

## 参与贡献

欢迎在 [github.com/ltz1990/claude-code-permit](https://github.com/ltz1990/claude-code-permit) 提交 Issue 和 PR。
