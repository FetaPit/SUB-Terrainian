#!/usr/bin/env python3
"""
tools/sync_dashboard.py — Venture Control dashboard sync

Reads venture_control/pending.json, applies operations to the
PT Live Design Venture Control dashboard hosted in FetaPit/Control_Room,
then clears the queue.

Requires: CONTROL_ROOM_TOKEN in .env (GitHub PAT, repo scope on Control_Room)

Usage:
    python tools/sync_dashboard.py          # apply pending ops + push
    python tools/sync_dashboard.py --auto   # same but silent on no-token / empty queue
    python tools/sync_dashboard.py --dry    # show what would change, no push
    python tools/sync_dashboard.py --status # print pending queue

Operation types in pending.json:
  update_project  : update scalar fields on a project (readiness, status, pub, touched, streak)
  update_task     : update a task's status, deadline, or done flag
  add_knox        : append a Knox asset/doc entry
"""

import json
import re
import base64
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
PENDING_PATH = BASE_DIR / "venture_control" / "pending.json"
REPO = "FetaPit/Control_Room"
FILE_PATH = "index.html"
API_BASE = "https://api.github.com"

HEADERS = lambda token: {
    "Authorization": f"token {token}",
    "Accept": "application/vnd.github+json",
    "User-Agent": "SubTerrainian/0.1 ( contact@ptliveddesign.example )",
}


# ── GitHub API helpers ────────────────────────────────────────────────────────

def _get_requests():
    try:
        import requests
        return requests
    except ImportError:
        print("ERROR: requests not installed. Run: pip install requests")
        sys.exit(1)

def github_get_file(token, path):
    requests = _get_requests()
    r = requests.get(
        f"{API_BASE}/repos/{REPO}/contents/{path}",
        headers=HEADERS(token),
        timeout=30,
    )
    if r.status_code == 404:
        raise FileNotFoundError(f"{path} not found in {REPO}")
    r.raise_for_status()
    data = r.json()
    content = base64.b64decode(data["content"].replace("\n", "")).decode("utf-8")
    return content, data["sha"]

def github_put_file(token, path, content, sha, message):
    requests = _get_requests()
    r = requests.put(
        f"{API_BASE}/repos/{REPO}/contents/{path}",
        headers=HEADERS(token),
        json={
            "message": message,
            "content": base64.b64encode(content.encode("utf-8")).decode(),
            "sha": sha,
        },
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


# ── HTML SEED surgery ─────────────────────────────────────────────────────────

def _find_project_range(html: str, code: str) -> tuple[int, int]:
    """Return (start, end) indices of the JS project object with given code."""
    marker = f'code:"{code}"'
    pos = html.find(marker)
    if pos == -1:
        raise ValueError(f"Project {code} not found in SEED")

    # Walk back to the opening { of this project object
    obj_start = html.rfind("{", 0, pos)
    if obj_start == -1:
        raise ValueError(f"No opening brace found before code:{code}")

    # Walk forward counting only {{ }} to find the matching close
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


def _set_str_field(block: str, field: str, value: str) -> str:
    """Replace   field:"old"  with  field:"new"  in a JS block."""
    return re.sub(
        rf'\b{re.escape(field)}:"[^"]*"',
        f'{field}:"{value}"',
        block,
    )


def _set_num_field(block: str, field: str, value: int | float) -> str:
    """Replace   field:42  with  field:new_value  in a JS block."""
    return re.sub(
        rf'\b{re.escape(field)}:\d+(?:\.\d+)?',
        f'{field}:{value}',
        block,
    )


def apply_update_project(html: str, code: str, fields: dict) -> str:
    start, end = _find_project_range(html, code)
    block = html[start:end]
    for field, value in fields.items():
        if isinstance(value, str):
            block = _set_str_field(block, field, value)
        elif isinstance(value, (int, float)):
            block = _set_num_field(block, field, value)
    return html[:start] + block + html[end:]


def _find_task_range(project_block: str, task_code: str) -> tuple[int, int]:
    """Return (start, end) of a task object inside a project block."""
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


def apply_update_task(html: str, task_code: str, fields: dict) -> str:
    # task_code looks like "26.002.07"; project code is "26.002"
    project_code = ".".join(task_code.split(".")[:2])
    p_start, p_end = _find_project_range(html, project_code)
    project_block = html[p_start:p_end]

    t_start, t_end = _find_task_range(project_block, task_code)
    task_block = project_block[t_start:t_end]

    for field, value in fields.items():
        if field == "done":
            task_block = re.sub(r'\bdone:(true|false)', f'done:{"true" if value else "false"}', task_block)
        elif isinstance(value, str):
            task_block = _set_str_field(task_block, field, value)
        elif isinstance(value, (int, float)):
            task_block = _set_num_field(task_block, field, value)

    project_block = project_block[:t_start] + task_block + project_block[t_end:]
    return html[:p_start] + project_block + html[p_end:]


def _dict_to_js(d: dict) -> str:
    """Convert a Python dict to a compact JS object literal (no JSON.stringify quotes on keys)."""
    parts = []
    for k, v in d.items():
        if isinstance(v, bool):
            parts.append(f'{k}:{"true" if v else "false"}')
        elif isinstance(v, str):
            escaped = v.replace("\\", "\\\\").replace('"', '\\"')
            parts.append(f'{k}:"{escaped}"')
        elif isinstance(v, (int, float)):
            parts.append(f"{k}:{v}")
        elif isinstance(v, list):
            items = ",".join(_dict_to_js(i) if isinstance(i, dict) else json.dumps(i) for i in v)
            parts.append(f"{k}:[{items}]")
        elif v is None:
            parts.append(f"{k}:null")
        else:
            parts.append(f"{k}:{v}")
    return "{" + ",".join(parts) + "}"


def apply_add_knox(html: str, entry: dict) -> str:
    """Append a Knox entry before the closing ]} of the knox array."""
    js_entry = "    " + _dict_to_js(entry)
    # Find the knox array closer: last entry before `]` then `}`  then `};`
    # Pattern: last item in knox array, followed by \n  ]
    pattern = r'(knox:\s*\[[\s\S]*?)(^\s*\]\s*\n?\s*\};)'
    m = re.search(pattern, html, re.MULTILINE)
    if not m:
        raise ValueError("Cannot find knox array in SEED")
    insert_at = m.start(2)
    return html[:insert_at] + js_entry + ",\n  " + html[insert_at:]


# ── Operation dispatcher ──────────────────────────────────────────────────────

def apply_operation(html: str, op: dict) -> str:
    op_type = op.get("type")
    if op_type == "update_project":
        return apply_update_project(html, op["code"], op["fields"])
    elif op_type == "update_task":
        return apply_update_task(html, op["task_code"], op["fields"])
    elif op_type == "add_knox":
        return apply_add_knox(html, op["entry"])
    else:
        raise ValueError(f"Unknown operation type: {op_type!r}")


# ── Main ──────────────────────────────────────────────────────────────────────

def load_pending() -> list:
    if not PENDING_PATH.exists():
        return []
    data = json.loads(PENDING_PATH.read_text("utf-8"))
    return data.get("operations", [])


def clear_pending():
    PENDING_PATH.write_text(json.dumps({"operations": []}, indent=2), encoding="utf-8")


def get_token(silent: bool = False) -> str | None:
    try:
        from dotenv import load_dotenv
        load_dotenv(BASE_DIR / ".env")
    except ImportError:
        pass
    token = os.getenv("CONTROL_ROOM_TOKEN")
    if not token and not silent:
        print("ERROR: CONTROL_ROOM_TOKEN not set in .env")
        print("       Create a GitHub PAT with repo scope on FetaPit/Control_Room")
        print("       Add:  CONTROL_ROOM_TOKEN=ghp_... to your .env")
    return token


def main():
    args = sys.argv[1:]
    silent = "--auto" in args
    dry_run = "--dry" in args
    status_only = "--status" in args

    ops = load_pending()

    if status_only:
        if not ops:
            print("venture_control/pending.json — no pending operations.")
        else:
            print(f"venture_control/pending.json — {len(ops)} pending operation(s):")
            for i, op in enumerate(ops, 1):
                print(f"  {i}. {op.get('type')} {op.get('code') or op.get('task_code') or ''}")
        return

    if not ops:
        if not silent:
            print("No pending operations — dashboard is already up to date.")
        return

    token = get_token(silent=silent)
    if not token:
        if silent:
            return
        sys.exit(1)

    print(f"Syncing {len(ops)} operation(s) to {REPO}/{FILE_PATH} ...")

    html, sha = github_get_file(token, FILE_PATH)
    original_html = html

    applied, failed = 0, []
    for op in ops:
        try:
            html = apply_operation(html, op)
            applied += 1
            print(f"  ✓ {op.get('type')} {op.get('code') or op.get('task_code') or ''}")
        except Exception as e:
            failed.append((op, str(e)))
            print(f"  ✗ {op.get('type')} failed: {e}")

    if applied == 0:
        print("No operations applied — dashboard unchanged.")
        return

    if dry_run:
        print(f"\n[DRY RUN] Would push {applied} change(s). Nothing written.")
        return

    if html == original_html:
        print("HTML unchanged after operations — skipping push.")
        clear_pending()
        return

    n = len(ops)
    msg = f"chore: venture dashboard sync ({n} update{'s' if n != 1 else ''})"
    github_put_file(token, FILE_PATH, html, sha, msg)
    print(f"  ✓ Dashboard pushed to {REPO}")

    clear_pending()
    print("  ✓ pending.json cleared")

    if failed:
        print(f"\n  {len(failed)} operation(s) failed (removed from queue):")
        for op, err in failed:
            print(f"    {op.get('type')}: {err}")


if __name__ == "__main__":
    silent = "--auto" in sys.argv
    try:
        main()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        if not silent:
            raise
        # Silent mode: exit 0 so the Stop hook never breaks a Claude Code session
