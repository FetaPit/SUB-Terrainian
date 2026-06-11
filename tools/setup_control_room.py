#!/usr/bin/env python3
"""
tools/setup_control_room.py — One-time Control_Room repo setup

Pushes all required files to FetaPit/Control_Room in a single commit:
  - index.html           (venture dashboard)
  - apply_ops.py         (GitHub Actions apply script)
  - .github/workflows/sync_dashboard.yml
  - pending/.gitkeep

Requires: CONTROL_ROOM_TOKEN in .env
          (GitHub PAT, Contents read+write on FetaPit/Control_Room)

Run once from Termux:
    python tools/setup_control_room.py
"""

import base64
import json
import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
REPO = "FetaPit/Control_Room"
API  = "https://api.github.com"
BRANCH = "main"

UA = {"User-Agent": "SubTerrainian/0.1 ( contact@ptliveddesign.example )"}


def _requests():
    try:
        import requests
        return requests
    except ImportError:
        print("ERROR: pip install requests")
        sys.exit(1)


def get_token():
    try:
        from dotenv import load_dotenv
        load_dotenv(BASE_DIR / ".env")
    except ImportError:
        pass
    t = os.getenv("CONTROL_ROOM_TOKEN")
    if not t:
        print("ERROR: CONTROL_ROOM_TOKEN not set in .env")
        print("  Create a GitHub fine-grained PAT:")
        print("  github.com/settings/tokens → Fine-grained → FetaPit/Control_Room → Contents: Read+Write")
        print("  Add to .env:  CONTROL_ROOM_TOKEN=github_pat_...")
        sys.exit(1)
    return t


def headers(token):
    return {**UA, "Authorization": f"token {token}", "Accept": "application/vnd.github+json"}


def get_sha(token, path):
    """Return existing file SHA or None."""
    r = _requests().get(f"{API}/repos/{REPO}/contents/{path}",
                        headers=headers(token), params={"ref": BRANCH}, timeout=15)
    if r.status_code == 404:
        return None
    r.raise_for_status()
    return r.json().get("sha")


def push_file(token, path, content_str, message):
    sha = get_sha(token, path)
    body = {
        "message": message,
        "branch": BRANCH,
        "content": base64.b64encode(content_str.encode("utf-8")).decode(),
    }
    if sha:
        body["sha"] = sha
    r = _requests().put(f"{API}/repos/{REPO}/contents/{path}",
                        headers=headers(token), json=body, timeout=30)
    r.raise_for_status()
    verb = "Updated" if sha else "Created"
    print(f"  {verb}  {path}")


def read_local(rel):
    p = BASE_DIR / rel
    if not p.exists():
        print(f"ERROR: {p} not found — run git pull first")
        sys.exit(1)
    return p.read_text("utf-8")


def main():
    print(f"Setting up {REPO} ...")
    token = get_token()

    # 1. Dashboard HTML (updated version with Sprint tasks + readiness 65)
    #    Try /home/user/index.html first (generated in this session), fall back to updated html
    html_candidates = [
        Path.home() / "index.html",
        Path.home() / "PTLiveDesignVentureControl_updated.html",
    ]
    html_content = None
    for c in html_candidates:
        if c.exists():
            html_content = c.read_text("utf-8")
            print(f"  Using dashboard: {c.name}")
            break
    if html_content is None:
        print("ERROR: dashboard HTML not found. Expected ~/index.html or ~/PTLiveDesignVentureControl_updated.html")
        sys.exit(1)

    # 2. apply_ops.py
    apply_content = read_local("venture_control/control_room_setup/apply_ops.py")

    # 3. GitHub Actions workflow
    workflow_content = read_local("venture_control/control_room_setup/sync_dashboard.yml")

    # Push everything
    push_file(token, "index.html",                           html_content,    "feat: add venture dashboard")
    push_file(token, "apply_ops.py",                         apply_content,   "feat: add dashboard apply script")
    push_file(token, ".github/workflows/sync_dashboard.yml", workflow_content,"feat: add dashboard sync workflow")

    # pending/.gitkeep — only if pending/ doesn't already have it
    if get_sha(token, "pending/.gitkeep") is None:
        push_file(token, "pending/.gitkeep", "", "chore: create pending queue folder")

    print(f"\nDone. Control_Room is ready.")
    print(f"Enable GitHub Pages: Settings → Pages → Deploy from branch → main → / → Save")
    print(f"Dashboard will be live at: https://fetapit.github.io/Control_Room/")
    print(f"\nNext: set CONTROL_ROOM_TOKEN in .env, then run:")
    print(f"  python tools/sync_dashboard.py")
    print(f"to push the pending dashboard updates (Sprints 1-3 + Knox entries).")


if __name__ == "__main__":
    main()
