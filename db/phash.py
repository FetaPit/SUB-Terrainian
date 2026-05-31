"""
db/phash.py  —  SUB-Terrainian

In-tree perceptual hash. No imagehash / PyWavelets / scipy dependency.
Implements pHash (DCT, canonical) and dHash (gradient, prefilter).
Both run on numpy + PIL only.
"""

from __future__ import annotations

import numpy as np
from PIL import Image


# ── pHash (DCT-based) ─────────────────────────────────────────────────────────

def phash(img_path: str, hash_size: int = 8) -> str:
    """
    Perceptual hash via 2D DCT. Robust against JPEG re-encode and scaling.
    Returns a 16-char hex string (64 bits).
    """
    img = (
        Image.open(img_path)
        .convert("L")
        .resize((hash_size * 4, hash_size * 4), Image.LANCZOS)
    )
    pixels = np.array(img, dtype=float)
    dct_block = _dct2(pixels)
    low_freq  = dct_block[:hash_size, :hash_size]
    median    = np.median(low_freq)
    bits      = (low_freq > median).flatten()
    return _bits_to_hex(bits)


def _dct2(a: np.ndarray) -> np.ndarray:
    """Separable 2D DCT-II via numpy (no scipy)."""
    N = a.shape[0]
    n = np.arange(N)
    k = n[:, np.newaxis]
    D = np.cos(np.pi * k * (2 * n + 1) / (2 * N))
    return D @ a @ D.T


# ── dHash (gradient-based) ────────────────────────────────────────────────────

def dhash(img_path: str, hash_size: int = 8) -> str:
    """
    Difference hash — fast gradient prefilter.
    Returns a 16-char hex string (64 bits).
    """
    img = (
        Image.open(img_path)
        .convert("L")
        .resize((hash_size + 1, hash_size), Image.LANCZOS)
    )
    pixels = np.array(img)
    diff   = pixels[:, 1:] > pixels[:, :-1]
    return _bits_to_hex(diff.flatten())


# ── Comparison ────────────────────────────────────────────────────────────────

def hamming(h1: str, h2: str) -> int:
    """Bit-level Hamming distance between two hex hash strings."""
    return bin(int(h1, 16) ^ int(h2, 16)).count("1")


def is_duplicate(h1: str, h2: str, threshold: int = 10) -> bool:
    """
    Returns True if two images are perceptually identical.
    threshold=10 catches JPEG re-encodes; lower = stricter.
    """
    return hamming(h1, h2) <= threshold


# ── Utility ───────────────────────────────────────────────────────────────────

def _bits_to_hex(bits: np.ndarray) -> str:
    n = int("".join("1" if b else "0" for b in bits), 2)
    hex_len = len(bits) // 4
    return hex(n)[2:].zfill(hex_len)
