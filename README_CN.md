# claude-code-permit

[English](README.md) | 中文

为 [Claude Code](https://docs.anthropic.com/en/docs/claude-code) 打造的 AI 自动权限审核 Hook。使用第二个 LLM 自动审批或升级工具调用请求，并通过会话级权限授予减少重复询问。

## 为什么需要它？

Claude Code 在执行 Shell 命令、访问项目外文件、抓取网页等操作前都会弹出权限确认。这对安全很有帮助，但在专注开发时反复点击"允许"会打断工作流。

**claude-code-permit** 引入一个 AI 审核员，自动评估每个权限请求：
- 审核通过 → 自动放行 + 授予会话级权限（等效于用户选择"始终允许"）
- 审核拒绝 / 超时 / 出错 → 降级为手动确认弹窗，不会阻断工作

## 工作原理

系统由两个 Claude Code Hook 协同工作：

```
工具调用
  │
  ▼
┌─────────────────────────────┐
│  PreToolUse (local_check)   │  本地快速判断，无网络请求
│  ─────────────────────────  │
│  内部工具 → 直接放行         │
│  工作目录内文件操作 → 放行   │
│  其他 → 交给权限系统         │
└──────────────┬──────────────┘
               │ "ask"
               ▼
┌─────────────────────────────┐
│  Claude Code 权限系统        │  检查是否已有会话级权限
│                             │  有 → 直接放行
└──────────────┬──────────────┘
               │ 无会话级权限
               ▼
┌─────────────────────────────┐
│  PermissionRequest          │  调用 LLM 审核
│  (permission_reviewer)      │
│  ─────────────────────────  │
│  LLM 通过 → 放行 +          │
│    授予会话级权限            │
│  LLM 拒绝 → 弹出手动确认    │
│  出错/超时 → 弹出手动确认    │
└─────────────────────────────┘
```

**核心设计：**
- **两层架构**：本地检查处理绝大多数工具调用（零延迟），LLM 审核仅在真正需要弹窗时才运行
- **会话级权限**：LLM 通过审核后会授予会话级权限（等效于"始终允许"），同类操作在本次会话中只审核一次
- **优雅降级**：LLM 不可用时（限流、认证过期、超时）自动降级为手动确认，不会阻断工作

## 项目结构

```
claude-code-permit/
├── local_check.py           # PreToolUse Hook — 本地快速判断
├── permission_reviewer.py   # PermissionRequest Hook — AI 审核
├── providers/
│   ├── __init__.py          # Provider 注册表
│   ├── codex.py             # Codex CLI（ChatGPT 订阅）
│   ├── anthropic_api.py     # Anthropic API
│   └── openai_api.py        # OpenAI API（+ 兼容 API）
└── .gitignore
```

## 安装

### 1. 克隆仓库

```bash
git clone https://github.com/user/claude-code-permit.git
cd claude-code-permit
```

### 2. 配置 LLM Provider

选择以下任一方式：

#### 方式 A：Codex CLI（默认）— 使用 ChatGPT 订阅，无需 API Key

```bash
# 安装 Codex CLI
npm install -g @anthropic-ai/codex  # 或参考 https://github.com/openai/codex

# 登录 ChatGPT 账号
codex login
```

#### 方式 B：Anthropic API

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
export PERMIT_PROVIDER="anthropic"
# 可选：export ANTHROPIC_MODEL="claude-sonnet-4-5-20250514"
```

#### 方式 C：OpenAI API

```bash
export OPENAI_API_KEY="sk-..."
export PERMIT_PROVIDER="openai"
# 可选：export OPENAI_MODEL="gpt-4o-mini"
```

#### 方式 D：OpenAI 兼容 API（DeepSeek、本地模型等）

```bash
export OPENAI_API_KEY="your-key"
export OPENAI_BASE_URL="https://api.deepseek.com/v1/chat/completions"
export OPENAI_MODEL="deepseek-chat"
export PERMIT_PROVIDER="openai"
```

### 3. 配置 Claude Code Hooks

在 `~/.claude/settings.json`（或项目级 `.claude/settings.json`）中添加：

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": ".*",
        "hooks": [
          {
            "type": "command",
            "command": "python3 /你的绝对路径/claude-code-permit/local_check.py",
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
            "command": "python3 /你的绝对路径/claude-code-permit/permission_reviewer.py",
            "timeout": 30
          }
        ]
      }
    ]
  }
}
```

将 `/你的绝对路径/claude-code-permit/` 替换为仓库实际克隆路径。

## 配置项

### 环境变量

| 变量 | 是否必须 | 默认值 | 说明 |
|---|---|---|---|
| `PERMIT_PROVIDER` | 否 | `codex` | LLM Provider：`codex`、`anthropic` 或 `openai` |
| `ANTHROPIC_API_KEY` | 使用 `anthropic` 时 | — | Anthropic API Key |
| `ANTHROPIC_MODEL` | 否 | `claude-sonnet-4-5-20250514` | Anthropic 模型 ID |
| `OPENAI_API_KEY` | 使用 `openai` 时 | — | OpenAI API Key |
| `OPENAI_MODEL` | 否 | `gpt-4o-mini` | OpenAI 模型 ID |
| `OPENAI_BASE_URL` | 否 | `https://api.openai.com/v1/chat/completions` | 自定义端点（用于兼容 API） |

### 审核规则

LLM 审核员使用内置 Prompt，遵循以下规则：

- **放行**：构建/测试/lint、git 常规操作、包管理、开发服务器、项目构建工具、文档网站访问
- **拒绝**：破坏性操作（`rm -rf /`、`git push --force`）、访问密钥文件、可疑网络请求、系统级修改、访问项目外敏感文件
- **默认**：不确定时倾向放行 — 开发者在自己的机器上工作

可通过编辑 `permission_reviewer.py` 中的 `REVIEW_PROMPT_TEMPLATE` 自定义审核规则。

### 本地检查规则

PreToolUse Hook（`local_check.py`）自动放行：
- Claude Code 内部工具：`Task`、`WebSearch`、`AskUserQuestion`、`EnterPlanMode` 等
- 目标路径在当前工作目录内的文件操作（`Read`、`Write`、`Edit`、`Glob`、`Grep`、`NotebookEdit`）

其他操作交给 Claude Code 权限系统处理，可能触发 AI 审核。

## 日志

所有权限决策记录在当前工作目录下的 `.claude_permission.log` 中：

```
[2026-02-20 22:28:26] tool=Read decision=allow reason=目标在工作目录内 detail=/project/src/main.py
[2026-02-20 22:28:35] tool=Bash decision=allow+session reason=常规开发命令 detail=npm run build
[2026-02-20 22:28:40] tool=Bash decision=manual(deny) reason=破坏性操作 detail=rm -rf /
```

此文件已在 `.gitignore` 中排除，不会被提交。

## 添加自定义 Provider

在 `providers/` 下新建文件，实现 `review` 函数：

```python
# providers/my_provider.py

def review(prompt: str, timeout: int = 25) -> str:
    """
    将审核 prompt 发送给你的 LLM 并返回原始响应文本。

    参数:
        prompt: 包含工具调用详情的审核 prompt
        timeout: 最大等待秒数

    返回:
        LLM 原始响应文本（须包含 "decision" 和 "reason" 的 JSON）

    异常:
        RuntimeError: 服务错误（触发不可用冷却期）
        subprocess.TimeoutExpired: 超时
    """
    # 你的实现
    ...
```

然后在 `providers/__init__.py` 中注册：

```python
from providers.my_provider import review as my_review

PROVIDERS = {
    # ...已有 providers...
    "my_provider": my_review,
}
```

设置 `PERMIT_PROVIDER=my_provider` 即可使用。

## 系统要求

- Python 3.10+（使用了 `str | None` 类型语法）
- 无外部 Python 依赖（仅使用标准库）
- 已配置至少一个 LLM Provider

## 已知限制

- 会话级权限仅在当前会话有效，重启 Claude Code 后重置
- Provider 不可用冷却期为 10 分钟（可在 `permission_reviewer.py` 中修改 `UNAVAILABLE_TTL`）
- 超大工具输入会被截断至 3000 字符

## 许可证

MIT
