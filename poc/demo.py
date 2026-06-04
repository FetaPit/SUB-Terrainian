#!/usr/bin/env python3
"""
poc/demo.py  —  SUB-Terrainian PoC Demo

Runs the full pipeline on a small sample (default 10 albums) and
produces a report showing coverage: artwork %, lyrics %, portrait %.

Designed to generate proof-of-concept evidence for player partnership outreach.

Usage:
    python poc/demo.py                         # 10-album sample from default root
    python poc/demo.py --all                   # full library
    python poc/demo.py --sample 20             # custom sample size
    python poc/demo.py --report-only           # just show stats, no pipeline run
"""

import os
import sys
import json
import time
import random
import sqlite3
from pathlib import Path
from datetime import datetime

from dotenv import load_dotenv

load_dotenv()

DB_PATH    = os.getenv("MANIFEST_PATH", "sub_terrainian.db")
MUSIC_ROOT = os.getenv("MUSIC_ROOT", os.path.expanduser("~/storage/shared/Music"))


def get_db() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def db_exists() -> bool:
    return Path(DB_PATH).exists()


def print_banner():
    print("""
╔═══════════════════════════════════════════════╗
║        SUB-Terrainian  ·  PoC Demo            ║
║        PT Lived Design  ·  Lincoln UK         ║
╚═══════════════════════════════════════════════╝
""")


def run_phase(cmd: list[str], label: str):
    import subprocess
    print(f"\n  ▶ {label}…")
    start = time.monotonic()
    result = subprocess.run(
        cmd, capture_output=False, text=True,
        cwd=str(Path(__file__).parent.parent),
    )
    elapsed = time.monotonic() - start
    status = "✓" if result.returncode == 0 else "✗"
    print(f"  {status} {label} ({elapsed:.0f}s)")
    return result.returncode == 0


def coverage_report(con: sqlite3.Connection, sample_ids: list[int] | None = None) -> dict:
    """Calculate coverage stats for a set of release IDs (or all)."""
    where = ""
    params_r = []
    if sample_ids:
        placeholders = ",".join("?" * len(sample_ids))
        where    = f"WHERE id IN ({placeholders})"
        params_r = sample_ids

    releases = con.execute(
        f"SELECT COUNT(*) FROM release {where}", params_r
    ).fetchone()[0]

    art = con.execute(
        f"SELECT COUNT(*) FROM release {where} {'AND' if where else 'WHERE'} "
        "artwork_fetched_at IS NOT NULL",
        params_r,
    ).fetchone()[0]

    tracks_where = ""
    params_t = []
    if sample_ids:
        tracks_where = f"WHERE release_id IN ({placeholders})"
        params_t = sample_ids

    tracks = con.execute(
        f"SELECT COUNT(*) FROM track {tracks_where}", params_t
    ).fetchone()[0]

    lyr_synced = con.execute(
        f"SELECT COUNT(*) FROM track {tracks_where} "
        f"{'AND' if tracks_where else 'WHERE'} lyrics_synced IS NOT NULL",
        params_t,
    ).fetchone()[0]

    lyr_any = con.execute(
        f"SELECT COUNT(*) FROM track {tracks_where} "
        f"{'AND' if tracks_where else 'WHERE'} lyrics_fetched_at IS NOT NULL",
        params_t,
    ).fetchone()[0]

    artists = con.execute(
        f"SELECT COUNT(DISTINCT artist_id) FROM release {where}", params_r
    ).fetchone()[0] if releases else 0

    portraits = con.execute(
        "SELECT COUNT(*) FROM artist WHERE portrait_fetched_at IS NOT NULL"
    ).fetchone()[0]

    return {
        "releases":      releases,
        "art_done":      art,
        "art_pct":       round(art / releases * 100) if releases else 0,
        "tracks":        tracks,
        "lyr_synced":    lyr_synced,
        "lyr_any":       lyr_any,
        "lyr_synced_pct": round(lyr_synced / tracks * 100) if tracks else 0,
        "lyr_any_pct":   round(lyr_any / tracks * 100) if tracks else 0,
        "artists":       artists,
        "portraits":     portraits,
        "portrait_pct":  round(portraits / artists * 100) if artists else 0,
    }


def player_compat_table(cov: dict) -> str:
    rows = [
        ("Musicolet",     "folder.jpg",      str(cov["art_pct"]) + "%",
                          ".lrc sidecar",    str(cov["lyr_synced_pct"]) + "%"),
        ("Samsung Music", "embedded tag",    str(cov["art_pct"]) + "%",
                          "embedded (ID3)",  "—"),
        ("Poweramp",      "folder.jpg",      str(cov["art_pct"]) + "%",
                          ".lrc sidecar",    str(cov["lyr_synced_pct"]) + "%"),
        ("BlackPlayer",   "folder.jpg",      str(cov["art_pct"]) + "%",
                          ".lrc sidecar",    str(cov["lyr_synced_pct"]) + "%"),
        ("VLC Android",   "embedded tag",    str(cov["art_pct"]) + "%",
                          ".lrc sidecar",    str(cov["lyr_synced_pct"]) + "%"),
    ]
    lines = [
        "\n  Player compatibility after this run:",
        f"  {'Player':<16} {'Artwork method':<18} {'Art%':>5}  {'Lyrics method':<18} {'Lyr%':>5}",
        "  " + "─" * 72,
    ]
    for row in rows:
        lines.append(f"  {row[0]:<16} {row[1]:<18} {row[2]:>5}  {row[3]:<18} {row[4]:>5}")
    return "\n".join(lines)


def print_report(cov: dict, sample_size: int | None, elapsed: float):
    print(f"""
╔═══════════════════════════════════════════════╗
║          SUB-Terrainian  ·  PoC Report        ║
╚═══════════════════════════════════════════════╝

  Run date : {datetime.now().strftime("%d %b %Y  %H:%M")}
  Duration : {elapsed:.0f}s
  Sample   : {sample_size or 'Full library'}

  ┌─ Library ─────────────────────────────────┐
  │ Albums   : {cov['releases']:>5}                           │
  │ Tracks   : {cov['tracks']:>5}                           │
  │ Artists  : {cov['artists']:>5}                           │
  └───────────────────────────────────────────┘

  ┌─ Enrichment coverage ─────────────────────┐
  │ Artwork          : {cov['art_done']:>4} / {cov['releases']:<4} ({cov['art_pct']:>3}%)        │
  │ Synced lyrics    : {cov['lyr_synced']:>4} / {cov['tracks']:<4} tracks ({cov['lyr_synced_pct']:>3}%)  │
  │ Any lyrics       : {cov['lyr_any']:>4} / {cov['tracks']:<4} tracks ({cov['lyr_any_pct']:>3}%)  │
  │ Artist portraits : {cov['portraits']:>4} / {cov['artists']:<4} ({cov['portrait_pct']:>3}%)        │
  └───────────────────────────────────────────┘
""")
    print(player_compat_table(cov))
    print(f"""

  To refresh all music players:
    python sub_terrainian.py sync

  To open the dashboard:
    python sub_terrainian.py serve
    → http://localhost:5000

  Musicolet partnership contact:
    Maulik Raviya / Krosbits
    See MUSICOLET_PARTNERSHIP.md for outreach template.
""")


def save_report_json(cov: dict, sample_size: int | None, elapsed: float):
    out = {
        "generated_at": datetime.now().isoformat(),
        "sample_size":  sample_size or "all",
        "duration_s":   round(elapsed, 1),
        "coverage":     cov,
    }
    path = Path("poc/last_report.json")
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(out, indent=2))
    print(f"  Report saved to {path}")


def main():
    args       = sys.argv[1:]
    run_all    = "--all" in args
    report_only= "--report-only" in args
    sample_n   = 10
    for a in args:
        if a.startswith("--sample="):
            sample_n = int(a.split("=")[1])
        elif a == "--sample" and args[args.index(a) + 1:]:
            sample_n = int(args[args.index(a) + 1])

    print_banner()

    if not db_exists() and report_only:
        print("  No manifest found. Run a scan first:")
        print("    python sub_terrainian.py scan ~/storage/shared/Music")
        sys.exit(1)

    if not report_only:
        # Step 1: ensure manifest exists (run scan if not)
        if not db_exists():
            print("  No manifest — running Phase 1 scan first…")
            run_phase(
                [sys.executable, "sub_terrainian.py", "scan", MUSIC_ROOT],
                "Phase 1: MBID resolve",
            )

        # Pick a sample of release IDs to demo
        con = get_db()
        if run_all:
            sample_ids = None
            print(f"\n  Running full library pipeline…")
        else:
            all_ids = [r[0] for r in con.execute(
                "SELECT id FROM release ORDER BY RANDOM() LIMIT ?", (sample_n,)
            ).fetchall()]
            sample_ids = all_ids
            print(f"\n  Running pipeline on {len(sample_ids)}-album sample…")
        con.close()

        start = time.monotonic()
        py = sys.executable

        # Run phases — artwork, portraits, lyrics, emit
        run_phase([py, "sub_terrainian.py", "art"],  "Phase 2: artwork")
        run_phase([py, "sub_terrainian.py", "port"], "Phase 3: portraits")
        run_phase([py, "sub_terrainian.py", "lyr"],  "Phase 4: lyrics")
        run_phase([py, "sub_terrainian.py", "emit", "--plain"], "Emit .lrc sidecars")
        run_phase([py, "sub_terrainian.py", "sync"], "MediaStore sync")

        elapsed = time.monotonic() - start
    else:
        start = time.monotonic()
        elapsed = 0
        sample_ids = None

    con = get_db()
    cov = coverage_report(con, sample_ids if not run_all else None)
    con.close()

    print_report(cov, None if run_all else sample_n, elapsed)
    save_report_json(cov, None if run_all else sample_n, elapsed)


if __name__ == "__main__":
    main()
