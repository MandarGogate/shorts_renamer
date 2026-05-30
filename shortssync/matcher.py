"""
Shared audio-fingerprint matcher (REF-1).

A single, vectorized implementation of the sliding-window Chromaprint matcher
used by the CLI, GUI, monitor, and web backend. Operating on the raw ``uint32``
fingerprint arrays (rather than 8x-larger unpacked bit arrays) keeps the
reference index compact (PERF-3) and lets NumPy compute every window distance
at once (PERF-1).

Algorithm (identical results to the previous per-call loops):
    The query (Q uint32 words) is slid across the reference (R words) at
    32-bit / one-word granularity. For each offset the Hamming distance between
    the query and the R-window is computed; the minimum distance divided by the
    query bit-length (Q * 32) is the Bit Error Rate (BER). Lower is better.
"""

from __future__ import annotations

from typing import Dict, Iterable, Mapping, Optional, Tuple

import numpy as np

# Bits set per byte value, for fast popcount over a uint8 view.
_POPCOUNT8 = np.array([bin(i).count("1") for i in range(256)], dtype=np.uint16)

# Bits per fingerprint word.
_WORD_BITS = 32


def fingerprint_ber(query_fp: np.ndarray, ref_fp: np.ndarray) -> float:
    """
    Minimum Bit Error Rate of ``query_fp`` slid across ``ref_fp``.

    Returns 1.0 (no usable match) when the query is empty or longer than the
    reference. Inputs are raw ``uint32`` Chromaprint arrays.
    """
    q = np.asarray(query_fp, dtype=np.uint32).ravel()
    r = np.asarray(ref_fp, dtype=np.uint32).ravel()

    q_len = q.shape[0]
    r_len = r.shape[0]
    if q_len == 0 or q_len > r_len:
        return 1.0

    # Sliding windows of the reference, shape (R-Q+1, Q); a strided view (cheap).
    windows = np.lib.stride_tricks.sliding_window_view(r, q_len)

    # Hamming distance per window: popcount(window XOR query) summed over words.
    xor = windows ^ q  # (W, Q) uint32, materialized + contiguous
    per_window = _POPCOUNT8[xor.view(np.uint8)].sum(axis=1)  # (W,)

    return float(per_window.min()) / (q_len * _WORD_BITS)


def find_best_match(
    query_fp: np.ndarray,
    ref_fps: Mapping[str, np.ndarray],
    threshold: float,
) -> Tuple[Optional[str], float]:
    """
    Find the lowest-BER reference for ``query_fp``.

    Returns ``(matched_label, best_ber)`` where ``matched_label`` is the
    reference name when ``best_ber < threshold``, else ``None``. ``best_ber``
    is always the lowest BER seen (1.0 if no reference was comparable), so
    callers can report it even on a miss.

    Iteration order, strict "<" comparison, and the early exit on a perfect
    match mirror the previous inline implementations exactly.
    """
    best_ber = 1.0
    best_ref: Optional[str] = None

    for name, ref_fp in ref_fps.items():
        ber = fingerprint_ber(query_fp, ref_fp)
        if ber < best_ber:
            best_ber = ber
            best_ref = name
            if best_ber == 0.0:
                break

    if best_ref is not None and best_ber < threshold:
        return best_ref, best_ber
    return None, best_ber


def to_reference_fingerprint(fp: np.ndarray) -> np.ndarray:
    """Normalize a raw fpcalc fingerprint to the stored reference form (uint32)."""
    return np.asarray(fp, dtype=np.uint32).ravel()


def iter_reference_fingerprints(
    items: Iterable[Tuple[str, np.ndarray]]
) -> Dict[str, np.ndarray]:
    """Build a name -> uint32 fingerprint index from (name, fp) pairs."""
    return {name: to_reference_fingerprint(fp) for name, fp in items}
