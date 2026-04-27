#!/usr/bin/env python3
"""诊断工具：测试 ~/.claude-auto-permit/ 中每个 provider/model 是否正常工作。"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from providers import load_provider_configs, is_provider_unavailable, get_active_providers

TEST_PROMPT = 'Reply with only: {"decision": "approve", "reason": "test"}'

PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"
SKIP = "\033[93mSKIP\033[0m"


def test_one(label, review_fn, timeout=15):
    start = time.time()
    try:
        resp = review_fn(TEST_PROMPT, timeout=timeout)
        elapsed = time.time() - start
        data = json.loads(resp) if resp else None
        if data and data.get("decision") == "approve":
            return PASS, f"{elapsed:.1f}s"
        return FAIL, f"unexpected response: {resp[:80]}"
    except Exception as e:
        elapsed = time.time() - start
        return FAIL, f"{elapsed:.1f}s {str(e)[:100]}"


def main():
    from providers import CONFIG_DIR

    print(f"Config dir: {CONFIG_DIR}")
    print(f"Exists: {'yes' if os.path.isdir(CONFIG_DIR) else 'no'}")
    print()

    if not os.path.isdir(CONFIG_DIR):
        # env var mode
        print("Mode: environment variable (single provider)")
        providers = get_active_providers()
        if not providers:
            print(f"  {FAIL} No provider configured")
            return
        for name, model, fn in providers:
            label = f"{name}/{model}" if model else name
            status, detail = test_one(label, fn)
            print(f"  {status} {label:45s} {detail}")
        return

    entries = load_provider_configs()
    if not entries:
        print(f"  {FAIL} No valid config files found, falling back to env var mode")
        providers = get_active_providers()
        for name, model, fn in providers:
            label = f"{name}/{model}" if model else name
            status, detail = test_one(label, fn)
            print(f"  {status} {label:45s} {detail}")
        return

    print("Mode: config file (multi-provider)")
    print(f"Loaded {len(entries)} model entries:")
    print()

    passed = 0
    failed = 0
    skipped = 0

    for pp, mp, pname, mname, fn in entries:
        label = f"{pname}/{mname}" if mname else pname
        unavail = is_provider_unavailable(pname, mname)
        if unavail:
            print(f"  {SKIP} {label:45s} unavailable: {unavail[:50]}")
            skipped += 1
            continue
        status, detail = test_one(label, fn)
        print(f"  {status} {label:45s} {detail}")
        if "PASS" in status:
            passed += 1
        else:
            failed += 1

    print()
    print(f"Total: {passed} passed, {failed} failed, {skipped} skipped")


if __name__ == "__main__":
    main()
