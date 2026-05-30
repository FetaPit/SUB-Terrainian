# SUB-Terrainian — Claude Code instructions

## Project

Personal discography builder with a planned industry-tool layer. Currently v0.1 alpha. Author: Pete Thickett, trading as PT Lived Design.

## Runtime

- Termux F-Droid build on Android aarch64. No glibc. No `/tmp` — use `$TMPDIR`.
- Python 3.13 via Termux `pkg`. Do **not** create a venv; Termux's system Python is the project Python.
- Claude Code pinned to `@anthropic-ai/claude-code@2.1.112` (the last JS-entry release). v2.1.113+ ships a glibc Linux binary that does not run on Termux/Bionic.
- Auto-updater is locked off via three layers (read-only install dir + env var + settings.json). Do not re-enable it.

## Hard rules

1. **Do NOT install** `imagehash`, `PyWavelets`, or `scipy`. The compile chain pulls in cmake, ninja, meson + numpy sdist rebuild, and Fortran-flavoured BLAS/LAPACK detection. On aarch64 phones it runs for over an hour before failing. Perceptual hashing is implemented in-tree in numpy + PIL.
2. **Always write the full project name** "SUB-Terrainian". Never abbreviate to "SUB" or "ST" in prose or documentation.
3. **Trading name** on any generated copyright header or attribution: "PT Lived Design".
4. **Deprecated branding — NEVER use:** "Fyrra Studio", "fyrrastudio.com", "Bauhaus Twenty One". All retired. `_archive/fetch_artwork.py` carries the old Fyrra Studio User-Agent — that file is reference only and confirms it is pre-canonical code.
5. **v0.1 unlock mechanism is filesystem-only** — write `folder.jpg` into verified album folders and `.lrc` sidecars next to each track. Musicolet (Krosbits / Maulik Raviya) picks both up natively. No Krosbits API integration in v0.1.
6. **User-Agent header required** on every outbound HTTP call. Format: `SubTerrainian/0.1 ( contact@ptliveddesign.example )`.
7. **Rate limits are non-negotiable** — MusicBrainz at 1 req/sec (declines 100% above), TheAudioDB free tier at 30 req/min, LRCLIB no published limit but stay polite. Single-threaded clients. Back off on 503.

## Stack on disk

- `fetch_v3.py` — working artwork resolver (MusicBrainz/CAA → iTunes → Deezer → embed via mutagen). Phase 2.
- `sync-lyrics.sh` — LRCLIB three-tier lyrics fetcher (exact → fuzzy → plain). Phase 4.
- `contracts/` — Solidity smart contracts for Base. MusicEdition (ERC-1155 + EIP-2981) and PhysicalClaim (EIP-5192 soulbound).
- `web3/` — Python bridge: manifest → IPFS metadata, ownership checks via JSON-RPC.
- `_archive/` — superseded scripts. Do not import.
- SQLite manifest — canonical store. Schema lives alongside the code that reads/writes each phase.

## v0.1 pipeline

| Phase | Function | Source chain |
|---|---|---|
| 1 | Metadata pull | MusicBrainz (MBID anchor) |
| 2 | Album artwork | MusicBrainz/CAA → iTunes → Deezer |
| 3 | Artist portrait | MusicBrainz → Wikidata `P18` → Commons; fallback TheAudioDB |
| 4 | Lyrics | LRCLIB exact → fuzzy → plain |

Phase 1 must resolve the MBID before 2/3/4 can run. Phase 3 runs once per artist. Phase 4 is per-track — expect ~10× the API volume of album-level passes.

## Web3 layer (v0.2)

Chain: **Base** (Coinbase L2, EVM, low gas, WalletConnect v2 native).

| Contract | Standard | Purpose |
|---|---|---|
| `MusicEdition` | ERC-1155 + EIP-2981 | Limited-edition digital ownership NFTs |
| `PhysicalClaim` | ERC-721 + EIP-5192 | Soulbound proof-of-physical-ownership |

- Token ID = `sha256(mbid) mod 2^256` — deterministic, matches `manifest_bridge.py`.
- `web3/manifest_bridge.py` reads SQLite manifest → produces EIP-1155 metadata JSON → pins to IPFS.
- `web3/ownership.py` — read-only balance checks; no private key required on device.
- Foundry toolchain: `forge install`, `forge test`, `forge script contracts/script/Deploy.s.sol`.

## Manifest schema additions

On `artist` table (all nullable):
- `portrait_source` (text — e.g. `wikidata`, `theaudiodb`)
- `portrait_url` (text — origin URL fetched from)
- `portrait_path` (text — local relative path)
- `portrait_phash` (text — in-tree pHash for dedupe / change detection)
- `portrait_fetched_at` (ISO timestamp)

On `track` table (all nullable):
- `lyrics_source` (text — `lrclib`, `genius`, `embedded`)
- `lyrics_plain` (text — UTF-8)
- `lyrics_synced` (text — LRC format or null)
- `lyrics_fetched_at` (ISO timestamp)
- `lyrics_lrclib_id` (integer — for re-fetch / dedupe)

On `release` table (all nullable, added for web3):
- `ipfs_artwork_cid` (text — IPFS CID of folder.jpg)
- `ipfs_preview_cid` (text — IPFS CID of audio preview)
- `nft_token_id` (text — uint256 as string)
- `nft_minted_at` (ISO timestamp)

## Sources explicitly NOT used

- **Last.fm artist images** — return placeholder white-star for all artists since 2019 per Last.fm API ToS change.
- **Spotify imagery** — OAuth + ToS restrictions on storage/redistribution.
- **Discogs** — auth-gated, not worth the credentials surface for v0.1.
- **Musixmatch** — commercial, strict redistribution ToS.
- **AZLyrics scraping** — no API, hostile to scrapers, brittle.
- **NetEase Cloud Music API** — uneven Western coverage, unofficial clients break on auth changes.

## House style

- One responsibility per script. Compose in a top-level `sub_terrainian.py` orchestrator.
- Lightweight libs only — `requests`, `mutagen` (pure-Python), `pytest`, `python-dotenv`, `Flask` if a local HTTP API becomes useful. Avoid anything with a compile chain.
- All phases write idempotently to the manifest. Each phase is independently rerunnable.
- Lyrics live in the manifest, not on disk. If `.lrc` sidecars are needed for Musicolet, emit them as a separate step — keep ingestion and emission decoupled.

## Open product decisions

See `HANDOVER_termux_to_claude_code.md` §8 for open questions Pete needs to decide before serious implementation work. Do not make these unilaterally:

1. Genius lyrics fallback — ship in v0.1 or hold to v0.2? (Recommendation: absent in v0.1)
2. TheAudioDB API key — register under PT Lived Design or use shared key `123`?
3. Perceptual hash choice — pHash canonical, dHash prefilter recommended
4. `folder.jpg` size — 600px JPEG or original CAA resolution?
5. Artist portrait crop — ship as-fetched in v0.1, face-crop pass in v0.2?
6. Web3 edition size philosophy — fixed at mint time or curator-set per release?
7. Revenue split — primary sale and EIP-2981 secondary royalty percentages?

Flag these in-session and wait.

## First action when this project opens in Claude Code

Read `CLAUDE.md` (this file), `HANDOVER_termux_to_claude_code.md`, then `fetch_v3.py`. **Without writing any new code yet**, produce:

1. A one-page summary of what `fetch_v3.py` currently does and the exact SQLite schema it expects/creates.
2. A proposed schema delta for the new `artist.portrait_*` and `track.lyrics_*` columns described above.
3. A proposed directory layout grouping by phase (`metadata/`, `artwork/`, `portraits/`, `lyrics/`) with a top-level `sub_terrainian.py` orchestrator.

Stop there. Wait for approval before writing code or migrations.
