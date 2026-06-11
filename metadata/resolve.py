#!/usr/bin/env python3
"""
metadata/resolve.py  —  SUB-Terrainian Phase 1

Resolves a music library folder tree to MusicBrainz IDs.
For each album folder: reads audio tags → finds MBID → stores in manifest.
Must run before Phases 2 / 3 / 4.

MusicBrainz rate limit: 1 req/sec strictly enforced.
"""

import os
import re
import time
import sqlite3
from pathlib import Path

import requests
from mutagen import File as MutagenFile

from db.manifest import open_db, upsert_artist, upsert_release, upsert_track, now_iso

HEADERS    = {"User-Agent": "SubTerrainian/0.1 ( contact@ptliveddesign.example )"}
MB_API     = "https://musicbrainz.org/ws/2"
_LAST_CALL = 0.0
AUDIO_EXTS = {".mp3", ".flac", ".m4a", ".ogg", ".opus", ".wav", ".aac", ".wma", ".ape"}


# ── Rate limiter ──────────────────────────────────────────────────────────────

def _mb_get(url: str, params: dict = None) -> dict:
    global _LAST_CALL
    elapsed = time.monotonic() - _LAST_CALL
    if elapsed < 1.1:
        time.sleep(1.1 - elapsed)
    for attempt in range(4):
        r = requests.get(url, params=params, headers=HEADERS, timeout=15)
        _LAST_CALL = time.monotonic()
        if r.status_code == 503:
            time.sleep(2 ** attempt)
            continue
        r.raise_for_status()
        return r.json()
    r.raise_for_status()


# ── Tag extraction ────────────────────────────────────────────────────────────

def _tag(audio, *keys: str) -> str | None:
    if audio is None or audio.tags is None:
        return None
    for key in keys:
        val = audio.tags.get(key)
        if val:
            v = val[0] if isinstance(val, list) else val
            s = str(v).strip()
            if s:
                return s
    return None


def read_folder_tags(folder: Path) -> dict:
    """Read artist/album/MBID from the first tagged audio file in a folder."""
    for f in sorted(folder.iterdir()):
        if f.suffix.lower() not in AUDIO_EXTS:
            continue
        try:
            audio = MutagenFile(f, easy=True)
            if audio is None:
                continue
            artist = _tag(audio, "artist", "albumartist", "album artist")
            album  = _tag(audio, "album")
            mbid   = _tag(audio, "musicbrainz_albumid", "MusicBrainz Album Id")
            year   = _tag(audio, "date", "year")[:4] if _tag(audio, "date", "year") else None
            label  = _tag(audio, "organization", "label", "publisher")
            if artist or album:
                return {
                    "artist": artist, "album": album, "mbid": mbid,
                    "year": year, "label": label,
                }
        except Exception:
            continue
    return {}


def read_track_tags(file: Path) -> dict:
    """Read per-track metadata from a single audio file."""
    try:
        audio = MutagenFile(file, easy=True)
        if audio is None:
            return {}
        title    = _tag(audio, "title")
        track_no = _tag(audio, "tracknumber")
        disc_no  = _tag(audio, "discnumber")
        duration = int(audio.info.length * 1000) if hasattr(audio, "info") else None
        isrc     = _tag(audio, "isrc")
        t_mbid   = _tag(audio, "musicbrainz_trackid")

        def _parse_no(s):
            if s and re.match(r"^\d+", s):
                return int(re.match(r"^(\d+)", s).group(1))
            return None

        return {
            "title":       title,
            "track_number": _parse_no(track_no) or 1,
            "disc_number":  _parse_no(disc_no)  or 1,
            "duration_ms":  duration,
            "isrc":         isrc,
            "mbid":         t_mbid,
        }
    except Exception:
        return {}


# ── MusicBrainz lookup ────────────────────────────────────────────────────────

def search_release(artist: str, album: str) -> str | None:
    """Search MusicBrainz for a release and return its MBID."""
    try:
        data = _mb_get(
            f"{MB_API}/release",
            params={
                "query": f'artist:"{artist}" AND release:"{album}"',
                "fmt": "json",
                "limit": 1,
            },
        )
        releases = data.get("releases", [])
        if releases:
            return releases[0]["id"]
    except Exception as e:
        print(f"  [MB search error] {e}")
    return None


def fetch_release_detail(mbid: str) -> dict:
    """Fetch full release detail including artist credits and track listing."""
    try:
        return _mb_get(
            f"{MB_API}/release/{mbid}",
            params={"inc": "artist-credits recordings labels", "fmt": "json"},
        )
    except Exception as e:
        print(f"  [MB detail error] {e}")
        return {}


def fetch_artist_mbid(release_detail: dict) -> tuple[str, str, str] | None:
    """Return (artist_mbid, artist_name, sort_name) from release detail."""
    credits = release_detail.get("artist-credit", [])
    for credit in credits:
        if isinstance(credit, dict) and "artist" in credit:
            a = credit["artist"]
            return a.get("id"), a.get("name"), a.get("sort-name")
    return None, None, None


# ── Folder scanner ────────────────────────────────────────────────────────────

def resolve_folder(folder: Path, con: sqlite3.Connection, force: bool = False) -> bool:
    """
    Resolve one album folder to a MusicBrainz MBID and write to manifest.
    Returns True if successfully resolved.
    """
    audio_files = [f for f in folder.iterdir() if f.suffix.lower() in AUDIO_EXTS]
    if not audio_files:
        return False

    tags = read_folder_tags(folder)
    artist_name = tags.get("artist")
    album_title = tags.get("album")
    mbid        = tags.get("mbid")

    if not artist_name or not album_title:
        print(f"  [skip] no tags: {folder.name}")
        return False

    print(f"  {artist_name} — {album_title}", end=" ")

    # Check if already resolved (idempotent)
    existing = con.execute(
        "SELECT id FROM release WHERE mbid = ?", (mbid,)
    ).fetchone() if mbid else None

    if existing and not force:
        print("(already in manifest)")
        return True

    # Resolve MBID via MusicBrainz search if not in tags
    if not mbid:
        mbid = search_release(artist_name, album_title)
        if not mbid:
            print("(not found)")
            return False

    # Fetch full release detail
    detail = fetch_release_detail(mbid)
    if not detail:
        print("(detail fetch failed)")
        return False

    # Resolve artist
    a_mbid, a_name, a_sort = fetch_artist_mbid(detail)
    if a_mbid:
        artist_id = upsert_artist(con, a_mbid, a_name or artist_name, a_sort)
    else:
        artist_id = upsert_artist(con, f"local:{artist_name}", artist_name)

    # Parse release date
    date  = detail.get("date") or tags.get("year") or ""
    year  = int(date[:4]) if date and date[:4].isdigit() else None
    label = None
    if detail.get("label-info"):
        li = detail["label-info"]
        if li and isinstance(li, list) and li[0].get("label"):
            label = li[0]["label"].get("name")
    label = label or tags.get("label")

    # Count tracks from media
    track_count = sum(
        m.get("track-count", 0) for m in detail.get("media", [])
    ) or len(audio_files)

    release_id = upsert_release(
        con, mbid, detail.get("title") or album_title,
        artist_id=artist_id,
        date=date,
        year=year,
        label=label,
        catalog_number=detail.get("catalog-number"),
        country=detail.get("country"),
        track_count=track_count,
        folder_path=str(folder.resolve()),
    )

    # Write tracks from audio files
    for audio_file in sorted(audio_files):
        t = read_track_tags(audio_file)
        if not t.get("title"):
            t["title"] = audio_file.stem
        upsert_track(
            con, release_id, t["title"], t.get("track_number", 1),
            disc_number=t.get("disc_number", 1),
            duration_ms=t.get("duration_ms"),
            isrc=t.get("isrc"),
            mbid=t.get("mbid"),
            file_path=str(audio_file.resolve()),
        )

    print(f"→ {mbid}")
    return True


def resolve_library(music_root: str, db_path: str = "sub_terrainian.db",
                    force: bool = False):
    """Walk a music library and resolve all album folders."""
    root = Path(music_root)
    if not root.exists():
        raise FileNotFoundError(f"Music root not found: {music_root}")

    con = open_db(db_path)
    ok = skipped = failed = 0

    print(f"Scanning: {root}")
    for folder in sorted(root.rglob("*")):
        if not folder.is_dir():
            continue
        audio = [f for f in folder.iterdir() if f.suffix.lower() in AUDIO_EXTS]
        if not audio:
            continue
        print(f"\n[{folder.name}]")
        if resolve_folder(folder, con, force):
            ok += 1
        else:
            failed += 1

    con.close()
    print(f"\nDone. Resolved: {ok}  Failed: {failed}")


if __name__ == "__main__":
    import sys
    root = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser("~/storage/shared/Music")
    resolve_library(root)
