import random

import db

GRID_ROWS = 5
GRID_COLS = 5
COL_LABELS = "ABCDE"
GRID_EMPTY = "🟦"
GRID_GEM = "💎"

# Casillas necesarias para alcanzar al menos x2 según el número de trampas.
X2_TILES = {
    1: 13, 2: 8, 3: 5, 4: 4, 5: 3, 6: 3, 7: 3,
    8: 2, 9: 2, 10: 2, 11: 2, 12: 2,
}


def suggested_count(mines):
    if mines in X2_TILES:
        return X2_TILES[mines]
    return 1


def signal_multiplier(mines):
    from math import comb

    k = suggested_count(mines)
    total = GRID_ROWS * GRID_COLS
    return comb(total, k) / comb(total - mines, k)


def generate_signal(user_id, mines):
    n = suggested_count(mines)
    mine_counts = db.get_mine_counts(user_id)
    safe_counts = db.get_safe_counts(user_id)
    total_mines = sum(mine_counts.values())

    if total_mines >= 50:
        expected = total_mines / (GRID_ROWS * GRID_COLS)
        stat = sum(
            ((mine_counts.get((r, c), 0) - expected) ** 2) / expected
            for r in range(GRID_ROWS)
            for c in range(GRID_COLS)
        )
        if stat > 36.415:  # chi-cuadrado df=24, p<0.05
            candidates = []
            for r in range(GRID_ROWS):
                for c in range(GRID_COLS):
                    candidates.append(
                        (
                            (r, c),
                            mine_counts.get((r, c), 0),
                            -safe_counts.get((r, c), 0),
                        )
                    )
            candidates.sort(key=lambda item: (item[1], item[2], random.random()))
            return [cell for cell, _, _ in candidates[:n]]

    # Sin sesgo detectable: juego justo, cualquier casilla es igual.
    candidates = [(r, c) for r in range(GRID_ROWS) for c in range(GRID_COLS)]
    random.shuffle(candidates)
    return candidates[:n]


def render_grid(cells):
    cells_set = set(cells)
    lines = []
    for r in range(GRID_ROWS):
        lines.append(
            "".join(GRID_GEM if (r, c) in cells_set else GRID_EMPTY for c in range(GRID_COLS))
        )
    return "\n".join(lines)


def cell_label(r, c):
    return f"{COL_LABELS[c]}{r + 1}"


def order_text(cells):
    if not cells:
        return ""
    return "Orden: " + ", ".join(cell_label(r, c) for r, c in cells)
