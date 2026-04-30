#!/usr/bin/env python3
"""
PreToolUse Hook: 本地快速判断（不走网络）

- 内部安全工具 → "allow" 直接放行
- 文件操作且目标在 cwd 内 → "allow" 直接放行
- 其他 → "ask" 交给权限系统（→ 可能触发 PermissionRequest hook）
"""

import json
import os
import re
import shlex
import sys
from datetime import datetime


LOG_FILE_NAME = ".claude_permission.log"


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

FILE_TOOL_PATH_FIELDS = {
    "Edit": "file_path",
    "Write": "file_path",
    "Read": "file_path",
    "Glob": "path",
    "Grep": "path",
    "NotebookEdit": "notebook_path",
}

ALWAYS_ALLOW_TOOLS = {
    "Task", "WebSearch", "Agent",
    "TaskCreate", "TaskUpdate", "TaskGet", "TaskList", "TaskStop",
    "EnterPlanMode", "ExitPlanMode",
    "EnterWorktree", "Skill", "TaskOutput",
    "SendMessage", "TeamCreate", "TeamDelete",
    "CronCreate", "CronDelete", "CronList",
    "ScheduleWakeup",
}


def is_within_cwd(file_path: str, cwd: str) -> bool:
    try:
        real_file = os.path.realpath(file_path)
        real_cwd = os.path.realpath(cwd)
        return real_file.startswith(real_cwd + os.sep) or real_file == real_cwd
    except Exception:
        return False


def output(decision: str, reason: str):
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": decision,
            "permissionDecisionReason": reason
        }
    }))


def _extract_commands(command: str) -> list[str]:
    """从管道/链式命令中提取各段的首命令。"""
    # 简单拆分管道和 &&/||，不处理引号内的分隔符（够用）
    parts = re.split(r'\||&&|\|\|;', command)
    result = []
    for part in parts:
        part = part.strip()
        if not part:
            continue
        # 去掉重定向
        part = re.split(r'[<>]', part)[0].strip()
        # 取第一个词作为命令名
        try:
            tokens = shlex.split(part)
        except ValueError:
            tokens = part.split()
        if tokens:
            result.append(tokens[0])
    return result


SAFE_COMMANDS = frozenset({
    # 文件查看
    "ls", "cat", "tree", "head", "tail", "less", "more", "file", "stat",
    # 搜索
    "grep", "egrep", "fgrep", "find", "rg", "ag", "ack", "which", "whereis",
    # 文本处理（只读）
    "wc", "sort", "uniq", "cut", "tr", "awk", "sed", "diff", "comm",
    # echo
    "echo", "printf",
    # git 只读
    "git",
    # 版本查询
    "python3", "python", "node", "npm", "pnpm", "npx", "go", "rustc", "cargo",
    # 系统（只读）
    "ps", "pgrep", "netstat", "ss", "lsof", "ip", "uname", "hostname",
    "whoami", "id", "env", "printenv", "date", "uptime",
    # 包管理（只读）
    "pip", "pip3", "dpkg", "rpm", "dnf",
    # shell 内建（安全）
    "cd", "pwd", "export", "source", "bash", "sh", "zsh",
    # 构建/运行工具
    "make", "cmake", "docker", "kubectl", "helm",
    "yarn", "bun", "deno",
    # 其他安全命令
    "jq", "yq", "xargs", "tee", "mkdir", "test", "[", "true", "false",
    "touch", "cp", "mv", "chmod", "chown",
    "curl", "wget", "tar", "unzip", "gzip",
})

DENY_PATTERNS = (
    r"rm\s+-rf\s+/",
    r"sudo\s+rm",
    r">\s*/etc/",
    r"chmod\s+777",
    r"git\s+push\s+.*--force",
    r"curl\s+.*\|\s*sh",
    r"wget\s+.*\|\s*sh",
)

# MCP 工具安全前缀：只读/搜索/分析类工具，无需 AI 审核
SAFE_MCP_PREFIXES = (
    "mcp__plugin_claude-mem_mcp-search__",   # claude-mem 代码搜索
    "mcp__zread__",                           # GitHub 仓库只读
    "mcp__web-search-prime__",                # Web 搜索
    "mcp__web-reader__",                      # Web 读取
    "mcp__web_reader__",                      # Web 读取（别名）
    "mcp__zai-mcp-server__",                  # AI 图像/数据分析
    "mcp__4_5v_mcp__",                        # 图像分析
    "mcp__plugin_playwright_playwright__",    # Playwright 浏览器
    "mcp__plugin_superpowers-chrome_chrome__", # Chrome 浏览器
)


def _is_safe_bash(command: str) -> bool:
    """判断 Bash 命令是否安全可放行。"""
    # 拒绝危险模式
    for pat in DENY_PATTERNS:
        if re.search(pat, command):
            return False

    cmds = _extract_commands(command)
    if not cmds:
        return True  # 空命令

    return all(c in SAFE_COMMANDS for c in cmds)


def main():
    input_data = json.loads(sys.stdin.read())
    cwd = input_data.get("cwd", "")
    tool_name = input_data.get("tool_name", "unknown")
    tool_input = input_data.get("tool_input", {})

    # 内部安全工具
    if tool_name in ALWAYS_ALLOW_TOOLS:
        write_log(cwd, tool_name, "allow", "内部安全工具")
        output("allow", f"[本地放行] {tool_name}")
        return

    # 文件类工具：cwd 内放行
    if tool_name in FILE_TOOL_PATH_FIELDS:
        path_field = FILE_TOOL_PATH_FIELDS[tool_name]
        target_path = tool_input.get(path_field)

        if target_path is None:
            write_log(cwd, tool_name, "allow", "默认工作目录")
            output("allow", "[本地放行] 默认工作目录")
            return

        if is_within_cwd(target_path, cwd):
            write_log(cwd, tool_name, "allow", "目标在工作目录内", target_path)
            output("allow", "[本地放行] 目标在工作目录内")
            return

    # Bash: 已知安全命令直接放行
    if tool_name == "Bash":
        command = tool_input.get("command", "").strip()
        if _is_safe_bash(command):
            write_log(cwd, tool_name, "allow", "已知安全命令", command)
            output("allow", f"[本地放行] {command[:60]}")
            return

    # MCP：已知安全的只读工具前缀直接放行
    if any(tool_name.startswith(prefix) for prefix in SAFE_MCP_PREFIXES):
        detail = tool_input.get("file_path", "") or tool_input.get("url", "") or ""
        write_log(cwd, tool_name, "allow", "MCP只读工具", detail)
        output("allow", f"[本地放行] MCP: {tool_name}")
        return

    # 其他：交给权限系统（→ 可能触发 PermissionRequest）
    detail = tool_input.get("command", "") or tool_input.get("file_path", "") or tool_input.get("url", "")
    write_log(cwd, tool_name, "ask", "需要审核", detail)
    output("ask", f"[需要审核] {tool_name}")


if __name__ == "__main__":
    main()
