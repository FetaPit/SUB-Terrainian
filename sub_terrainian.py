#!/usr/bin/env python3
"""
sub_terrainian.py  —  SUB-Terrainian v0.1 alpha

Top-level orchestrator. Runs any combination of pipeline phases
or launches the local web dashboard.

Usage:
    python sub_terrainian.py scan  [/path/to/music]   Phase 1: resolve MBIDs
    python sub_terrainian.py art   [--force]           Phase 2: album artwork
    python sub_terrainian.py port  [--force]           Phase 3: artist portraits
    python sub_terrainian.py lyr   [--force]           Phase 4: lyrics → manifest
    python sub_terrainian.py emit  [--force] [--plain] Emit .lrc sidecars
    python sub_terrainian.py sync                      Trigger MediaStore rescan
    python sub_terrainian.py run   [/path/to/music]    Full pipeline (1→4 + emit)
    python sub_terrainian.py serve [--port 5000]       Launch web dashboard

Environment: see .env.example
"""

import os
import sys
import subprocess
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

DEFAULT_MUSIC = os.path.expanduser(
    os.getenv("MUSIC_ROOT", "~/storage/shared/Music")
)
DB_PATH = os.getenv("MANIFEST_PATH", "sub_terrainian.db")


# ── MediaStore sync (Termux → Samsung Music / Musicolet) ─────────────────────

def sync_media(path: str = None):
    """
    Trigger Android MediaStore rescan so Samsung Music, Musicolet, and
    other players pick up newly written folder.jpg / .lrc files.

    Requires: pkg install termux-api  (one-time setup)
    """
    target = path or DEFAULT_MUSIC
    print(f"Syncing MediaStore: {target}")
    try:
        result = subprocess.run(
            ["termux-media-scan", "-r", target],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode == 0:
            print("  MediaStore updated. Samsung Music will refresh on next open.")
        else:
            print(f"  termux-media-scan failed: {result.stderr.strip()}")
            print("  Install with: pkg install termux-api")
    except FileNotFoundError:
        print("  termux-media-scan not found.")
        print("  Install: pkg install termux-api  then re-run.")
    except subprocess.TimeoutExpired:
        print("  Scan timed out (large library). Samsung Music will catch up shortly.")


# ── Phase runners ─────────────────────────────────────────────────────────────

def run_scan(music_root: str = None, force: bool = False):
    from metadata.resolve import resolve_library
    resolve_library(music_root or DEFAULT_MUSIC, DB_PATH, force=force)


def run_artwork(force: bool = False):
    from artwork.fetch import fetch_all_artwork
    fetch_all_artwork(DB_PATH, force=force)


def run_portraits(force: bool = False):
    from portraits.fetch import fetch_all_portraits
    fetch_all_portraits(DB_PATH, force=force)


def run_lyrics(force: bool = False):
    from lyrics.fetch import fetch_all_lyrics
    fetch_all_lyrics(DB_PATH, force=force)


def run_emit(force: bool = False, plain: bool = False):
    from lyrics.emit import emit_all
    emit_all(DB_PATH, force=force, emit_plain=plain)


def run_all(music_root: str = None, force: bool = False):
    print("=" * 50)
    print("SUB-Terrainian — full pipeline run")
    print("=" * 50)
    print("\n[Phase 1] Metadata resolve")
    run_scan(music_root, force)
    print("\n[Phase 2] Album artwork")
    run_artwork(force)
    print("\n[Phase 3] Artist portraits")
    run_portraits(force)
    print("\n[Phase 4] Lyrics")
    run_lyrics(force)
    print("\n[Emit] .lrc sidecars")
    run_emit(force, plain=True)
    print("\n[Sync] MediaStore")
    sync_media(music_root)
    print("\nAll phases complete.")


def serve(port: int = 5000):
    os.environ.setdefault("FLASK_SECRET_KEY", os.urandom(24).hex())
    from chain.flask_app import app
    print(f"SUB-Terrainian dashboard → http://localhost:{port}")
    print("Open this URL in your Android browser (or MetaMask Mobile).")
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(0)

    cmd   = args[0].lower()
    force = "--force" in args
    plain = "--plain" in args
    rest  = [a for a in args[1:] if not a.startswith("--")]

    if cmd == "scan":
        run_scan(rest[0] if rest else None, force)
    elif cmd in ("art", "artwork"):
        run_artwork(force)
    elif cmd in ("port", "portraits"):
        run_portraits(force)
    elif cmd in ("lyr", "lyrics"):
        run_lyrics(force)
    elif cmd == "emit":
        run_emit(force, plain)
    elif cmd == "sync":
        sync_media(rest[0] if rest else None)
    elif cmd == "run":
        run_all(rest[0] if rest else None, force)
    elif cmd == "serve":
        port = int(rest[0]) if rest else 5000
        for a in args:
            if a.startswith("--port"):
                port = int(a.split("=")[-1]) if "=" in a else int(args[args.index(a)+1])
        serve(port)
    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
