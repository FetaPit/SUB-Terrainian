#!/usr/bin/env python3
"""
tools/sync_dashboard.py — Venture Control dashboard sync

Reads a pending.json file and pushes the operations to FetaPit/Control_Room.

Two modes:
  --queue  (default): push ops as pending/<timestamp>.json to Control_Room.
           GitHub Actions picks it up and applies it to index.html automatically.
           Best when GitHub Actions workflow is set up in Control_Room.

  --direct: download index.html, apply ops locally, push full file back.
           Works without GitHub Actions — useful as a fallback.

Requires: CONTROL_ROOM_TOKEN in .env (GitHub PAT, repo scope on Control_Room)

Usage:
    python tools/sync_dashboard.py                  # queue mode, auto-detect pending.json
    python tools/sync_dashboard.py --auto           # silent on no-token / empty queue
    python tools/sync_dashboard.py --direct         # direct HTML modification mode
    python tools/sync_dashboard.py --dry            # show what would change, no push
    python tools/sync_dashboard.py --status         # print pending queue
    python tools/sync_dashboard.py --pending PATH   # use a specific pending.json path

Pending file search order (first found wins):
  1. Path from --pending flag
  2. ./venture_control/pending.json  (project-local)
  3. ~/.claude/venture_control/pending.json  (global, used by all projects)

Operation types:
  update_project  : scalar fields on a project (readiness, status, pub, touched, streak)
  update_task     : task status, deadline, done flag
  add_knox        : append a Knox asset/doc entry
  add_project     : append a new project entry
"""

import json
import re
import base64
import os
import sys
import datetime
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
REPO = "FetaPit/Control_Room"
FILE_PATH = "index.html"
API_BASE = "https://api.github.com"

# Pending file search order
_PENDING_CANDIDATES = [
    BASE_DIR / "venture_control" / "pending.json",
    Path.home() / ".claude" / "venture_control" / "pending.json",
]

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
    pattern = r'(knox:\s*\[[\s\S]*?)(^\s*\]\s*\n?\s*\};)'
    m = re.search(pattern, html, re.MULTILINE)
    if not m:
        raise ValueError("Cannot find knox array in SEED")
    return html[:m.start(2)] + js_entry + ",\n  " + html[m.start(2):]


def apply_add_project(html: str, project: dict) -> str:
    """Append a new project before the knox section."""
    js_entry = "    " + _dict_to_js(project)
    pattern = r'(projects:\s*\[[\s\S]*?)(^\s*\]\s*,\s*\n\s*knox\s*:)'
    m = re.search(pattern, html, re.MULTILINE)
    if not m:
        raise ValueError("Cannot find projects array end in SEED")
    return html[:m.start(2)] + js_entry + ",\n  " + html[m.start(2):]


# ── Operation dispatcher ──────────────────────────────────────────────────────

def apply_operation(html: str, op: dict) -> str:
    op_type = op.get("type")
    if op_type == "update_project":
        return apply_update_project(html, op["code"], op["fields"])
    elif op_type == "update_task":
        return apply_update_task(html, op["task_code"], op["fields"])
    elif op_type == "add_knox":
        return apply_add_knox(html, op["entry"])
    elif op_type == "add_project":
        return apply_add_project(html, op["project"])
    else:
        raise ValueError(f"Unknown operation type: {op_type!r}")


# ── Pending file helpers ──────────────────────────────────────────────────────

def find_pending(explicit: str | None = None) -> Path | None:
    """Return the first pending.json that exists, or None."""
    if explicit:
        p = Path(explicit).expanduser()
        return p if p.exists() else None
    for candidate in _PENDING_CANDIDATES:
        if candidate.expanduser().exists():
            return candidate.expanduser()
    return None


def load_pending(path: Path) -> list:
    data = json.loads(path.read_text("utf-8"))
    return data.get("operations", [])


def clear_pending(path: Path):
    path.write_text(json.dumps({"operations": []}, indent=2), encoding="utf-8")


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


# ── Queue mode: push ops JSON to Control_Room/pending/ ───────────────────────

def queue_push(token: str, ops: list, dry_run: bool = False) -> bool:
    """Push pending ops as a timestamped JSON file to Control_Room/pending/."""
    ts = datetime.datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    remote_path = f"pending/{ts}.json"
    content = json.dumps({"operations": ops}, indent=2, ensure_ascii=False)

    if dry_run:
        print(f"[DRY RUN] Would push {len(ops)} op(s) to {REPO}/{remote_path}")
        return True

    requests = _get_requests()
    r = requests.put(
        f"{API_BASE}/repos/{REPO}/contents/{remote_path}",
        headers=HEADERS(token),
        json={
            "message": f"chore: queue {len(ops)} dashboard op(s)",
            "content": base64.b64encode(content.encode("utf-8")).decode(),
        },
        timeout=30,
    )
    r.raise_for_status()
    print(f"  ✓ Queued → {REPO}/{remote_path}")
    print(f"  ✓ GitHub Actions will apply {len(ops)} op(s) to dashboard automatically")
    return True


def main():
    args = sys.argv[1:]
    silent = "--auto" in args
    dry_run = "--dry" in args
    status_only = "--status" in args
    direct_mode = "--direct" in args
    pending_arg = None
    for i, a in enumerate(args):
        if a == "--pending" and i + 1 < len(args):
            pending_arg = args[i + 1]

    pending_path = find_pending(pending_arg)

    if status_only:
        if pending_path is None:
            print("No pending.json found.")
        else:
            ops = load_pending(pending_path)
            if not ops:
                print(f"{pending_path} — no pending operations.")
            else:
                print(f"{pending_path} — {len(ops)} pending operation(s):")
                for i, op in enumerate(ops, 1):
                    print(f"  {i}. {op.get('type')} {op.get('code') or op.get('task_code') or ''}")
        return

    if pending_path is None:
        if not silent:
            print("No pending.json found — nothing to sync.")
        return

    ops = load_pending(pending_path)

    if not ops:
        if not silent:
            print("No pending operations — dashboard is already up to date.")
        return

    token = get_token(silent=silent)
    if not token:
        if silent:
            return
        sys.exit(1)

    n = len(ops)

    # Queue mode: push ops JSON to Control_Room/pending/ → GitHub Actions handles the merge
    if not direct_mode:
        print(f"Queuing {n} operation(s) to {REPO}/pending/ ...")
        queue_push(token, ops, dry_run=dry_run)
        if not dry_run:
            clear_pending(pending_path)
            print(f"  ✓ {pending_path.name} cleared")
        return

    # Direct mode: download HTML, apply ops locally, push full file back
    print(f"Syncing {n} operation(s) directly to {REPO}/{FILE_PATH} ...")

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
        clear_pending(pending_path)
        return

    msg = f"chore: venture dashboard sync ({n} update{'s' if n != 1 else ''})"
    github_put_file(token, FILE_PATH, html, sha, msg)
    print(f"  ✓ Dashboard pushed to {REPO}")

    clear_pending(pending_path)
    print(f"  ✓ {pending_path.name} cleared")

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
