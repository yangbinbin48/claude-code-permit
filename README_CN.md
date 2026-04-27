# claude-code-permit

> 为 [Claude Code](https://docs.anthropic.com/en/docs/claude-code) 打造的 AI 自动权限审核 Hook。

[English](README.md) | [中文](README_CN.md)

受够了每次会话点几百次"允许"？**claude-code-permit** 使用第二个 LLM 自动审核权限请求 —— 安全操作自动放行并授予会话级权限，危险操作降级为手动确认。

## 特性

- **零延迟本地检查** —— 内部工具、项目内文件操作、安全 Bash 命令、只读 MCP 工具即时放行，无需网络请求
- **AI 智能审核** —— 未识别的 Bash 命令、外部文件访问、网页抓取等由第二个 LLM 评估
- **AskUserQuestion 保护** —— 始终降级为手动确认，AI 不会自动回答面向用户的提示
- **会话级权限** —— 同类操作审核通过后，本次会话内不再重复询问（等效于"始终允许"）
- **优雅降级** —— LLM 不可用时（限流、认证过期、超时）自动降级为手动确认。瞬态错误自动重试最多 3 次
- **可插拔 Provider** —— 内置 Codex CLI（ChatGPT 订阅）、Anthropic API、OpenAI API，易于扩展
- **SDK 指纹伪装** —— Anthropic 和 OpenAI Provider 发送 Roo Code 风格的 Stainless SDK 请求头，与官方 SDK 流量一致
- **零依赖** —— 纯 Python 标准库，无需 pip install

## 架构

```
工具调用
  |
  v
+----------------------------------+
|  PreToolUse (local_check.py)     |  本地快速判断，无网络请求
|  - 内部工具 -> 直接放行           |
|  - 工作目录内文件 -> 放行         |
|  - 安全 Bash 命令 -> 放行         |
|  - 只读 MCP 工具 -> 放行          |
|  - AskUserQuestion -> 交给审核    |
|  - 其他 -> 交给权限系统           |
+----------------+-----------------+
                 | "ask"
                 v
+----------------------------------+
|  Claude Code 权限系统             |  检查已有会话级权限
|                                  |  有 -> 直接放行
+----------------+-----------------+
                 | 无会话级权限
                 v
+----------------------------------+
|  PermissionRequest               |  调用 LLM 审核
|  (permission_reviewer.py)        |
|  - AskUserQuestion -> 拒绝        |
|  - 通过 -> 放行 +                 |
|    授予会话级权限                  |
|  - 拒绝 -> 弹出手动确认           |
|  - 出错/超时 -> 重试 ->           |
|    手动确认                       |
+----------------------------------+
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

### 多 Provider 配置文件模式

在 `~/.claude-auto-permit/` 目录下创建 JSON 文件，每个文件定义一个 provider 及其模型。该目录存在时优先于环境变量模式。

**配置文件格式** (`~/.claude-auto-permit/<名称>.json`)：

| 字段 | 是否必须 | 默认值 | 说明 |
|---|---|---|---|
| `provider` | 否 | 文件名 | 底层 provider 类型：`openai`、`anthropic` 或 `codex` |
| `priority` | 否 | `5` | Provider 优先级（0–10，越小越优先） |
| `api_key` | 是 | — | API Key |
| `base_url` | 否 | Provider 默认值 | 自定义端点（兼容 API） |
| `model` | 否 | — | 单模型（简写，等同于 `models` 只有一项） |
| `models` | 否 | — | 模型数组，每项可单独设优先级 |

**`models` 数组条目：**

| 字段 | 是否必须 | 默认值 | 说明 |
|---|---|---|---|
| `model` | 是 | — | 模型 ID |
| `priority` | 否 | `5` | 模型优先级（0–10，越小越优先） |

模型按 `(provider_priority, model_priority)` 二级排序依次尝试，一个失败自动切换下一个。每个 `(provider, model)` 组合独立不可用冷却。

**示例 — 多 provider 多模型：**

`~/.claude-auto-permit/glm.json`：
```json
{
  "provider": "openai",
  "priority": 3,
  "api_key": "your-key",
  "base_url": "https://open.bigmodel.cn/api/paas/v4/chat/completions",
  "models": [
    {"model": "glm-4-flash", "priority": 3},
    {"model": "glm-4.7", "priority": 5}
  ]
}
```

`~/.claude-auto-permit/modelscope.json`：
```json
{
  "provider": "openai",
  "priority": 5,
  "api_key": "your-key",
  "base_url": "https://api-inference.modelscope.cn/v1/chat/completions",
  "models": [
    {"model": "deepseek-ai/DeepSeek-V4-Flash", "priority": 3},
    {"model": "Qwen/Qwen3-Coder-480B-A35B-Instruct", "priority": 5}
  ]
}
```

**故障转移顺序：**
1. 尝试 `glm/glm-4-flash`（provider 优先级 3，model 优先级 3）
2. 失败 → 尝试 `glm/glm-4.7`（3, 5）
3. 失败 → 尝试 `modelscope/DeepSeek-V4-Flash`（5, 3）
4. 失败 → 尝试 `modelscope/Qwen3-Coder`（5, 5）
5. 全部失败 → 弹出手动确认

**诊断：** 运行 `python diagnose.py` 测试所有已配置模型。

### 本地自动放行（不调用 LLM）

#### 内部工具（始终放行）

`Task`、`WebSearch`、`Agent`、`TaskCreate`、`TaskUpdate`、`TaskGet`、`TaskList`、`TaskStop`、`EnterPlanMode`、`ExitPlanMode`、`EnterWorktree`、`Skill`、`TaskOutput`、`SendMessage`、`CronCreate`、`CronDelete`、`CronList`、`ScheduleWakeup` 等。

> **注意：** `AskUserQuestion` 被明确排除 —— 它始终需要用户手动交互。

#### 工作目录内文件操作

`Read`、`Write`、`Edit`、`Glob`、`Grep`、`NotebookEdit` —— 当目标路径在当前工作目录内时。

#### 安全 Bash 命令

以下命令（及其管道/链式组合）自动放行：

| 类别 | 命令 |
|---|---|
| 文件查看 | `ls`、`cat`、`tree`、`head`、`tail`、`less`、`more`、`file`、`stat` |
| 搜索 | `grep`、`egrep`、`fgrep`、`find`、`rg`、`ag`、`ack`、`which`、`whereis` |
| 文本处理（只读） | `wc`、`sort`、`uniq`、`cut`、`tr`、`awk`、`sed`、`diff`、`comm` |
| 输出 | `echo`、`printf` |
| Git（所有子命令） | `git` |
| 版本查询 | `python3`、`python`、`node`、`npm`、`pnpm`、`npx`、`go`、`rustc`、`cargo` |
| 系统信息（只读） | `ps`、`pgrep`、`netstat`、`ss`、`lsof`、`ip`、`uname`、`hostname`、`whoami`、`id`、`env`、`printenv`、`date`、`uptime` |
| 包管理（只读） | `pip`、`pip3`、`dpkg`、`rpm`、`dnf` |
| Shell 内建 | `cd`、`pwd`、`export`、`source`、`bash`、`sh`、`zsh` |
| 构建/运行工具 | `make`、`cmake`、`docker`、`kubectl`、`helm`、`yarn`、`bun`、`deno` |
| 其他安全命令 | `jq`、`yq`、`xargs`、`tee`、`mkdir`、`test`、`touch`、`cp`、`mv`、`chmod`、`chown`、`curl`、`wget`、`tar`、`unzip`、`gzip` |

#### 危险模式（本地始终拦截）

即使基础命令在安全列表中，以下模式也会触发 `ask` 交给审核：

- `rm -rf /` — 破坏性根目录删除
- `sudo rm` — 提权删除
- `> /etc/` — 写入系统配置
- `chmod 777` — 过度开放权限
- `git push --force` — 强制推送
- `curl ... | sh` / `wget ... | sh` — 管道远程执行

#### 只读 MCP 工具

匹配以下前缀的 MCP 工具自动放行：

- `mcp__plugin_claude-mem_mcp-search__` — 代码搜索
- `mcp__web-search-prime__` — 网页搜索
- `mcp__web-reader__` / `mcp__web_reader__` — 网页读取
- `mcp__4_5v_mcp__` — 图像分析
- `mcp__zread__` — GitHub 只读
- `mcp__zai-mcp-server__` — AI 数据分析
- `mcp__plugin_playwright_playwright__` — 浏览器自动化
- `mcp__plugin_superpowers-chrome_chrome__` — Chrome 浏览器

### AI 审核范围

未匹配本地规则的所有操作 —— 未识别的 Bash 命令、项目外文件操作、MCP 写操作等。审核规则：

| 决策 | 条件 |
|---|---|
| **放行** | 构建/测试/lint、git 常规操作、包管理、开发服务器、文档网站访问 |
| **拒绝** | `rm -rf /`、`git push --force` 到 main、访问密钥、可疑网络请求、系统配置修改 |
| **默认** | 不确定时倾向放行 —— 开发者在自己的机器上工作 |

可通过编辑 `permission_reviewer.py` 中的 `REVIEW_PROMPT_TEMPLATE` 自定义规则。

## 错误处理与重试

权限审核器内置重试机制：

- **瞬态错误**（超时、网络）—— 最多重试 3 次，延迟递增（0s、1s、2s）
- **服务级错误**（401、403、500、配额、计费）—— 标记 Provider 不可用，立即降级为手动确认
- **Provider 冷却期** —— 标记不可用后 10 分钟内跳过 LLM 调用（可通过源码中 `UNAVAILABLE_TTL` 配置）

## 日志

所有决策记录在项目目录下的 `.claude_permission.log`：

```
[2026-04-27 09:15:00] tool=Edit decision=allow reason=Target within cwd detail=src/main.py
[2026-04-27 09:15:10] tool=Bash decision=allow reason=Known safe command detail=npm run build
[2026-04-27 09:15:20] tool=Bash decision=allow+session reason=Standard build detail=npm install
[2026-04-27 09:15:30] tool=Bash decision=manual(deny) reason=Destructive op detail=rm -rf /
[2026-04-27 09:15:40] tool=Bash decision=retry(2/3) reason=Timeout detail=some command
```

此文件已在 `.gitignore` 中排除，不会被提交。

## 项目结构

```
claude-code-permit/
├── local_check.py           # PreToolUse Hook — 本地快速判断
├── permission_reviewer.py   # PermissionRequest Hook — AI 审核 + 多 Provider 故障转移
├── diagnose.py              # 诊断工具 — 测试所有已配置模型
├── providers/
│   ├── __init__.py          # Provider 注册表 + 配置加载器
│   ├── codex.py             # Codex CLI（ChatGPT 订阅）
│   ├── anthropic_api.py     # Anthropic API（标准库 + Roo Code 请求头）
│   └── openai_api.py        # OpenAI API（+ 兼容 API + Roo Code 请求头）
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
