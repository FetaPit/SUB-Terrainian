#!/usr/bin/env python3
"""
physical/scan.py  —  SUB-Terrainian Sprint 4

Barcode → Discogs → MusicBrainz verification for physical release claims.
On Termux: reads barcode via stdin or zbar (pkg install zbar).
Returns a verified MBID or raises.
"""

import os
import re
import time

import requests
from dotenv import load_dotenv

load_dotenv()

HEADERS  = {"User-Agent": "SubTerrainian/0.1 ( contact@ptliveddesign.example )"}
_MB_LAST = 0.0

DISCOGS_TOKEN = os.getenv("DISCOGS_TOKEN", "")


# ── Rate-limited MB GET ───────────────────────────────────────────────────────

def _mb_get(url: str, params: dict = None) -> dict:
    global _MB_LAST
    elapsed = time.monotonic() - _MB_LAST
    if elapsed < 1.1:
        time.sleep(1.1 - elapsed)
    r = requests.get(url, params=params, headers=HEADERS, timeout=15)
    _MB_LAST = time.monotonic()
    r.raise_for_status()
    return r.json()


# ── Barcode input ─────────────────────────────────────────────────────────────

def read_barcode_stdin() -> str:
    """Read a barcode typed or pasted into stdin."""
    barcode = input("Scan or enter barcode: ").strip()
    if not re.match(r"^\d{8,14}$", barcode):
        raise ValueError(f"Invalid barcode format: {barcode}")
    return barcode


def read_barcode_zbar(image_path: str) -> str | None:
    """
    Decode a barcode from an image file using zbar.
    Requires: pkg install zbar (Termux) or apt install zbar-tools (Debian).
    """
    import subprocess
    result = subprocess.run(
        ["zbarimg", "--quiet", "--raw", image_path],
        capture_output=True, text=True,
    )
    if result.returncode == 0 and result.stdout.strip():
        return result.stdout.strip().split("\n")[0]
    return None


# ── Discogs lookup ────────────────────────────────────────────────────────────

def discogs_lookup(barcode: str) -> list[dict]:
    """
    Search Discogs by barcode. Returns list of release candidates.
    Each has 'title', 'catno', 'country', 'year', 'resource_url'.
    """
    headers = dict(HEADERS)
    if DISCOGS_TOKEN:
        headers["Authorization"] = f"Discogs token={DISCOGS_TOKEN}"

    r = requests.get(
        "https://api.discogs.com/database/search",
        params={"barcode": barcode, "type": "release"},
        headers=headers,
        timeout=15,
    )
    r.raise_for_status()
    results = r.json().get("results", [])
    return [
        {
            "title":        r.get("title", ""),
            "catno":        r.get("catno", ""),
            "country":      r.get("country", ""),
            "year":         r.get("year", ""),
            "resource_url": r.get("resource_url", ""),
            "thumb":        r.get("thumb", ""),
        }
        for r in results[:5]
    ]


# ── MusicBrainz barcode lookup ────────────────────────────────────────────────

def mb_lookup_barcode(barcode: str) -> str | None:
    """Direct MusicBrainz barcode search. Returns MBID or None."""
    try:
        data = _mb_get(
            "https://musicbrainz.org/ws/2/release",
            params={
                "query": f"barcode:{barcode}",
                "fmt": "json",
                "limit": 1,
            },
        )
        releases = data.get("releases", [])
        if releases and releases[0].get("score", 0) > 80:
            return releases[0]["id"]
    except Exception as e:
        print(f"  [MB barcode error] {e}")
    return None


def mb_lookup_catno(catno: str, artist_hint: str = None) -> str | None:
    """MusicBrainz catalogue number search. Returns MBID or None."""
    try:
        query = f'catno:"{catno}"'
        if artist_hint:
            query += f' AND artist:"{artist_hint}"'
        data = _mb_get(
            "https://musicbrainz.org/ws/2/release",
            params={"query": query, "fmt": "json", "limit": 1},
        )
        releases = data.get("releases", [])
        if releases and releases[0].get("score", 0) > 75:
            return releases[0]["id"]
    except Exception as e:
        print(f"  [MB catno error] {e}")
    return None


# ── Verification chain ────────────────────────────────────────────────────────

class VerificationResult:
    def __init__(self, mbid: str, title: str, method: str,
                 catno: str = None, barcode: str = None):
        self.mbid    = mbid
        self.title   = title
        self.method  = method  # 'mb_barcode', 'mb_catno', 'discogs_catno'
        self.catno   = catno
        self.barcode = barcode

    def __str__(self):
        return f"{self.title} [{self.mbid}] via {self.method}"


def verify_barcode(barcode: str) -> VerificationResult:
    """
    Verify a physical release via barcode.
    Returns VerificationResult or raises ValueError if not verifiable.
    """
    print(f"Verifying barcode: {barcode}")

    # 1. Direct MusicBrainz barcode lookup
    mbid = mb_lookup_barcode(barcode)
    if mbid:
        detail = _mb_get(
            f"https://musicbrainz.org/ws/2/release/{mbid}",
            params={"fmt": "json"},
        )
        return VerificationResult(
            mbid    = mbid,
            title   = detail.get("title", "Unknown"),
            method  = "mb_barcode",
            barcode = barcode,
        )

    # 2. Discogs barcode → catalogue number → MusicBrainz
    print("  MusicBrainz barcode not found, trying Discogs…")
    discogs_results = discogs_lookup(barcode)

    for candidate in discogs_results:
        catno = candidate.get("catno")
        if not catno or catno.lower() == "none":
            continue

        # Extract artist hint from "Artist - Title" format
        title_parts = candidate["title"].split(" - ", 1)
        artist_hint = title_parts[0] if len(title_parts) == 2 else None

        mbid = mb_lookup_catno(catno, artist_hint)
        if mbid:
            detail = _mb_get(
                f"https://musicbrainz.org/ws/2/release/{mbid}",
                params={"fmt": "json"},
            )
            return VerificationResult(
                mbid    = mbid,
                title   = detail.get("title", candidate["title"]),
                method  = "discogs_catno",
                catno   = catno,
                barcode = barcode,
            )

    raise ValueError(
        f"Could not verify barcode {barcode} against MusicBrainz or Discogs. "
        "The release may not be in either database. "
        "You can add it at musicbrainz.org and retry."
    )


if __name__ == "__main__":
    import sys
    barcode = sys.argv[1] if len(sys.argv) > 1 else read_barcode_stdin()
    try:
        result = verify_barcode(barcode)
        print(f"\nVerified: {result}")
    except ValueError as e:
        print(f"\nFailed: {e}")
        sys.exit(1)
