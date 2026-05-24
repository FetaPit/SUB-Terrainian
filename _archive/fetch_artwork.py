#!/usr/bin/env python3
"""
Album Artwork Fetcher for Musicolet
Uses MusicBrainz + Cover Art Archive API
Saves folder.jpg to each album folder + central copy to Music/Album Artwork/
"""

import os
import time
import requests
from mutagen import File
from pathlib import Path

MUSIC_ROOT = "/sdcard/Music"
ARTWORK_DIR = "/sdcard/Music/Album Artwork"
HEADERS = {"User-Agent": "FyrraStudioArtworkFetcher/1.0 contact@fyrrastudio.com"}
LOG = []

def get_audio_files(folder):
    exts = (".mp3", ".flac", ".m4a", ".ogg", ".opus", ".wav", ".aac")
    return [f for f in os.listdir(folder) if f.lower().endswith(exts)]

def has_artwork(folder):
    for name in ("folder.jpg", "cover.jpg", "album.jpg", "front.jpg"):
        if os.path.exists(os.path.join(folder, name)):
            return True
    return False

def get_tags(folder, audio_files):
    artist, album, mbid = None, None, None
    for f in audio_files:
        try:
            audio = File(os.path.join(folder, f))
            if not audio or not audio.tags:
                continue
            tags = audio.tags
            for key in tags.keys():
                kl = key.lower()
                if not artist and ("tpe1" in kl or kl == "artist" or "\xa9art" in kl):
                    val = tags[key]
                    artist = str(val[0] if isinstance(val, list) else val)
                if not album and ("talb" in kl or kl == "album" or "\xa9alb" in kl):
                    val = tags[key]
                    album = str(val[0] if isinstance(val, list) else val)
                if not mbid and "musicbrainz" in kl and "release" in kl:
                    val = tags[key]
                    mbid = str(val[0] if isinstance(val, list) else val)
            if artist and album:
                break
        except Exception:
            continue
    return artist, album, mbid

def search_mb(artist, album):
    try:
        r = requests.get(
            "https://musicbrainz.org/ws/2/release",
            params={"query": f'artist:"{artist}" AND release:"{album}"', "fmt": "json", "limit": 1},
            headers=HEADERS, timeout=15
        )
        releases = r.json().get("releases", [])
        if releases:
            return releases[0]["id"]
    except Exception:
        pass
    return None

def fetch_art(mbid):
    for size in ["1200", "500", ""]:
        suffix = f"-{size}" if size else ""
        try:
            r = requests.get(
                f"https://coverartarchive.org/release/{mbid}/front{suffix}",
                headers=HEADERS, timeout=20, allow_redirects=True
            )
            ct = r.headers.get("content-type", "")
            if r.status_code == 200 and "image" in ct:
                return r.content
        except Exception:
            pass
    return None

def save(data, path):
    with open(path, "wb") as f:
        f.write(data)

def safe_name(s):
    for ch in r'/\:*?"<>|':
        s = s.replace(ch, "-")
    return s.strip()

def main():
    os.makedirs(ARTWORK_DIR, exist_ok=True)
    found = skipped = missing = no_art = 0

    print("Scanning Music folder...\n")

    for root, dirs, files in os.walk(MUSIC_ROOT):
        dirs[:] = [d for d in dirs if os.path.join(root, d) != ARTWORK_DIR]
        if root == ARTWORK_DIR:
            continue

        audio_files = get_audio_files(root)
        if not audio_files:
            continue

        if has_artwork(root):
            skipped += 1
            continue

        artist, album, mbid = get_tags(root, audio_files)

        if not artist or not album:
            msg = f"NO TAGS: {root}"
            LOG.append(msg)
            print(f"  Skipping (no tags): {os.path.basename(root)}")
            missing += 1
            continue

        print(f"Fetching: {artist} - {album}")

        if not mbid:
            mbid = search_mb(artist, album)
            time.sleep(1.1)  # MusicBrainz rate limit: max 1 req/sec

        if not mbid:
            msg = f"NOT FOUND in MusicBrainz: {artist} - {album}"
            LOG.append(msg)
            print(f"  Not found")
            missing += 1
            continue

        art = fetch_art(mbid)
        if not art:
            msg = f"NO ARTWORK in Cover Art Archive: {artist} - {album}"
            LOG.append(msg)
            print(f"  No artwork available")
            no_art += 1
            continue

        # Save to album folder (Musicolet reads folder.jpg natively)
        save(art, os.path.join(root, "folder.jpg"))

        # Save central copy
        central_name = safe_name(f"{artist} - {album}") + ".jpg"
        save(art, os.path.join(ARTWORK_DIR, central_name))

        print(f"  Saved OK")
        LOG.append(f"OK: {artist} - {album}")
        found += 1

    # Write log
    log_path = os.path.join(ARTWORK_DIR, "artwork_log.txt")
    with open(log_path, "w") as f:
        f.write(f"Run complete\n")
        f.write(f"Artwork saved:    {found}\n")
        f.write(f"Already had art:  {skipped}\n")
        f.write(f"Not found:        {missing}\n")
        f.write(f"No art available: {no_art}\n\n")
        f.write("\n".join(LOG))

    print(f"\n--- Done ---")
    print(f"Saved:           {found}")
    print(f"Already had art: {skipped}")
    print(f"Not found:       {missing}")
    print(f"No art in CAA:   {no_art}")
    print(f"Log: {log_path}")

if __name__ == "__main__":
    main()


