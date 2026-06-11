#!/usr/bin/env python3
"""
apply_ops.py — Venture Control dashboard updater (runs in GitHub Actions)

Place this file in the ROOT of FetaPit/Control_Room alongside index.html.

It reads every JSON file in pending/, applies the operations to index.html,
then deletes the processed files. The GitHub Actions workflow commits the result.

No external dependencies — stdlib only.
"""

import json
import re
import sys
from pathlib import Path

DASHBOARD = Path("index.html")
PENDING_DIR = Path("pending")


# ── Operation logic ───────────────────────────────────────────────────────────

def _find_project_range(html: str, code: str):
    marker = f'code:"{code}"'
    pos = html.find(marker)
    if pos == -1:
        raise ValueError(f"Project {code} not found in SEED")
    obj_start = html.rfind("{", 0, pos)
    if obj_start == -1:
        raise ValueError(f"No opening brace before code:{code}")
    depth = 0
    i = obj_start
    while i < len(html):
        c = html[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return obj_start, i + 1
        i += 1
    raise ValueError(f"Unmatched brace for project {code}")


def _find_task_range(project_block: str, task_code: str):
    marker = f'code:"{task_code}"'
    pos = project_block.find(marker)
    if pos == -1:
        raise ValueError(f"Task {task_code} not found")
    obj_start = project_block.rfind("{", 0, pos)
    depth = 0
    i = obj_start
    while i < len(project_block):
        c = project_block[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                return obj_start, i + 1
        i += 1
    raise ValueError(f"Unmatched brace for task {task_code}")


def _set_str(block: str, field: str, value: str) -> str:
    return re.sub(rf'\b{re.escape(field)}:"[^"]*"', f'{field}:"{value}"', block)


def _set_num(block: str, field: str, value) -> str:
    return re.sub(rf'\b{re.escape(field)}:\d+(?:\.\d+)?', f'{field}:{value}', block)


def _dict_to_js(d: dict) -> str:
    parts = []
    for k, v in d.items():
        if isinstance(v, bool):
            parts.append(f'{k}:{"true" if v else "false"}')
        elif isinstance(v, str):
            parts.append(f'{k}:"{v.replace(chr(34), chr(92)+chr(34))}"')
        elif isinstance(v, (int, float)):
            parts.append(f"{k}:{v}")
        elif isinstance(v, list):
            items = ",".join(_dict_to_js(i) if isinstance(i, dict) else json.dumps(i) for i in v)
            parts.append(f"{k}:[{items}]")
        elif v is None:
            parts.append(f"{k}:null")
    return "{" + ",".join(parts) + "}"


def apply_update_project(html: str, code: str, fields: dict) -> str:
    start, end = _find_project_range(html, code)
    block = html[start:end]
    for field, value in fields.items():
        if isinstance(value, str):
            block = _set_str(block, field, value)
        elif isinstance(value, (int, float)):
            block = _set_num(block, field, value)
    return html[:start] + block + html[end:]


def apply_update_task(html: str, task_code: str, fields: dict) -> str:
    project_code = ".".join(task_code.split(".")[:2])
    p_start, p_end = _find_project_range(html, project_code)
    project_block = html[p_start:p_end]
    t_start, t_end = _find_task_range(project_block, task_code)
    task_block = project_block[t_start:t_end]
    for field, value in fields.items():
        if field == "done":
            task_block = re.sub(r'\bdone:(true|false)', f'done:{"true" if value else "false"}', task_block)
        elif isinstance(value, str):
            task_block = _set_str(task_block, field, value)
        elif isinstance(value, (int, float)):
            task_block = _set_num(task_block, field, value)
    project_block = project_block[:t_start] + task_block + project_block[t_end:]
    return html[:p_start] + project_block + html[p_end:]


def apply_add_knox(html: str, entry: dict) -> str:
    js_entry = "    " + _dict_to_js(entry)
    pattern = r'(knox:\s*\[[\s\S]*?)(^\s*\]\s*\n?\s*\};)'
    m = re.search(pattern, html, re.MULTILINE)
    if not m:
        raise ValueError("Cannot find knox array in SEED")
    return html[:m.start(2)] + js_entry + ",\n  " + html[m.start(2):]


def apply_add_project(html: str, project: dict) -> str:
    """Append a new project to the projects array."""
    js_entry = "    " + _dict_to_js(project)
    pattern = r'(projects:\s*\[[\s\S]*?)(^\s*\]\s*,?\s*\n\s*//[^\n]*KNOX)'
    m = re.search(pattern, html, re.MULTILINE)
    if not m:
        pattern2 = r'(projects:\s*\[[\s\S]*?)(^\s*\]\s*,\s*\n\s*knox\s*:)'
        m = re.search(pattern2, html, re.MULTILINE)
    if not m:
        raise ValueError("Cannot find projects array end in SEED")
    return html[:m.start(2)] + js_entry + ",\n  " + html[m.start(2):]


def dispatch(html: str, op: dict) -> str:
    t = op.get("type")
    if t == "update_project":
        return apply_update_project(html, op["code"], op["fields"])
    elif t == "update_task":
        return apply_update_task(html, op["task_code"], op["fields"])
    elif t == "add_knox":
        return apply_add_knox(html, op["entry"])
    elif t == "add_project":
        return apply_add_project(html, op["project"])
    else:
        raise ValueError(f"Unknown op type: {t!r}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    if not DASHBOARD.exists():
        print(f"ERROR: {DASHBOARD} not found — is this running in the Control_Room root?")
        sys.exit(1)

    pending_files = sorted(PENDING_DIR.glob("*.json")) if PENDING_DIR.exists() else []
    if not pending_files:
        print("No pending operations found.")
        return

    html = DASHBOARD.read_text("utf-8")
    original = html
    processed = []
    total_ops = 0

    for pf in pending_files:
        try:
            data = json.loads(pf.read_text("utf-8"))
        except Exception as e:
            print(f"  SKIP {pf.name}: invalid JSON — {e}")
            continue

        ops = data.get("operations", [])
        file_applied = 0
        for op in ops:
            try:
                html = dispatch(html, op)
                file_applied += 1
                print(f"  ✓ {op.get('type')} {op.get('code') or op.get('task_code') or ''}")
            except Exception as e:
                print(f"  ✗ {op.get('type')} failed: {e}")

        total_ops += file_applied
        processed.append(pf)

    if html == original:
        print("HTML unchanged — nothing to commit.")
        for pf in processed:
            pf.unlink()
        return

    DASHBOARD.write_text(html, "utf-8")
    for pf in processed:
        pf.unlink()

    print(f"\nApplied {total_ops} operation(s) across {len(processed)} file(s).")
    print("index.html updated. Processed pending files deleted.")


if __name__ == "__main__":
    main()
