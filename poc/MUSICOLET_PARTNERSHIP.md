# SUB-Terrainian × Musicolet — Partnership Outreach

**For:** Maulik Raviya, Krosbits  
**From:** Pete Thickett, PT Lived Design (Lincoln, UK)  
**Project:** SUB-Terrainian v0.1

---

## What We Built

SUB-Terrainian is a personal discography builder for Android. It runs entirely on-device (Termux + Python) and enriches a local music library with:

- **Verified album artwork** — sourced from MusicBrainz Cover Art Archive → iTunes → Deezer, written as `folder.jpg` into every album folder
- **Synced lyrics (.lrc sidecars)** — sourced from LRCLIB (community-maintained, free, no key), written as `.lrc` files next to each audio track
- **Artist portraits** — sourced from Wikidata (P18) → Wikimedia Commons → TheAudioDB fallback
- **MusicBrainz-anchored manifest** — every release and track tied to a verified MBID, stored in a local SQLite database

Every asset is written using Musicolet's native formats. No patching required. No API access required. It just works.

---

## Why Musicolet?

Musicolet is the only local Android player that handles both `folder.jpg` artwork and `.lrc` synced lyrics natively and reliably. That combination is rare. It made Musicolet the natural target platform for this entire build.

We designed the output format around what Musicolet already does well — not the other way around.

---

## Proof-of-Concept Evidence

Running `python poc/demo.py` on a sample of albums produces a live coverage report:

```
  ┌─ Enrichment coverage ─────────────────────┐
  │ Artwork          : ███ / ███  (  ~%)       │
  │ Synced lyrics    : ████ / ████ tracks (~%) │
  │ Any lyrics       : ████ / ████ tracks (~%) │
  │ Artist portraits : ███ / ███  (  ~%)       │
  └───────────────────────────────────────────┘
```

After the pipeline runs, Musicolet picks up all artwork and lyrics on the next library scan — no manual steps.

To generate a live report against your own library:

```bash
git clone https://github.com/FetaPit/SUB-Terrainian
cd SUB-Terrainian
pip install -r requirements.txt
python poc/demo.py --sample 20
```

---

## The Partnership Proposition

### Phase 1 — What exists today (no integration needed)

SUB-Terrainian already writes the files Musicolet reads. Users who run the tool immediately get enriched artwork and lyrics in Musicolet. This works today, with no changes on Krosbits' side.

### Phase 2 — Featured tool or in-app recommendation

Musicolet could mention SUB-Terrainian as a recommended enrichment tool for users who want to fill gaps in their library metadata. A single line in the FAQ, a help article, or a community post would surface it to your users who are already frustrated by missing artwork and lyrics.

### Phase 3 — Deeper integration (to discuss)

If Krosbits is open to it, tighter integration could include:

1. **Trigger enrichment from within Musicolet** — a "Fetch missing metadata" option that hands off to SUB-Terrainian (Android Intent)
2. **Real-time progress** — SUB-Terrainian exposes a local HTTP API; Musicolet could poll/stream status
3. **MBID sharing** — if Musicolet surfaces the MusicBrainz ID it already resolves internally, SUB-Terrainian can skip its Phase 1 scan and run ~3× faster
4. **Verified badge** — albums enriched via SUB-Terrainian carry a `sub_terrainian_verified` flag in their manifest; Musicolet could surface this as a quality indicator

None of phase 3 is required for the core value. It's a roadmap, not a demand.

---

## Web3 Layer (Context — Not the Ask)

SUB-Terrainian also issues on-chain ownership NFTs (Base, Coinbase L2) for verified releases:

- `MusicEdition` — ERC-1155 limited-edition digital ownership, with EIP-2981 royalties
- `PhysicalClaim` — EIP-5192 soulbound token, proving physical ownership of a release

This is a separate layer on top of the filesystem enrichment. It doesn't change how Musicolet works. It's context for where the project is heading — toward a verified discography that lives both locally and on-chain.

---

## What We're Asking For

1. **Five minutes of your time** — a read of this document and the repo
2. **A short reply** — even just "interesting, let's talk" or "not right now"
3. **If open to it** — a call or async exchange about whether a featured-tool relationship makes sense

There's no funding ask. No exclusivity request. No revenue share required at this stage. The goal is to make Musicolet users' libraries better — you already built the player that deserves it.

---

## Contact

**Pete Thickett**  
PT Lived Design, Lincoln, UK  
ptlived@gmail.com  
GitHub: [FetaPit/SUB-Terrainian](https://github.com/FetaPit/SUB-Terrainian)

---

## Technical Summary for Krosbits Devs

| Artifact | Format | Written by SUB-Terrainian | Musicolet reads natively |
|---|---|---|---|
| Album artwork | `folder.jpg` (600px JPEG) | ✓ | ✓ |
| Synced lyrics | `.lrc` sidecar (LRC v2) | ✓ | ✓ |
| Unsynchronised lyrics | `.txt` sidecar | ✓ | ✓ (plain text fallback) |
| Embedded artwork | ID3 APIC / FLAC PICTURE / MP4Cover | ✓ | ✓ |
| Artist portraits | `portraits/cache/<mbid>.jpg` | ✓ | — (dashboard only) |

Pipeline phases (each independently rerunnable, idempotent):

| Phase | Source | Rate limit |
|---|---|---|
| 1 — MBID resolve | MusicBrainz | 1 req/sec |
| 2 — Artwork | CAA → iTunes → Deezer | Polite |
| 3 — Portraits | Wikidata → Commons → TheAudioDB | 30 req/min |
| 4 — Lyrics | LRCLIB exact → fuzzy → plain | Polite |

All source code: MIT licence.  
Dependency surface: Python 3.10+, `requests`, `mutagen`, `Pillow`, `numpy`, `Flask`.  
Runs on Android (Termux), Linux, macOS. No compile chain. No native extensions.
