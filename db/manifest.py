#!/usr/bin/env python3
"""
db/manifest.py  —  SUB-Terrainian

SQLite manifest: schema creation, migrations, and shared helpers.
Every phase reads/writes through here. Open once, pass the connection around.
"""

import sqlite3
import time
from pathlib import Path

DEFAULT_PATH = "sub_terrainian.db"


# ── Schema ─────────────────────────────────────────────────────────────────────

_SCHEMA = """
CREATE TABLE IF NOT EXISTS artist (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    mbid                TEXT UNIQUE,
    name                TEXT NOT NULL,
    sort_name           TEXT,
    portrait_source     TEXT,
    portrait_url        TEXT,
    portrait_path       TEXT,
    portrait_phash      TEXT,
    portrait_fetched_at TEXT
);

CREATE TABLE IF NOT EXISTS release (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    mbid                TEXT UNIQUE NOT NULL,
    artist_id           INTEGER REFERENCES artist(id),
    title               TEXT NOT NULL,
    date                TEXT,
    year                INTEGER,
    label               TEXT,
    catalog_number      TEXT,
    country             TEXT,
    track_count         INTEGER,
    folder_path         TEXT,
    artwork_source      TEXT,
    artwork_path        TEXT,
    artwork_fetched_at  TEXT,
    ipfs_artwork_cid    TEXT,
    ipfs_preview_cid    TEXT,
    nft_token_id        TEXT,
    nft_minted_at       TEXT,
    resolved_at         TEXT
);

CREATE TABLE IF NOT EXISTS track (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    release_id          INTEGER NOT NULL REFERENCES release(id),
    mbid                TEXT UNIQUE,
    title               TEXT NOT NULL,
    artist_credit       TEXT,
    disc_number         INTEGER DEFAULT 1,
    track_number        INTEGER NOT NULL,
    duration_ms         INTEGER,
    isrc                TEXT,
    file_path           TEXT,
    lyrics_source       TEXT,
    lyrics_plain        TEXT,
    lyrics_synced       TEXT,
    lyrics_fetched_at   TEXT,
    lyrics_lrclib_id    INTEGER
);

CREATE INDEX IF NOT EXISTS idx_release_mbid   ON release(mbid);
CREATE INDEX IF NOT EXISTS idx_artist_mbid    ON artist(mbid);
CREATE INDEX IF NOT EXISTS idx_track_release  ON track(release_id);
CREATE INDEX IF NOT EXISTS idx_track_mbid     ON track(mbid);
"""


def open_db(path: str = DEFAULT_PATH) -> sqlite3.Connection:
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA foreign_keys=ON")
    con.executescript(_SCHEMA)
    con.commit()
    return con


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


# ── Artist helpers ─────────────────────────────────────────────────────────────

def upsert_artist(con: sqlite3.Connection, mbid: str, name: str, sort_name: str = None) -> int:
    cur = con.execute(
        """
        INSERT INTO artist (mbid, name, sort_name)
        VALUES (?, ?, ?)
        ON CONFLICT(mbid) DO UPDATE SET
            name      = excluded.name,
            sort_name = excluded.sort_name
        RETURNING id
        """,
        (mbid, name, sort_name),
    )
    row = cur.fetchone()
    con.commit()
    return row["id"]


def get_artist_by_mbid(con: sqlite3.Connection, mbid: str) -> sqlite3.Row | None:
    return con.execute("SELECT * FROM artist WHERE mbid = ?", (mbid,)).fetchone()


def update_portrait(con: sqlite3.Connection, artist_id: int, **kwargs):
    allowed = {"portrait_source", "portrait_url", "portrait_path",
                "portrait_phash", "portrait_fetched_at"}
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    if not fields:
        return
    sets = ", ".join(f"{k} = ?" for k in fields)
    con.execute(f"UPDATE artist SET {sets} WHERE id = ?", [*fields.values(), artist_id])
    con.commit()


# ── Release helpers ────────────────────────────────────────────────────────────

def upsert_release(con: sqlite3.Connection, mbid: str, title: str,
                   artist_id: int = None, **kwargs) -> int:
    allowed = {"date", "year", "label", "catalog_number", "country",
               "track_count", "folder_path", "resolved_at"}
    extra = {k: v for k, v in kwargs.items() if k in allowed}
    extra.setdefault("resolved_at", now_iso())

    cols = ["mbid", "title", "artist_id"] + list(extra.keys())
    vals = [mbid, title, artist_id] + list(extra.values())
    placeholders = ", ".join("?" * len(vals))
    updates = ", ".join(
        f"{c} = excluded.{c}"
        for c in cols if c != "mbid"
    )

    cur = con.execute(
        f"""
        INSERT INTO release ({', '.join(cols)})
        VALUES ({placeholders})
        ON CONFLICT(mbid) DO UPDATE SET {updates}
        RETURNING id
        """,
        vals,
    )
    row = cur.fetchone()
    con.commit()
    return row["id"]


def get_release_by_mbid(con: sqlite3.Connection, mbid: str) -> sqlite3.Row | None:
    return con.execute("SELECT * FROM release WHERE mbid = ?", (mbid,)).fetchone()


def update_artwork(con: sqlite3.Connection, release_id: int, **kwargs):
    allowed = {"artwork_source", "artwork_path", "artwork_fetched_at",
               "ipfs_artwork_cid", "nft_token_id", "nft_minted_at"}
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    if not fields:
        return
    sets = ", ".join(f"{k} = ?" for k in fields)
    con.execute(f"UPDATE release SET {sets} WHERE id = ?", [*fields.values(), release_id])
    con.commit()


def all_releases_needing_artwork(con: sqlite3.Connection) -> list[sqlite3.Row]:
    return con.execute(
        "SELECT * FROM release WHERE artwork_fetched_at IS NULL"
    ).fetchall()


def all_releases_needing_nft(con: sqlite3.Connection) -> list[sqlite3.Row]:
    return con.execute(
        "SELECT * FROM release WHERE mbid IS NOT NULL AND nft_token_id IS NULL"
    ).fetchall()


# ── Track helpers ──────────────────────────────────────────────────────────────

def upsert_track(con: sqlite3.Connection, release_id: int, title: str,
                 track_number: int, **kwargs) -> int:
    allowed = {"mbid", "artist_credit", "disc_number", "duration_ms",
               "isrc", "file_path"}
    extra = {k: v for k, v in kwargs.items() if k in allowed}
    extra.setdefault("disc_number", 1)

    mbid = extra.pop("mbid", None)
    cols = ["release_id", "title", "track_number"] + list(extra.keys())
    vals = [release_id, title, track_number] + list(extra.values())

    if mbid:
        cols.insert(0, "mbid")
        vals.insert(0, mbid)

    placeholders = ", ".join("?" * len(vals))
    updates = ", ".join(
        f"{c} = excluded.{c}"
        for c in cols if c not in ("mbid", "release_id")
    )

    conflict_col = "mbid" if mbid else "rowid"
    cur = con.execute(
        f"""
        INSERT INTO track ({', '.join(cols)})
        VALUES ({placeholders})
        ON CONFLICT({'mbid' if mbid else 'id'}) DO UPDATE SET {updates}
        RETURNING id
        """,
        vals,
    )
    row = cur.fetchone()
    con.commit()
    return row["id"]


def update_lyrics(con: sqlite3.Connection, track_id: int, **kwargs):
    allowed = {"lyrics_source", "lyrics_plain", "lyrics_synced",
               "lyrics_fetched_at", "lyrics_lrclib_id"}
    fields = {k: v for k, v in kwargs.items() if k in allowed}
    if not fields:
        return
    sets = ", ".join(f"{k} = ?" for k in fields)
    con.execute(f"UPDATE track SET {sets} WHERE id = ?", [*fields.values(), track_id])
    con.commit()


def all_tracks_needing_lyrics(con: sqlite3.Connection) -> list[sqlite3.Row]:
    return con.execute(
        "SELECT * FROM track WHERE lyrics_fetched_at IS NULL AND file_path IS NOT NULL"
    ).fetchall()


def tracks_for_release(con: sqlite3.Connection, release_id: int) -> list[sqlite3.Row]:
    return con.execute(
        "SELECT * FROM track WHERE release_id = ? ORDER BY disc_number, track_number",
        (release_id,),
    ).fetchall()
