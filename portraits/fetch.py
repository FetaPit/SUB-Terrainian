#!/usr/bin/env python3
"""
portraits/fetch.py  —  SUB-Terrainian Phase 3

Artist portrait fetcher.
Chain: MusicBrainz → Wikidata P18 → Wikimedia Commons.
Fallback: TheAudioDB (THEAUDIODB_KEY from .env).

Runs once per artist. Idempotent — skips artists with portrait_fetched_at set.
"""

import os
import re
import time
import sqlite3
import urllib.parse
from pathlib import Path

import requests
from dotenv import load_dotenv

from db.manifest import open_db, update_portrait, now_iso, get_artist_by_mbid
from db.phash import phash as compute_phash

load_dotenv()

HEADERS        = {"User-Agent": "SubTerrainian/0.1 ( contact@ptliveddesign.example )"}
PORTRAIT_DIR   = Path("portraits/cache")
TADB_KEY       = os.getenv("THEAUDIODB_KEY", "123")
_MB_LAST       = 0.0


# ── Rate-limited MB GET ───────────────────────────────────────────────────────

def _mb_get(url: str, params: dict = None) -> dict:
    global _MB_LAST
    elapsed = time.monotonic() - _MB_LAST
    if elapsed < 1.1:
        time.sleep(1.1 - elapsed)
    for attempt in range(4):
        r = requests.get(url, params=params, headers=HEADERS, timeout=15)
        _MB_LAST = time.monotonic()
        if r.status_code == 503:
            time.sleep(2 ** attempt)
            continue
        r.raise_for_status()
        return r.json()
    r.raise_for_status()


def _get(url: str, params: dict = None, stream: bool = False) -> requests.Response:
    return requests.get(url, params=params, headers=HEADERS, timeout=20, stream=stream)


# ── MusicBrainz → Wikidata QID ────────────────────────────────────────────────

def get_wikidata_qid(artist_mbid: str) -> str | None:
    try:
        data = _mb_get(
            f"https://musicbrainz.org/ws/2/artist/{artist_mbid}",
            params={"inc": "url-rels", "fmt": "json"},
        )
        for rel in data.get("relations", []):
            url = rel.get("url", {}).get("resource", "")
            if "wikidata.org/wiki/Q" in url:
                match = re.search(r"(Q\d+)$", url)
                if match:
                    return match.group(1)
    except Exception as e:
        print(f"    [MB url-rels error] {e}")
    return None


# ── Wikidata P18 → Commons filename ───────────────────────────────────────────

def get_commons_filename(qid: str) -> str | None:
    try:
        r = _get(
            f"https://www.wikidata.org/wiki/Special:EntityData/{qid}.json"
        )
        if r.status_code != 200:
            return None
        data = r.json()
        entity = data.get("entities", {}).get(qid, {})
        claims = entity.get("claims", {})
        p18 = claims.get("P18", [])
        if p18:
            return p18[0]["mainsnak"]["datavalue"]["value"]
    except Exception as e:
        print(f"    [Wikidata P18 error] {e}")
    return None


def commons_image_url(filename: str, width: int = 600) -> str:
    encoded = urllib.parse.quote(filename.replace(" ", "_"))
    return f"https://commons.wikimedia.org/wiki/Special:FilePath/{encoded}?width={width}"


# ── TheAudioDB fallback ────────────────────────────────────────────────────────

def get_tadb_portrait(artist_mbid: str) -> tuple[str, str] | None:
    """Returns (image_url, source_label) or None."""
    try:
        r = _get(
            f"https://www.theaudiodb.com/api/v1/json/{TADB_KEY}/artist-mb.php",
            params={"i": artist_mbid},
        )
        if r.status_code != 200:
            return None
        data = r.json()
        artists = data.get("artists")
        if not artists:
            return None
        a = artists[0]
        url = a.get("strArtistThumb") or a.get("strArtistFanart")
        if url:
            return url, "theaudiodb"
    except Exception as e:
        print(f"    [TheAudioDB error] {e}")
    return None


# ── Download + save ───────────────────────────────────────────────────────────

def download_portrait(url: str, dest: Path) -> bool:
    try:
        r = _get(url, stream=True)
        if r.status_code != 200:
            return False
        ct = r.headers.get("content-type", "")
        if "image" not in ct:
            return False
        dest.parent.mkdir(parents=True, exist_ok=True)
        with dest.open("wb") as f:
            for chunk in r.iter_content(8192):
                f.write(chunk)
        return True
    except Exception as e:
        print(f"    [download error] {e}")
        return False


# ── Main per-artist fetch ──────────────────────────────────────────────────────

def fetch_artist_portrait(artist_row: sqlite3.Row, con: sqlite3.Connection,
                          force: bool = False) -> bool:
    artist_id   = artist_row["id"]
    artist_mbid = artist_row["mbid"]
    artist_name = artist_row["name"]

    if not force and artist_row["portrait_fetched_at"]:
        return True  # already done

    if not artist_mbid or artist_mbid.startswith("local:"):
        print(f"  [skip] no MBID: {artist_name}")
        return False

    print(f"  {artist_name} ({artist_mbid})", end=" ")

    image_url = None
    source    = None

    # Chain: MB → Wikidata → Commons
    qid = get_wikidata_qid(artist_mbid)
    if qid:
        filename = get_commons_filename(qid)
        if filename:
            image_url = commons_image_url(filename)
            source    = "wikidata"
            print(f"→ Wikidata {qid}", end=" ")

    # Fallback: TheAudioDB
    if not image_url:
        result = get_tadb_portrait(artist_mbid)
        if result:
            image_url, source = result
            print(f"→ TheAudioDB", end=" ")

    if not image_url:
        print("→ no portrait found")
        update_portrait(con, artist_id, portrait_fetched_at=now_iso())
        return False

    # Download
    safe_name = re.sub(r'[^\w\-]', '_', artist_name)[:60]
    dest = PORTRAIT_DIR / f"{safe_name}.jpg"

    if not download_portrait(image_url, dest):
        print("→ download failed")
        return False

    # pHash
    try:
        phash_val = compute_phash(str(dest))
    except Exception:
        phash_val = None

    update_portrait(
        con, artist_id,
        portrait_source     = source,
        portrait_url        = image_url,
        portrait_path       = str(dest),
        portrait_phash      = phash_val,
        portrait_fetched_at = now_iso(),
    )

    print(f"→ saved ({dest.name})")
    return True


def fetch_all_portraits(db_path: str = "sub_terrainian.db", force: bool = False):
    PORTRAIT_DIR.mkdir(parents=True, exist_ok=True)
    con = open_db(db_path)

    artists = con.execute(
        "SELECT * FROM artist WHERE portrait_fetched_at IS NULL OR ? = 1",
        (1 if force else 0,),
    ).fetchall()

    ok = failed = skipped = 0
    print(f"Fetching portraits for {len(artists)} artist(s)…")

    for artist in artists:
        if not artist["mbid"] or artist["mbid"].startswith("local:"):
            skipped += 1
            continue
        if fetch_artist_portrait(artist, con, force):
            ok += 1
        else:
            failed += 1
        time.sleep(0.5)  # courtesy delay between artists

    con.close()
    print(f"\nDone. OK: {ok}  Failed: {failed}  Skipped: {skipped}")


if __name__ == "__main__":
    import sys
    force = "--force" in sys.argv
    fetch_all_portraits(force=force)
