#!/usr/bin/env python3
"""
manifest_bridge.py  —  SUB-Terrainian Sprint 1

Reads the SQLite manifest and produces EIP-1155 metadata JSON per release,
ready for IPFS pinning. Output lands in web3/metadata/<tokenId>.json.

Usage:
    python web3/manifest_bridge.py --mbid <uuid>        # single release
    python web3/manifest_bridge.py --all                # full manifest

Environment (.env):
    MANIFEST_PATH        path to SQLite manifest  (default: sub_terrainian.db)
    PINATA_JWT           Pinata JWT for IPFS pinning (optional — skip for local only)
    MUSIC_EDITION_ADDRESS deployed MusicEdition contract address (post-deploy)
"""

import argparse
import hashlib
import json
import os
import sqlite3
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

MANIFEST_PATH = os.getenv("MANIFEST_PATH", "sub_terrainian.db")
OUTPUT_DIR    = Path("web3/metadata")
USER_AGENT    = "SubTerrainian/0.1 ( contact@ptliveddesign.example )"


# ── Token ID derivation ────────────────────────────────────────────────────────

def mbid_to_token_id(mbid: str) -> int:
    """
    Deterministic uint256 token ID from a MusicBrainz UUID string.
    Matches the Solidity usage: pass the same mbid string both sides.
    The bytes32 on-chain is keccak256(abi.encodePacked(mbid)) — use
    mbid_to_bytes32() for the contract call.
    """
    return int(hashlib.sha256(mbid.encode()).hexdigest(), 16) % (2 ** 256)


def mbid_to_bytes32(mbid: str) -> str:
    """Hex bytes32 for Solidity contract calls (0x-prefixed, 64 hex chars)."""
    digest = hashlib.sha256(mbid.encode()).hexdigest()
    return "0x" + digest[:64]


# ── Manifest read ──────────────────────────────────────────────────────────────

def _open(db_path: str) -> sqlite3.Connection:
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    return con


def fetch_release(mbid: str, db_path: str = MANIFEST_PATH) -> dict:
    """Return release + artist data for a single MBID."""
    con = _open(db_path)
    cur = con.cursor()

    release = cur.execute(
        "SELECT * FROM release WHERE mbid = ?", (mbid,)
    ).fetchone()

    if release is None:
        raise ValueError(f"MBID not found in manifest: {mbid}")

    artist = cur.execute(
        "SELECT * FROM artist WHERE id = ?", (release["artist_id"],)
    ).fetchone() if release["artist_id"] else None

    tracks = cur.execute(
        "SELECT * FROM track WHERE release_id = ? ORDER BY disc_number, track_number",
        (release["id"],)
    ).fetchall()

    con.close()
    return {
        "release": dict(release),
        "artist":  dict(artist) if artist else {},
        "tracks":  [dict(t) for t in tracks],
    }


def fetch_all_mbids(db_path: str = MANIFEST_PATH) -> list[str]:
    con = _open(db_path)
    rows = con.execute("SELECT mbid FROM release WHERE mbid IS NOT NULL").fetchall()
    con.close()
    return [r["mbid"] for r in rows]


# ── Metadata construction ──────────────────────────────────────────────────────

def build_metadata(mbid: str, db_path: str = MANIFEST_PATH) -> dict:
    """
    Build EIP-1155 metadata JSON for a release.
    artwork_cid and animation_cid are placeholders until Phase 2 IPFS pins exist.
    """
    data     = fetch_release(mbid, db_path)
    release  = data["release"]
    artist   = data["artist"]
    tracks   = data["tracks"]

    artist_name  = artist.get("name", "Unknown Artist")
    album_title  = release.get("title", "Unknown Album")
    year         = release.get("year") or release.get("date", "")[:4] if release.get("date") else ""
    label        = release.get("label", "")
    track_count  = len(tracks)
    token_id     = mbid_to_token_id(mbid)

    attributes = [
        {"trait_type": "MBID",        "value": mbid},
        {"trait_type": "Artist",      "value": artist_name},
        {"trait_type": "Album",       "value": album_title},
        {"trait_type": "Tracks",      "value": track_count},
        {"trait_type": "Provenance",  "value": "MusicBrainz-verified"},
    ]

    if year:
        attributes.append({"trait_type": "Year",  "value": year})
    if label:
        attributes.append({"trait_type": "Label", "value": label})
    if artist.get("mbid"):
        attributes.append({"trait_type": "Artist MBID", "value": artist["mbid"]})

    artwork_cid   = release.get("ipfs_artwork_cid", "PENDING")
    animation_cid = release.get("ipfs_preview_cid", None)

    metadata = {
        "name":         f"{artist_name} — {album_title}",
        "description":  (
            f"Verified music release. {track_count} tracks. "
            f"Provenance: MusicBrainz MBID {mbid}."
        ),
        "image":        f"ipfs://{artwork_cid}" if artwork_cid != "PENDING" else "",
        "external_url": f"https://musicbrainz.org/release/{mbid}",
        "attributes":   attributes,
    }

    if animation_cid:
        metadata["animation_url"] = f"ipfs://{animation_cid}"

    return metadata


# ── Output ─────────────────────────────────────────────────────────────────────

def write_metadata(mbid: str, db_path: str = MANIFEST_PATH) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    metadata = build_metadata(mbid, db_path)
    token_id = mbid_to_token_id(mbid)
    out_path = OUTPUT_DIR / f"{token_id}.json"
    out_path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False))
    return out_path


def pin_to_ipfs(file_path: Path) -> str | None:
    """
    Pin a metadata JSON to IPFS via Pinata.
    Returns the IPFS CID string, or None if PINATA_JWT is not set.
    Requires: pip install requests
    """
    jwt = os.getenv("PINATA_JWT")
    if not jwt:
        return None

    import requests  # only imported when actually pinning

    with file_path.open("rb") as f:
        response = requests.post(
            "https://api.pinata.cloud/pinning/pinFileToIPFS",
            headers={"Authorization": f"Bearer {jwt}"},
            files={"file": (file_path.name, f, "application/json")},
            headers_override={"User-Agent": USER_AGENT},
            timeout=30,
        )
    response.raise_for_status()
    return response.json()["IpfsHash"]


# ── CLI ────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="SUB-Terrainian manifest → IPFS metadata bridge")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--mbid", help="Single MusicBrainz release UUID")
    group.add_argument("--all",  action="store_true", help="Process entire manifest")
    parser.add_argument("--pin", action="store_true", help="Pin to IPFS via Pinata (requires PINATA_JWT)")
    parser.add_argument("--db",  default=MANIFEST_PATH, help="Path to SQLite manifest")
    args = parser.parse_args()

    mbids = [args.mbid] if args.mbid else fetch_all_mbids(args.db)

    for mbid in mbids:
        try:
            path = write_metadata(mbid, args.db)
            token_id = mbid_to_token_id(mbid)
            cid = pin_to_ipfs(path) if args.pin else None
            status = f"pinned → ipfs://{cid}" if cid else "written (not pinned)"
            print(f"{mbid}  token={token_id}  {status}  → {path}")
        except ValueError as e:
            print(f"SKIP  {mbid}  {e}")
        except Exception as e:
            print(f"ERROR {mbid}  {e}")


if __name__ == "__main__":
    main()
