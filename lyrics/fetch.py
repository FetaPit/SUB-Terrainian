#!/usr/bin/env python3
"""
lyrics/fetch.py  —  SUB-Terrainian Phase 4

LRCLIB lyrics ingestion. Stores in manifest — does NOT write .lrc files.
Use lyrics/emit.py to write .lrc sidecars for Musicolet.

Tier 1: exact match  (artist + title + album + duration)
Tier 2: fuzzy search (artist + title)
Tier 3: plain text only (no synced lyrics available)
"""

import time
import sqlite3

import requests

from db.manifest import open_db, update_lyrics, all_tracks_needing_lyrics, now_iso

HEADERS  = {"User-Agent": "SubTerrainian/0.1 ( contact@ptliveddesign.example )"}
LRCLIB   = "https://lrclib.net/api"
SLEEP    = 0.4  # courtesy delay — LRCLIB has no published rate limit


# ── LRCLIB client ─────────────────────────────────────────────────────────────

def _get(endpoint: str, params: dict) -> dict | list | None:
    try:
        r = requests.get(
            f"{LRCLIB}/{endpoint}",
            params=params,
            headers=HEADERS,
            timeout=10,
        )
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"    [LRCLIB error] {e}")
        return None


def fetch_lrclib(title: str, artist: str, album: str = None,
                 duration_ms: int = None) -> dict | None:
    """
    Returns LRCLIB result dict with syncedLyrics / plainLyrics / id,
    or None if nothing found.
    """
    duration_s = round(duration_ms / 1000) if duration_ms else None

    # Tier 1: exact match
    params = {"track_name": title, "artist_name": artist}
    if album:
        params["album_name"] = album
    if duration_s:
        params["duration"] = duration_s

    result = _get("get", params)
    if result and (result.get("syncedLyrics") or result.get("plainLyrics")):
        result["_tier"] = 1
        return result

    time.sleep(SLEEP)

    # Tier 2: fuzzy search
    results = _get("search", {"track_name": title, "artist_name": artist})
    if results and isinstance(results, list):
        for r in results:
            if r.get("syncedLyrics"):
                r["_tier"] = 2
                return r
        for r in results:
            if r.get("plainLyrics"):
                r["_tier"] = 2
                return r

    return None


# ── Manifest writer ───────────────────────────────────────────────────────────

def _source_label(result: dict) -> str:
    if result.get("syncedLyrics"):
        return "lrclib_synced"
    return "lrclib_plain"


def process_track(track: sqlite3.Row, con: sqlite3.Connection,
                  artist_name: str, album_title: str,
                  force: bool = False) -> str:
    """
    Fetch and store lyrics for one track.
    Returns: 'synced' | 'plain' | 'miss' | 'skip'
    """
    if not force and track["lyrics_fetched_at"]:
        return "skip"

    if not track["title"]:
        return "miss"

    print(f"    [{track['track_number']:02d}] {track['title']}", end=" ")

    result = fetch_lrclib(
        title       = track["title"],
        artist      = artist_name,
        album       = album_title,
        duration_ms = track["duration_ms"],
    )

    if result is None:
        print("→ miss")
        update_lyrics(con, track["id"], lyrics_fetched_at=now_iso())
        return "miss"

    synced = result.get("syncedLyrics")
    plain  = result.get("plainLyrics")
    tier   = result.get("_tier", 1)

    update_lyrics(
        con, track["id"],
        lyrics_source      = _source_label(result),
        lyrics_plain       = plain,
        lyrics_synced      = synced,
        lyrics_fetched_at  = now_iso(),
        lyrics_lrclib_id   = result.get("id"),
    )

    if synced:
        print(f"→ synced (tier {tier})")
        return "synced"
    else:
        print(f"→ plain only (tier {tier})")
        return "plain"


# ── Full manifest pass ────────────────────────────────────────────────────────

def fetch_all_lyrics(db_path: str = "sub_terrainian.db", force: bool = False):
    con = open_db(db_path)
    tracks = all_tracks_needing_lyrics(con) if not force else con.execute(
        "SELECT * FROM track WHERE file_path IS NOT NULL"
    ).fetchall()

    synced = plain = miss = skip = 0
    print(f"Fetching lyrics for {len(tracks)} track(s)…\n")

    # Group by release for context
    release_cache = {}
    artist_cache  = {}

    for track in tracks:
        release_id = track["release_id"]

        if release_id not in release_cache:
            row = con.execute(
                "SELECT r.title, r.artist_id, a.name "
                "FROM release r LEFT JOIN artist a ON a.id = r.artist_id "
                "WHERE r.id = ?", (release_id,)
            ).fetchone()
            release_cache[release_id] = row["title"] if row else ""
            artist_cache[release_id]  = row["name"]  if row else ""

        album_title = release_cache[release_id]
        artist_name = artist_cache[release_id]

        result = process_track(track, con, artist_name, album_title, force)
        if result == "synced": synced += 1
        elif result == "plain": plain  += 1
        elif result == "miss":  miss   += 1
        else:                   skip   += 1

        time.sleep(SLEEP)

    con.close()
    print(f"\nDone. Synced: {synced}  Plain: {plain}  Miss: {miss}  Skipped: {skip}")


if __name__ == "__main__":
    import sys
    force = "--force" in sys.argv
    fetch_all_lyrics(force=force)
