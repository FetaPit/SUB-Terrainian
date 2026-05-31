# Deploying contracts from Android (no laptop needed)

Use Remix IDE — it runs entirely in your Android browser.

## Step 1 — Open Remix

Open **Chrome or MetaMask Mobile browser** on your phone and go to:

```
https://remix.ethereum.org
```

## Step 2 — Load the contracts

In the Remix file explorer (left panel):

1. Create `contracts/MusicEdition.sol` — paste the full contents of this repo's file
2. Create `contracts/PhysicalClaim.sol` — paste the full contents of this repo's file

Or use the GitHub import:
- Click the GitHub icon in the file explorer
- Enter: `FetaPit/SUB-Terrainian`
- Remix will import the contracts directly

## Step 3 — Install OpenZeppelin

In the Remix terminal (bottom panel):

```
npm install @openzeppelin/contracts
```

Or use Remix's built-in package manager: click the npm icon and search `@openzeppelin/contracts`.

## Step 4 — Compile

- Click **Solidity Compiler** (left panel, shield icon)
- Select compiler version: `0.8.24`
- Enable optimisation: `200` runs
- Click **Compile MusicEdition.sol**
- Compile **PhysicalClaim.sol**

No errors = ready to deploy.

## Step 5 — Connect MetaMask to Base Sepolia (testnet first)

In MetaMask Mobile:
1. Open the browser menu → Networks → Add network
2. Add Base Sepolia:
   - Network name: `Base Sepolia`
   - RPC URL: `https://sepolia.base.org`
   - Chain ID: `84532`
   - Currency: `ETH`
   - Explorer: `https://sepolia.basescan.org`
3. Get free testnet ETH from `faucet.quicknode.com/base/sepolia`

## Step 6 — Deploy

In Remix → **Deploy & Run Transactions** (left panel, Ethereum icon):

- Environment: **Injected Provider — MetaMask**
- Make sure MetaMask is on **Base Sepolia**
- Contract: select `MusicEdition`
- Constructor arg `initialOwner`: paste your wallet address
- Click **Deploy** → confirm in MetaMask

Repeat for `PhysicalClaim`.

## Step 7 — Copy addresses to .env

After deployment, Remix shows the contract address in the left panel.

Copy both addresses into your `.env`:

```
MUSIC_EDITION_ADDRESS=0x...
PHYSICAL_CLAIM_ADDRESS=0x...
```

## Step 8 — Verify on Basescan (optional but recommended)

In Remix → Solidity Compiler → copy the ABI.
Go to `sepolia.basescan.org` → find your contract → Verify & Publish.
Paste the source code and compiler settings.

---

## Mainnet deploy (when ready)

Same process, but:
- Switch MetaMask to **Base Mainnet** (Chain ID `8453`, RPC `https://mainnet.base.org`)
- You need real ETH on Base (bridge from Ethereum at `bridge.base.org`)
- Cost per deploy: ~$0.05 on Base

---

## After deploy — run the Python bridge

```bash
cd ~/SUB-Terrainian
python web3/manifest_bridge.py --mbid <your-mbid>
```

This produces the metadata JSON for each release, ready for IPFS pinning.
