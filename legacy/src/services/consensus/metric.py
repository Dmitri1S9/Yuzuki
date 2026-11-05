"""The pairwise agreement metric consensus_rank's search optimizes: each
pass reduced to pairwise labels {>, <, =}, Cohen's kappa between two such
label sets, and the maximin key that lexicographically prioritizes the
worst-agreeing pass first.
"""
import math

import numpy as np

CATS = (-1, 0, 1)
NEG_INF = float("-inf")


def sign_matrix(vec: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """vec: float array, NaN = missing. Returns (codes in {-1,0,1}, valid mask)."""
    diff = vec[:, None] - vec[None, :]
    valid = ~np.isnan(diff)
    np.fill_diagonal(valid, False)
    codes = np.sign(np.nan_to_num(diff, nan=0.0)).astype(np.int8)
    return codes, valid


def cohen_kappa_masked(codes_a: np.ndarray, codes_b: np.ndarray, valid: np.ndarray) -> float:
    a, b = codes_a[valid], codes_b[valid]
    n = a.size
    if n == 0:
        return float("nan")
    conf = np.zeros((3, 3), dtype=np.float64)
    for i, cv in enumerate(CATS):
        am = a == cv
        if not am.any():
            continue
        for j, dv in enumerate(CATS):
            conf[i, j] = np.sum(am & (b == dv))
    po = np.trace(conf) / n
    row, col = conf.sum(axis=1), conf.sum(axis=0)
    pe = np.sum(row * col) / (n * n)
    if abs(1.0 - pe) < 1e-10:
        return float("nan")
    return float((po - pe) / (1.0 - pe))


def block_vector(blocks: list[list[int]], m: int) -> np.ndarray:
    vec = np.empty(m, dtype=np.int32)
    for b_idx, block in enumerate(blocks):
        for i in block:
            vec[i] = b_idx
    return vec


def evaluate(blocks: list[list[int]], pass_codes: dict, pass_valid: dict, m: int,
             passes: tuple) -> tuple:
    bvec = block_vector(blocks, m)
    codes_r, _ = sign_matrix(bvec.astype(np.float64))
    return tuple(cohen_kappa_masked(pass_codes[p], codes_r, pass_valid[p]) for p in passes)


def maximin_key(kappas: tuple) -> tuple:
    vals = [NEG_INF if math.isnan(k) else k for k in kappas]
    return tuple(sorted(vals))
