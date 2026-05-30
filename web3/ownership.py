#!/usr/bin/env python3
"""
ownership.py  —  SUB-Terrainian Sprint 3 stub

Read-only ownership checks against MusicEdition and PhysicalClaim
contracts on Base via JSON-RPC. No transaction signing required.

Environment (.env):
    BASE_RPC_URL             e.g. https://mainnet.base.org or Alchemy/Infura URL
    MUSIC_EDITION_ADDRESS    deployed MusicEdition contract
    PHYSICAL_CLAIM_ADDRESS   deployed PhysicalClaim contract
"""

import json
import os
from web3 import Web3
from dotenv import load_dotenv
from web3.manifest_bridge import mbid_to_token_id, mbid_to_bytes32

load_dotenv()

_w3 = None

def _get_w3() -> Web3:
    global _w3
    if _w3 is None:
        rpc = os.getenv("BASE_RPC_URL", "https://mainnet.base.org")
        _w3 = Web3(Web3.HTTPProvider(rpc))
    return _w3


# Minimal ABI fragments — only what we need for read calls

_EDITION_ABI = json.loads('[{"inputs":[{"type":"address"},{"type":"uint256"}],"name":"balanceOf","outputs":[{"type":"uint256"}],"stateMutability":"view","type":"function"}]')

_PHYSICAL_ABI = json.loads('[{"inputs":[{"type":"address"},{"type":"bytes32"}],"name":"hasClaimed","outputs":[{"type":"bool"}],"stateMutability":"view","type":"function"}]')


def owns_edition(wallet: str, mbid: str) -> bool:
    """True if `wallet` holds at least one MusicEdition token for `mbid`."""
    addr = os.getenv("MUSIC_EDITION_ADDRESS")
    if not addr:
        raise EnvironmentError("MUSIC_EDITION_ADDRESS not set in .env")

    w3 = _get_w3()
    contract = w3.eth.contract(address=Web3.to_checksum_address(addr), abi=_EDITION_ABI)
    token_id = mbid_to_token_id(mbid)
    balance = contract.functions.balanceOf(
        Web3.to_checksum_address(wallet), token_id
    ).call()
    return balance > 0


def owns_physical(wallet: str, mbid: str) -> bool:
    """True if `wallet` has a soulbound physical claim for `mbid`."""
    addr = os.getenv("PHYSICAL_CLAIM_ADDRESS")
    if not addr:
        raise EnvironmentError("PHYSICAL_CLAIM_ADDRESS not set in .env")

    w3 = _get_w3()
    contract = w3.eth.contract(address=Web3.to_checksum_address(addr), abi=_PHYSICAL_ABI)
    bytes32_mbid = bytes.fromhex(mbid_to_bytes32(mbid)[2:])
    return contract.functions.hasClaimed(
        Web3.to_checksum_address(wallet), bytes32_mbid
    ).call()


def owns_any(wallet: str, mbid: str) -> bool:
    """True if wallet owns the digital edition OR the physical SBT."""
    return owns_edition(wallet, mbid) or owns_physical(wallet, mbid)
