#!/usr/bin/env python3
"""
PreToolUse Hook: 本地快速判断（不走网络）

- 内部安全工具 → "allow" 直接放行
- 文件操作且目标在 cwd 内 → "allow" 直接放行
- 其他 → "ask" 交给权限系统（→ 可能触发 PermissionRequest hook）
"""

import json
import os
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
    "Task", "WebSearch",
    "TaskCreate", "TaskUpdate", "TaskGet", "TaskList", "TaskStop",
    "EnterPlanMode", "ExitPlanMode",
    "EnterWorktree", "Skill", "TaskOutput",
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

    # 其他：交给权限系统（→ 可能触发 PermissionRequest）
    detail = tool_input.get("command", "") or tool_input.get("file_path", "") or tool_input.get("url", "")
    write_log(cwd, tool_name, "ask", "需要审核", detail)
    output("ask", f"[需要审核] {tool_name}")


if __name__ == "__main__":
    main()
