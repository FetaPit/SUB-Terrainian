#!/usr/bin/env python3
"""
artwork/fetch.py  —  SUB-Terrainian Phase 2

Album artwork resolver.
Chain: MusicBrainz / Cover Art Archive → iTunes → Deezer.
Writes folder.jpg into album folder and embeds in audio tags via mutagen.

NOTE: The full implementation of this phase is in fetch_v3.py (on device,
pending recovery to repo). This file provides the canonical module structure
and the iTunes + Deezer fallback chain that fetch_v3.py's flat script does not
yet export as functions. Once fetch_v3.py is recovered, its logic moves here.
"""

import io
import time
import sqlite3
from pathlib import Path

import requests
from PIL import Image
from mutagen import File as MutagenFile
from mutagen.id3 import ID3, APIC, error as ID3Error
from mutagen.flac import FLAC, Picture
from mutagen.mp4 import MP4, MP4Cover

from db.manifest import open_db, update_artwork, all_releases_needing_artwork, now_iso
from db.phash import phash as compute_phash

HEADERS      = {"User-Agent": "SubTerrainian/0.1 ( contact@ptliveddesign.example )"}
ARTWORK_SIZE = 600   # target JPEG dimension (px)
_MB_LAST     = 0.0


def _mb_get(url: str, **kwargs) -> requests.Response:
    global _MB_LAST
    elapsed = time.monotonic() - _MB_LAST
    if elapsed < 1.1:
        time.sleep(1.1 - elapsed)
    for attempt in range(4):
        r = requests.get(url, headers=HEADERS, timeout=20, **kwargs)
        _MB_LAST = time.monotonic()
        if r.status_code == 503:
            time.sleep(2 ** attempt)
            continue
        return r
    return r


def _get(url: str, **kwargs) -> requests.Response:
    return requests.get(url, headers=HEADERS, timeout=20, **kwargs)


# ── Source chain ──────────────────────────────────────────────────────────────

def fetch_caa(mbid: str) -> bytes | None:
    for size in ["1200", "500", ""]:
        suffix = f"-{size}" if size else ""
        r = _mb_get(
            f"https://coverartarchive.org/release/{mbid}/front{suffix}",
            allow_redirects=True,
        )
        if r.status_code == 200 and "image" in r.headers.get("content-type", ""):
            return r.content
    return None


def fetch_itunes(artist: str, album: str) -> bytes | None:
    try:
        r = _get(
            "https://itunes.apple.com/search",
            params={"term": f"{artist} {album}", "entity": "album", "limit": 1},
        )
        if r.status_code != 200:
            return None
        results = r.json().get("results", [])
        if not results:
            return None
        art_url = results[0].get("artworkUrl100", "").replace("100x100bb", "600x600bb")
        if not art_url:
            return None
        ri = _get(art_url)
        if ri.status_code == 200 and "image" in ri.headers.get("content-type", ""):
            return ri.content
    except Exception:
        pass
    return None


def fetch_deezer(artist: str, album: str) -> bytes | None:
    try:
        r = _get(
            "https://api.deezer.com/search/album",
            params={"q": f"{artist} {album}", "limit": 1},
        )
        if r.status_code != 200:
            return None
        items = r.json().get("data", [])
        if not items:
            return None
        cover = items[0].get("cover_xl") or items[0].get("cover_big")
        if not cover:
            return None
        ri = _get(cover)
        if ri.status_code == 200 and "image" in ri.headers.get("content-type", ""):
            return ri.content
    except Exception:
        pass
    return None


# ── Image processing ──────────────────────────────────────────────────────────

def resize_jpeg(data: bytes, size: int = ARTWORK_SIZE) -> bytes:
    img = Image.open(io.BytesIO(data)).convert("RGB")
    img.thumbnail((size, size), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85, optimize=True)
    return buf.getvalue()


# ── Tag embedding ─────────────────────────────────────────────────────────────

def embed_artwork(file_path: str, jpeg_data: bytes):
    """Embed artwork into audio file tags (MP3, FLAC, M4A)."""
    path = Path(file_path)
    ext  = path.suffix.lower()
    try:
        if ext == ".mp3":
            try:
                tags = ID3(file_path)
            except ID3Error:
                tags = ID3()
            tags.delall("APIC")
            tags.add(APIC(encoding=3, mime="image/jpeg", type=3,
                          desc="Cover", data=jpeg_data))
            tags.save(file_path)

        elif ext == ".flac":
            audio = FLAC(file_path)
            pic = Picture()
            pic.type = 3
            pic.mime = "image/jpeg"
            pic.data = jpeg_data
            audio.clear_pictures()
            audio.add_picture(pic)
            audio.save()

        elif ext in (".m4a", ".aac", ".mp4"):
            audio = MP4(file_path)
            audio["covr"] = [MP4Cover(jpeg_data, imageformat=MP4Cover.FORMAT_JPEG)]
            audio.save()
    except Exception as e:
        print(f"    [embed error] {path.name}: {e}")


# ── Main per-release fetch ────────────────────────────────────────────────────

def fetch_release_artwork(release: sqlite3.Row, con: sqlite3.Connection,
                          force: bool = False) -> bool:
    if not force and release["artwork_fetched_at"]:
        return True

    mbid        = release["mbid"]
    folder      = Path(release["folder_path"]) if release["folder_path"] else None
    artist_row  = con.execute(
        "SELECT name FROM artist WHERE id = ?", (release["artist_id"],)
    ).fetchone() if release["artist_id"] else None

    artist_name = artist_row["name"] if artist_row else ""
    album_title = release["title"]

    print(f"  {artist_name} — {album_title}", end=" ")

    # Try CAA first
    data   = fetch_caa(mbid)
    source = "caa"

    # iTunes fallback
    if not data and artist_name:
        data   = fetch_itunes(artist_name, album_title)
        source = "itunes"

    # Deezer fallback
    if not data and artist_name:
        data   = fetch_deezer(artist_name, album_title)
        source = "deezer"

    if not data:
        print("→ not found")
        update_artwork(con, release["id"], artwork_fetched_at=now_iso())
        return False

    jpeg = resize_jpeg(data)

    # Write folder.jpg
    if folder and folder.exists():
        dest = folder / "folder.jpg"
        dest.write_bytes(jpeg)

        # Embed in all audio files in folder
        for audio_file in folder.iterdir():
            if audio_file.suffix.lower() in {".mp3", ".flac", ".m4a", ".aac", ".mp4"}:
                embed_artwork(str(audio_file), jpeg)

        # pHash
        try:
            phash_val = compute_phash(str(dest))
        except Exception:
            phash_val = None

        update_artwork(
            con, release["id"],
            artwork_source     = source,
            artwork_path       = str(dest),
            artwork_fetched_at = now_iso(),
        )
        print(f"→ {source} ({len(jpeg)//1024}KB)")
        return True

    print("→ no folder path")
    return False


def fetch_all_artwork(db_path: str = "sub_terrainian.db", force: bool = False):
    con = open_db(db_path)
    releases = all_releases_needing_artwork(con) if not force else \
        con.execute("SELECT * FROM release WHERE folder_path IS NOT NULL").fetchall()

    ok = failed = 0
    print(f"Fetching artwork for {len(releases)} release(s)…\n")

    for release in releases:
        if fetch_release_artwork(release, con, force):
            ok += 1
        else:
            failed += 1

    con.close()
    print(f"\nDone. OK: {ok}  Failed: {failed}")


if __name__ == "__main__":
    import sys
    force = "--force" in sys.argv
    fetch_all_artwork(force=force)
