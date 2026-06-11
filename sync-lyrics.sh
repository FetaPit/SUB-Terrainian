#!/data/data/com.termux/files/usr/bin/bash
#
# sync-lyrics.sh
# Pull synced LRC lyrics from LRCLIB for every audio file in a tree.
# Supports: mp3, flac, wav, m4a, aac, ogg, opus, wma, ape, alac
#
# Tier 1: LRCLIB exact match (artist + title + album + duration)
# Tier 2: LRCLIB fuzzy search (artist + title)
# Tier 3: Plain lyrics fallback saved as .txt if no synced version exists
#
# Usage:
#   ./sync-lyrics.sh                            # scans ~/storage/shared
#   ./sync-lyrics.sh /path/to/music             # scans custom path
#
# First time setup:
#   pkg install ffmpeg jq curl
#   termux-setup-storage
#   chmod +x sync-lyrics.sh
#
# LRCLIB: https://lrclib.net (open source, no API key, community contributed)

MUSIC_DIR="${1:-$HOME/storage/shared}"
API_BASE="https://lrclib.net/api"
USER_AGENT="SubTerrainian/0.1 ( contact@ptliveddesign.example )"
SLEEP_SECS="0.4"

EXTS=("mp3" "flac" "wav" "m4a" "aac" "ogg" "opus" "wma" "ape" "alac")

# Dependency check
for cmd in ffprobe curl jq; do
  if ! command -v "$cmd" &> /dev/null; then
    echo "Missing: $cmd"
    echo "Install with: pkg install ffmpeg jq curl"
    exit 1
  fi
done

if [ ! -d "$MUSIC_DIR" ]; then
  echo "Directory not found: $MUSIC_DIR"
  echo "If using shared storage, run: termux-setup-storage"
  exit 1
fi

urlencode() {
  jq -rn --arg v "$1" '$v|@uri'
}

# Build find expression for all extensions
find_args=()
for i in "${!EXTS[@]}"; do
  if [ $i -eq 0 ]; then
    find_args+=("-iname" "*.${EXTS[i]}")
  else
    find_args+=("-o" "-iname" "*.${EXTS[i]}")
  fi
done

# Counters
total=0
synced_exact=0
synced_fuzzy=0
plain_only=0
misses=0
skipped=0
no_tags=0

echo "Scanning: $MUSIC_DIR"
echo "Formats: ${EXTS[*]}"
echo

while IFS= read -r -d '' audio; do
  total=$((total + 1))
  base="${audio%.*}"
  lrc="${base}.lrc"
  txt="${base}.txt"

  # Skip if either output already exists
  if [ -f "$lrc" ] || [ -f "$txt" ]; then
    skipped=$((skipped + 1))
    continue
  fi

  # Extract metadata via ffprobe (works across all supported formats)
  meta=$(ffprobe -v quiet -print_format json -show_format "$audio" 2>/dev/null)
  artist=$(echo "$meta" | jq -r '.format.tags.artist // .format.tags.ARTIST // .format.tags.album_artist // .format.tags.ALBUM_ARTIST // empty' 2>/dev/null)
  title=$(echo "$meta" | jq -r '.format.tags.title // .format.tags.TITLE // empty' 2>/dev/null)
  album=$(echo "$meta" | jq -r '.format.tags.album // .format.tags.ALBUM // empty' 2>/dev/null)
  duration=$(echo "$meta" | jq -r '.format.duration // empty' 2>/dev/null | cut -d. -f1)

  if [ -z "$artist" ] || [ -z "$title" ]; then
    echo "[skip] no tags: $(basename "$audio")"
    no_tags=$((no_tags + 1))
    continue
  fi

  echo "[try] $artist - $title"

  # Tier 1: Exact match
  url="$API_BASE/get?artist_name=$(urlencode "$artist")&track_name=$(urlencode "$title")"
  [ -n "$album" ] && url+="&album_name=$(urlencode "$album")"
  [ -n "$duration" ] && url+="&duration=$duration"

  response=$(curl -s -A "$USER_AGENT" "$url" || echo "{}")
  synced=$(echo "$response" | jq -r '.syncedLyrics // empty' 2>/dev/null)

  if [ -n "$synced" ] && [ "$synced" != "null" ]; then
    printf '%s\n' "$synced" > "$lrc"
    echo "  ok synced (exact)"
    synced_exact=$((synced_exact + 1))
    sleep "$SLEEP_SECS"
    continue
  fi

  # Tier 2: Fuzzy search
  search_url="$API_BASE/search?artist_name=$(urlencode "$artist")&track_name=$(urlencode "$title")"
  results=$(curl -s -A "$USER_AGENT" "$search_url" || echo "[]")
  synced=$(echo "$results" | jq -r '[.[] | select(.syncedLyrics != null)] | .[0].syncedLyrics // empty' 2>/dev/null)

  if [ -n "$synced" ] && [ "$synced" != "null" ]; then
    printf '%s\n' "$synced" > "$lrc"
    echo "  ok synced (fuzzy)"
    synced_fuzzy=$((synced_fuzzy + 1))
    sleep "$SLEEP_SECS"
    continue
  fi

  # Tier 3: Plain lyrics fallback
  plain=$(echo "$response" | jq -r '.plainLyrics // empty' 2>/dev/null)
  if [ -z "$plain" ] || [ "$plain" = "null" ]; then
    plain=$(echo "$results" | jq -r '[.[] | select(.plainLyrics != null)] | .[0].plainLyrics // empty' 2>/dev/null)
  fi

  if [ -n "$plain" ] && [ "$plain" != "null" ]; then
    printf '%s\n' "$plain" > "$txt"
    echo "  ~ plain only"
    plain_only=$((plain_only + 1))
  else
    echo "  miss"
    misses=$((misses + 1))
  fi

  sleep "$SLEEP_SECS"

done < <(find "$MUSIC_DIR" -type f \( "${find_args[@]}" \) -print0)

echo
echo "Done."
echo "  Total files:    $total"
echo "  Already had:    $skipped"
echo "  Synced exact:   $synced_exact"
echo "  Synced fuzzy:   $synced_fuzzy"
echo "  Plain only:     $plain_only"
echo "  No tags:        $no_tags"
echo "  No lyrics:      $misses"
