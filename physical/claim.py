#!/usr/bin/env python3
"""
physical/claim.py  —  SUB-Terrainian Sprint 4

Issues a soulbound EIP-5192 PhysicalClaim NFT on Base after physical
release verification. Uses raw JSON-RPC (no web3.py) — stays Termux-safe.

Requires a funded wallet and the PRIVATE_KEY env var (or hardware wallet via
Foundry's cast). The private key NEVER touches the manifest or git history.

Environment (.env):
    BASE_RPC_URL              e.g. https://mainnet.base.org
    PHYSICAL_CLAIM_ADDRESS    deployed PhysicalClaim contract
    PRIVATE_KEY               wallet private key (keep offline, never commit)
    CHAIN_ID                  8453 for Base mainnet, 84532 for Base Sepolia
"""

import hashlib
import json
import os
import time

import requests
from dotenv import load_dotenv

load_dotenv()

HEADERS   = {"User-Agent": "SubTerrainian/0.1 ( contact@ptliveddesign.example )"}
RPC_URL   = os.getenv("BASE_RPC_URL", "https://mainnet.base.org")
CONTRACT  = os.getenv("PHYSICAL_CLAIM_ADDRESS", "")
CHAIN_ID  = int(os.getenv("CHAIN_ID", "8453"))


# ── MBID → bytes32 (matches contract + manifest_bridge) ──────────────────────

def mbid_to_bytes32(mbid: str) -> str:
    return "0x" + hashlib.sha256(mbid.encode()).hexdigest()


# ── Raw JSON-RPC helpers ──────────────────────────────────────────────────────

def _rpc(method: str, params: list) -> dict:
    payload = {"jsonrpc": "2.0", "method": method, "params": params, "id": 1}
    r = requests.post(RPC_URL, json=payload, headers=HEADERS, timeout=15)
    r.raise_for_status()
    return r.json()


def get_nonce(address: str) -> int:
    result = _rpc("eth_getTransactionCount", [address, "latest"])
    return int(result["result"], 16)


def get_gas_price() -> int:
    result = _rpc("eth_gasPrice", [])
    return int(result["result"], 16)


def send_raw_tx(signed_tx_hex: str) -> str:
    result = _rpc("eth_sendRawTransaction", [signed_tx_hex])
    if "error" in result:
        raise RuntimeError(f"RPC error: {result['error']}")
    return result["result"]  # tx hash


def wait_for_receipt(tx_hash: str, timeout: int = 120) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = _rpc("eth_getTransactionReceipt", [tx_hash])
        receipt = result.get("result")
        if receipt:
            return receipt
        time.sleep(3)
    raise TimeoutError(f"Transaction {tx_hash} not confirmed within {timeout}s")


# ── ABI encode claim(address,bytes32) ─────────────────────────────────────────

def encode_claim(claimant: str, mbid_bytes32: str) -> str:
    """
    ABI-encode the call to claim(address claimant, bytes32 mbid).
    Function selector: keccak256("claim(address,bytes32)")[:4]
    = 0x2f926732 (pre-computed — verify with cast sig "claim(address,bytes32)")
    """
    selector = "2f926732"
    # address: 32 bytes, zero-padded left
    addr = claimant.lower().replace("0x", "").zfill(64)
    # bytes32: already 32 bytes
    b32  = mbid_bytes32.replace("0x", "")
    return "0x" + selector + addr + b32


# ── Sign and send (requires eth_account or cast) ──────────────────────────────

def claim_via_cast(claimant: str, mbid: str) -> str:
    """
    Uses Foundry's `cast send` for signing — keeps private key out of Python.
    Returns transaction hash.

    Requires cast on PATH: foundryup on Termux or any EVM dev machine.
    PRIVATE_KEY env var OR hardware wallet flag in cast.
    """
    import subprocess

    contract = CONTRACT
    if not contract:
        raise EnvironmentError("PHYSICAL_CLAIM_ADDRESS not set in .env")

    calldata  = encode_claim(claimant, mbid_to_bytes32(mbid))
    chain_arg = f"--chain-id {CHAIN_ID}"

    pk = os.getenv("PRIVATE_KEY")
    if pk:
        pk_arg = f"--private-key {pk}"
    else:
        pk_arg = "--ledger"  # hardware wallet fallback

    cmd = (
        f"cast send {contract} {calldata} "
        f"--rpc-url {RPC_URL} "
        f"{chain_arg} {pk_arg} "
        f"--json"
    )

    result = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"cast send failed:\n{result.stderr}")

    out = json.loads(result.stdout)
    return out.get("transactionHash", "")


def check_already_claimed(claimant: str, mbid: str) -> bool:
    """
    Read hasClaimed(address, bytes32) from contract via eth_call.
    Returns True if already claimed.
    """
    # hasClaimed(address,bytes32) selector = keccak256("hasClaimed(address,bytes32)")[:4]
    # Pre-computed: cast sig "hasClaimed(address,bytes32)"
    selector = "6e7a1e17"
    addr     = claimant.lower().replace("0x", "").zfill(64)
    b32      = mbid_to_bytes32(mbid).replace("0x", "")
    calldata = "0x" + selector + addr + b32

    result = _rpc("eth_call", [{"to": CONTRACT, "data": calldata}, "latest"])
    raw    = result.get("result", "0x")
    return raw != "0x" and int(raw, 16) != 0


def issue_physical_claim(claimant: str, mbid: str, dry_run: bool = False) -> str | None:
    """
    Issue a soulbound PhysicalClaim token.
    Returns transaction hash, or None on dry_run.

    claimant: wallet address of the physical owner (checksummed or lowercase)
    mbid:     MusicBrainz release UUID string
    """
    if not CONTRACT:
        raise EnvironmentError("PHYSICAL_CLAIM_ADDRESS not set in .env")

    print(f"Physical claim: {mbid[:8]}… → {claimant[:10]}…")

    if check_already_claimed(claimant, mbid):
        print("  Already claimed — nothing to do.")
        return None

    if dry_run:
        print(f"  [dry-run] would call claim({claimant}, {mbid_to_bytes32(mbid)})")
        return None

    tx_hash = claim_via_cast(claimant, mbid)
    print(f"  Sent: {tx_hash}")

    receipt = wait_for_receipt(tx_hash)
    if receipt.get("status") == "0x1":
        print(f"  Confirmed in block {int(receipt['blockNumber'], 16)}")
    else:
        print(f"  Transaction reverted!")

    return tx_hash


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 3:
        print("Usage: python physical/claim.py <wallet_address> <mbid> [--dry-run]")
        sys.exit(1)
    dry = "--dry-run" in sys.argv
    issue_physical_claim(sys.argv[1], sys.argv[2], dry_run=dry)
