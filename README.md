# SUB-Terrainian

A personal discography builder with a planned industry-tool layer. Resolves album artwork, artist portraits, lyrics, and metadata through verified provenance chains — MusicBrainz, Wikidata, Cover Art Archive, LRCLIB — and anchors verified releases on Base as limited-edition NFTs.

**Status:** v0.1 alpha — pipeline + web3 foundation in development. Single-user, Termux-on-Android target.

**Author:** Pete Thickett — PT Lived Design, Lincoln UK.

---

## What it does

### Phase pipeline (Python)

Four phases writing idempotently into a shared SQLite manifest:

| Phase | Function | Sources |
|---|---|---|
| 1 | Metadata | MusicBrainz MBID anchor + album metadata |
| 2 | Artwork | MusicBrainz/CAA → iTunes → Deezer; embeds tags, writes `folder.jpg` |
| 3 | Artist portraits | MusicBrainz → Wikidata `P18` → Wikimedia Commons; fallback TheAudioDB |
| 4 | Lyrics | LRCLIB exact → fuzzy → plain-text; saved as `.lrc` sidecars |

Each phase is independently rerunnable. Outputs are filesystem-native — designed to drop straight into Musicolet (Krosbits) with no app integration required.

### Web3 layer (Base — v0.2)

On-chain ownership infrastructure built on Base (Coinbase L2):

- **MusicEdition** (`contracts/MusicEdition.sol`) — ERC-1155 limited-edition NFTs. One token type per MusicBrainz release. Edition size fixed at creation. EIP-2981 royalties on every secondary sale.
- **PhysicalClaim** (`contracts/PhysicalClaim.sol`) — EIP-5192 soulbound proof-of-physical-ownership. Issued when a physical release (vinyl, CD) is verified via barcode → Discogs → MusicBrainz chain. Non-transferable.
- **manifest_bridge.py** — reads the SQLite manifest and produces EIP-1155 metadata JSON per MBID, ready for IPFS pinning.
- **ownership.py** — read-only wallet ownership checks via JSON-RPC; no private key on device required.

Token ID derivation: `sha256(mbid) mod 2^256` — deterministic, reproducible off-chain.

---

## Scripts

| File | Phase | Status |
|---|---|---|
| `fetch_v3.py` | Artwork | Working on device — needs recovering to repo |
| `sync-lyrics.sh` | Lyrics | Working — LRCLIB three-tier fetch |
| `contracts/MusicEdition.sol` | Web3 | Written — deploy to Base Sepolia |
| `contracts/PhysicalClaim.sol` | Web3 | Written — deploy to Base Sepolia |
| `web3/manifest_bridge.py` | Web3 | Written — runs against live manifest |
| `web3/ownership.py` | Web3 | Sprint 3 stub — ready post-deploy |
| _Phase 1 + 3_ | Metadata, portraits | Scoped, not yet built |

`_archive/` holds superseded scripts kept for reference only. Do not import from there.

---

## Setup

### Phase pipeline (Termux)

See `HANDOVER_termux_to_claude_code.md` for the full Termux environment record.

```bash
pkg install python flac jq curl
chmod +x sync-lyrics.sh
./sync-lyrics.sh /path/to/music
```

### Web3 / Foundry (any EVM dev machine)

```bash
# Install Foundry
curl -L https://foundry.paradigm.xyz | bash
foundryup

# Install OpenZeppelin and forge-std
forge install OpenZeppelin/openzeppelin-contracts
forge install foundry-rs/forge-std

# Run tests
forge test -vv

# Deploy to Base Sepolia
cp .env.example .env   # fill in keys
forge script contracts/script/Deploy.s.sol \
  --rpc-url base_sepolia \
  --broadcast \
  --verify \
  --etherscan-api-key $BASESCAN_API_KEY
```

### Environment variables (`.env`)

```
MANIFEST_PATH=sub_terrainian.db
PINATA_JWT=<your Pinata JWT>
BASESCAN_API_KEY=<your Basescan key>
DEPLOYER_ADDRESS=<your wallet address>
BASE_RPC_URL=https://mainnet.base.org
MUSIC_EDITION_ADDRESS=<deployed contract>
PHYSICAL_CLAIM_ADDRESS=<deployed contract>
THEAUDIODB_KEY=<registered key>
```

---

## Hard rules

See `CLAUDE.md` for the engineering and naming constraints any contributor (human or agent) must follow. Key points:

- Do **not** install `imagehash`, `PyWavelets`, or `scipy` — compile chain fails on aarch64 Termux.
- Always write the full name "SUB-Terrainian".
- Attribution: PT Lived Design.
- Deprecated branding never to be used: "Fyrra Studio", "Bauhaus Twenty One".
