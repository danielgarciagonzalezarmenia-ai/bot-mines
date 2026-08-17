import random

import signals

GRID_TOTAL = 25
CHI2_CRIT_95 = 36.415  # df=24, p=0.05
CHI2_CRIT_99 = 42.980  # df=24, p=0.01


def monte_carlo(mines, tiles, games=100000, seed=42):
    rng = random.Random(seed)
    wins = 0
    hits = [0] * GRID_TOTAL
    for _ in range(games):
        board = set(rng.sample(range(GRID_TOTAL), mines))
        chosen = rng.sample(range(GRID_TOTAL), tiles)
        if board.isdisjoint(chosen):
            wins += 1
        else:
            for c in chosen:
                if c in board:
                    hits[c] += 1
    mult = signals.signal_multiplier(mines)
    win_rate = wins / games
    return {
        "games": games,
        "mines": mines,
        "tiles": tiles,
        "mult": mult,
        "win_rate": win_rate,
        "ev": round(mult * win_rate, 4),
        "hits": hits,
        "hit_rate": round(sum(hits) / (games * tiles), 6),
    }


def _pad_counts(counts):
    return [counts.get((r, c), 0) for r in range(signals.GRID_ROWS) for c in range(signals.GRID_COLS)]


def chi_square_uniformity(counts):
    total = sum(counts.values())
    if total < 50:
        return None
    padded = _pad_counts(counts)
    expected = total / GRID_TOTAL
    stat = sum(((o - expected) ** 2) / expected for o in padded)
    return {
        "total": total,
        "expected": expected,
        "stat": round(stat, 2),
        "biased": stat > CHI2_CRIT_95,
        "strong_biased": stat > CHI2_CRIT_99,
    }


def best_cells_by_data(mines, mine_counts, safe_counts):
    scores = []
    for r in range(signals.GRID_ROWS):
        for c in range(signals.GRID_COLS):
            scores.append(
                (
                    (r, c),
                    mine_counts.get((r, c), 0),
                    -safe_counts.get((r, c), 0),
                )
            )
    scores.sort(key=lambda item: (item[1], item[2], random.random()))
    return [cell for cell, _, _ in scores[: signals.suggested_count(mines)]]


def render_recommendation(indices):
    lines = []
    for r in range(signals.GRID_ROWS):
        row = "".join(
            signals.GRID_GEM if (r, c) in set(indices) else signals.GRID_EMPTY
            for c in range(signals.GRID_COLS)
        )
        lines.append(row)
    return "\n".join(lines)