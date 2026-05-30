"""Tests for shortssync.matcher (REF-1 / PERF-1 / PERF-3).

The vectorized matcher must produce identical results to the previous inline
sliding-window loop. ``_naive_ber`` reimplements that loop over unpacked bits
and is used as the oracle.
"""

import numpy as np

from shortssync.matcher import find_best_match, fingerprint_ber


def _naive_ber(query_fp: np.ndarray, ref_fp: np.ndarray) -> float:
    """Reference implementation copied from the original inline matching loop."""
    q_bits = np.unpackbits(np.asarray(query_fp, dtype=np.uint32).view(np.uint8))
    r_bits = np.unpackbits(np.asarray(ref_fp, dtype=np.uint32).view(np.uint8))
    n_q = len(q_bits)
    n_r = len(r_bits)
    if n_q == 0 or n_q > n_r:
        return 1.0
    n_windows = (n_r // 32) - len(query_fp) + 1
    if n_windows < 1:
        return 1.0
    min_dist = float("inf")
    for w in range(n_windows):
        start = w * 32
        end = start + n_q
        sub_r = r_bits[start:end]
        dist = np.count_nonzero(np.bitwise_xor(q_bits, sub_r))
        if dist < min_dist:
            min_dist = dist
    return min_dist / n_q if n_q > 0 else 1.0


def test_identical_fingerprint_is_zero_ber():
    fp = np.array([1, 2, 3, 4, 5], dtype=np.uint32)
    assert fingerprint_ber(fp, fp) == 0.0


def test_query_longer_than_reference_returns_one():
    q = np.arange(10, dtype=np.uint32)
    r = np.arange(3, dtype=np.uint32)
    assert fingerprint_ber(q, r) == 1.0


def test_empty_query_returns_one():
    assert fingerprint_ber(np.array([], dtype=np.uint32), np.arange(5, dtype=np.uint32)) == 1.0


def test_subsequence_match_found_at_offset():
    ref = np.array([10, 20, 30, 40, 50, 60], dtype=np.uint32)
    query = ref[2:5].copy()  # 30,40,50 -> perfect match at offset 2
    assert fingerprint_ber(query, ref) == 0.0


def test_matches_naive_reference_on_random_data():
    rng = np.random.default_rng(1234)
    for _ in range(200):
        q_len = int(rng.integers(1, 8))
        r_len = int(rng.integers(1, 16))
        q = rng.integers(0, 2**32, size=q_len, dtype=np.uint64).astype(np.uint32)
        r = rng.integers(0, 2**32, size=r_len, dtype=np.uint64).astype(np.uint32)
        assert fingerprint_ber(q, r) == _naive_ber(q, r)


def test_find_best_match_selects_lowest_ber_under_threshold():
    ref = np.array([1, 2, 3, 4], dtype=np.uint32)
    refs = {
        "exact": ref,
        "noise": np.array([0xFFFFFFFF, 0, 0xFFFFFFFF, 0], dtype=np.uint32),
    }
    name, ber = find_best_match(ref, refs, threshold=0.15)
    assert name == "exact"
    assert ber == 0.0


def test_find_best_match_returns_none_when_above_threshold():
    query = np.array([0x0F0F0F0F], dtype=np.uint32)
    refs = {"a": np.array([0xF0F0F0F0], dtype=np.uint32)}  # all 32 bits differ -> BER 1.0
    name, ber = find_best_match(query, refs, threshold=0.15)
    assert name is None
    assert ber == 1.0


def test_find_best_match_keeps_first_on_tie():
    query = np.array([1], dtype=np.uint32)
    refs = {"first": np.array([1], dtype=np.uint32), "second": np.array([1], dtype=np.uint32)}
    name, _ = find_best_match(query, refs, threshold=0.15)
    assert name == "first"
