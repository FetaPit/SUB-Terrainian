#!/usr/bin/env python3
"""
lyrics/emit.py  —  SUB-Terrainian

Emits .lrc sidecars from the manifest to the filesystem next to each audio file.
Intentionally decoupled from ingestion (lyrics/fetch.py).

Only writes when:
  - Track has lyrics_synced in the manifest
  - The .lrc file does not already exist (idempotent)
  - file_path is set and the audio file exists

Usage:
    python lyrics/emit.py                   # emit all pending
    python lyrics/emit.py --force           # overwrite existing .lrc files
    python lyrics/emit.py --plain           # also emit plain .txt for tracks with no LRC
"""

from pathlib import Path
import sys

from db.manifest import open_db


def emit_lrc(track, force: bool = False, emit_plain: bool = False) -> str:
    """
    Write .lrc (or .txt) sidecar for one track.
    Returns: 'lrc' | 'txt' | 'skip' | 'no_file'
    """
    if not track["file_path"]:
        return "no_file"

    audio = Path(track["file_path"])
    if not audio.exists():
        return "no_file"

    base = audio.with_suffix("")

    if track["lyrics_synced"]:
        dest = base.with_suffix(".lrc")
        if dest.exists() and not force:
            return "skip"
        dest.write_text(track["lyrics_synced"], encoding="utf-8")
        return "lrc"

    if emit_plain and track["lyrics_plain"]:
        dest = base.with_suffix(".txt")
        if dest.exists() and not force:
            return "skip"
        dest.write_text(track["lyrics_plain"], encoding="utf-8")
        return "txt"

    return "skip"


def emit_all(db_path: str = "sub_terrainian.db",
             force: bool = False,
             emit_plain: bool = False):
    con = open_db(db_path)

    tracks = con.execute(
        """
        SELECT * FROM track
        WHERE (lyrics_synced IS NOT NULL OR lyrics_plain IS NOT NULL)
          AND file_path IS NOT NULL
        """
    ).fetchall()

    lrc = txt = skipped = no_file = 0
    print(f"Emitting sidecars for {len(tracks)} track(s)…")

    for track in tracks:
        result = emit_lrc(track, force=force, emit_plain=emit_plain)
        if   result == "lrc":     lrc     += 1
        elif result == "txt":     txt     += 1
        elif result == "skip":    skipped += 1
        elif result == "no_file": no_file += 1

    con.close()
    print(f"\nDone. .lrc: {lrc}  .txt: {txt}  Skipped: {skipped}  File missing: {no_file}")


if __name__ == "__main__":
    force      = "--force" in sys.argv
    emit_plain = "--plain" in sys.argv
    emit_all(force=force, emit_plain=emit_plain)
