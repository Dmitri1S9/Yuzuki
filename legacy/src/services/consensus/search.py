"""The block-structure search: a Borda-score initial ordering, then hill
climbing over merge/split/transfer/swap moves, accepting the first move
that improves the maximin kappa key (see metric.py). Blocked from ever
merging two different majority tiers together (see tiers.py).
"""
import random

from src.services.consensus.metric import evaluate, maximin_key
from src.services.consensus.tiers import block_tier, tiers_compatible

WINDOW = 5


def borda_init(names: list[int], borda_score: dict, tiers: dict, maj_tier: dict, passes: tuple,
                rng: random.Random | None = None) -> list[list[int]]:
    if rng is not None:
        noisy = {n: borda_score[n] + rng.gauss(0, 0.5) for n in names}
        order = sorted(names, key=lambda n: noisy[n])
    else:
        order = sorted(names, key=lambda n: borda_score[n])

    blocks: list[list[int]] = [[order[0]]]
    current_tier = maj_tier[order[0]]
    for a, b in zip(order, order[1:]):
        distinct_votes = sum(
            1 for p in passes
            if tiers[p].get(a) is not None and tiers[p].get(b) is not None and tiers[p][a] != tiers[p][b]
        )
        b_tier = maj_tier[b]
        if distinct_votes >= 2 or not tiers_compatible(current_tier, b_tier):
            blocks.append([b])
            current_tier = b_tier
        else:
            blocks[-1].append(b)
            if current_tier is None:
                current_tier = b_tier
    return blocks


def gen_moves(blocks: list[list[int]], positions: dict):
    k = len(blocks)
    for i in range(k - 1):
        yield ("merge", i)
    for i, block in enumerate(blocks):
        for split_at in range(1, len(block)):
            yield ("split", i, split_at)
    for i, block in enumerate(blocks):
        for elem in block:
            if i > 0:
                yield ("transfer_neighbor", i, elem, i - 1)
            if i < k - 1:
                yield ("transfer_neighbor", i, elem, i + 1)
    for i in range(k - 1):
        yield ("swap", i)
    for i, block in enumerate(blocks):
        for elem in block:
            p = positions[elem]
            targets = {
                j for j, other in enumerate(blocks)
                if j != i and any(abs(positions[o] - p) <= WINDOW for o in other)
            }
            for j in targets:
                yield ("window_transfer", i, elem, j)


def apply_move(blocks: list[list[int]], move, maj_tier: dict) -> list[list[int]] | None:
    blocks = [list(b) for b in blocks]
    kind = move[0]

    if kind == "merge":
        i = move[1]
        if not tiers_compatible(block_tier(blocks[i], maj_tier), block_tier(blocks[i + 1], maj_tier)):
            return None
        blocks[i] = blocks[i] + blocks[i + 1]
        del blocks[i + 1]

    elif kind == "split":
        _, i, at = move
        block = blocks[i]
        blocks[i:i + 1] = [block[:at], block[at:]]

    elif kind in ("transfer_neighbor", "window_transfer"):
        _, i, elem, j = move
        if len(blocks[i]) <= 1:
            return None  # would empty the source block — not a valid move
        if not tiers_compatible(maj_tier[elem], block_tier(blocks[j], maj_tier)):
            return None
        blocks[i].remove(elem)
        blocks[j].append(elem)
        if not blocks[i]:
            return None

    elif kind == "swap":
        i = move[1]
        blocks[i], blocks[i + 1] = blocks[i + 1], blocks[i]

    return [b for b in blocks if b]


def hill_climb(blocks: list[list[int]], pass_codes: dict, pass_valid: dict, m: int, maj_tier: dict,
                passes: tuple) -> list[list[int]]:
    current_key = maximin_key(evaluate(blocks, pass_codes, pass_valid, m, passes))
    improved = True
    while improved:
        improved = False
        positions = {elem: pos for pos, elem in enumerate(e for b in blocks for e in b)}
        for move in gen_moves(blocks, positions):
            candidate = apply_move(blocks, move, maj_tier)
            if candidate is None or len(candidate) < 1:
                continue
            cand_key = maximin_key(evaluate(candidate, pass_codes, pass_valid, m, passes))
            if cand_key > current_key:
                blocks, current_key = candidate, cand_key
                improved = True
                break
    return blocks
