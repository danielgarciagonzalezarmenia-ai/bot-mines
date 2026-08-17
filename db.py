import json
import os
import sqlite3
from datetime import datetime

DATA_DIR = os.environ.get("DATA_DIR", os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(DATA_DIR, "bot.db")


def _conn():
    os.makedirs(DATA_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = _conn()
    try:
        with conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS cells (
                    user_id INTEGER,
                    row INTEGER,
                    col INTEGER,
                    opened INTEGER DEFAULT 0,
                    wins INTEGER DEFAULT 0,
                    losses INTEGER DEFAULT 0,
                    PRIMARY KEY (user_id, row, col)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS games (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    mines INTEGER,
                    suggested TEXT,
                    result TEXT DEFAULT 'pending',
                    created_at TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS stats (
                    user_id INTEGER PRIMARY KEY,
                    games INTEGER DEFAULT 0,
                    wins INTEGER DEFAULT 0,
                    losses INTEGER DEFAULT 0
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS risk_stats (
                    user_id INTEGER,
                    mines INTEGER,
                    games INTEGER DEFAULT 0,
                    wins INTEGER DEFAULT 0,
                    PRIMARY KEY (user_id, mines)
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS mine_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    row INTEGER,
                    col INTEGER,
                    created_at TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS safe_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    row INTEGER,
                    col INTEGER,
                    created_at TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS bank (
                    user_id INTEGER PRIMARY KEY,
                    bank INTEGER NOT NULL,
                    updated_at TEXT
                )
                """
            )
            try:
                conn.execute("ALTER TABLE games ADD COLUMN stake INTEGER")
            except sqlite3.OperationalError:
                pass
    finally:
        conn.close()


def get_cell_stats(user_id):
    conn = _conn()
    try:
        return conn.execute(
            "SELECT row, col, opened, wins, losses FROM cells WHERE user_id=?",
            (user_id,),
        ).fetchall()
    finally:
        conn.close()


def get_user_stats(user_id):
    conn = _conn()
    try:
        row = conn.execute(
            "SELECT games, wins, losses FROM stats WHERE user_id=?", (user_id,)
        ).fetchone()
        if row:
            return {"games": row["games"], "wins": row["wins"], "losses": row["losses"]}
        return {"games": 0, "wins": 0, "losses": 0}
    finally:
        conn.close()


def get_risk_stats(user_id):
    conn = _conn()
    try:
        return conn.execute(
            "SELECT mines, games, wins FROM risk_stats WHERE user_id=? ORDER BY mines",
            (user_id,),
        ).fetchall()
    finally:
        conn.close()


def create_game(user_id, mines, cells, stake=None):
    conn = _conn()
    try:
        with conn:
            conn.execute(
                "DELETE FROM games WHERE user_id=? AND result='pending'",
                (user_id,),
            )
            conn.execute(
                "INSERT INTO games (user_id, mines, suggested, stake, created_at) VALUES (?,?,?,?,?)",
                (user_id, mines, json.dumps(cells), stake, datetime.utcnow().isoformat()),
            )
    finally:
        conn.close()


def get_pending_game(user_id):
    conn = _conn()
    try:
        row = conn.execute(
            "SELECT id, mines, suggested, stake FROM games "
            "WHERE user_id=? AND result='pending' ORDER BY id DESC LIMIT 1",
            (user_id,),
        ).fetchone()
        if row:
            return {
                "id": row["id"],
                "mines": row["mines"],
                "stake": row["stake"] or 0,
                "suggested": [tuple(cell) for cell in json.loads(row["suggested"])],
            }
        return None
    finally:
        conn.close()


def resolve_game(game_id, won):
    conn = _conn()
    try:
        with conn:
            game = conn.execute(
                "SELECT user_id, mines, suggested FROM games WHERE id=?", (game_id,)
            ).fetchone()
            if not game:
                return
            user_id = game["user_id"]
            cells = json.loads(game["suggested"])
            result = "won" if won else "lost"
            conn.execute("UPDATE games SET result=? WHERE id=?", (result, game_id))

            for r, c in cells:
                conn.execute(
                    """
                    INSERT INTO cells (user_id, row, col, opened, wins, losses)
                    VALUES (?,?,?,1,?,?)
                    ON CONFLICT(user_id, row, col) DO UPDATE SET
                        opened = opened + 1,
                        wins = wins + excluded.wins,
                        losses = losses + excluded.losses
                    """,
                    (user_id, r, c, 1 if won else 0, 0 if won else 1),
                )

            conn.execute(
                """
                INSERT INTO stats (user_id, games, wins, losses)
                VALUES (?,1,?,?)
                ON CONFLICT(user_id) DO UPDATE SET
                    games = games + 1,
                    wins = wins + excluded.wins,
                    losses = losses + excluded.losses
                """,
                (user_id, 1 if won else 0, 0 if won else 1),
            )

            conn.execute(
                """
                INSERT INTO risk_stats (user_id, mines, games, wins)
                VALUES (?,?,1,?)
                ON CONFLICT(user_id, mines) DO UPDATE SET
                    games = games + 1,
                    wins = wins + excluded.wins
                """,
                (user_id, game["mines"], 1 if won else 0),
            )
    finally:
        conn.close()


def log_mine(user_id, row, col):
    conn = _conn()
    try:
        with conn:
            conn.execute(
                "INSERT INTO mine_log (user_id, row, col, created_at) VALUES (?,?,?,?)",
                (user_id, row, col, datetime.utcnow().isoformat()),
            )
    finally:
        conn.close()


def log_many_mines(user_id, cells):
    conn = _conn()
    try:
        with conn:
            ts = datetime.utcnow().isoformat()
            for row, col in cells:
                conn.execute(
                    "INSERT INTO mine_log (user_id, row, col, created_at) VALUES (?,?,?,?)",
                    (user_id, row, col, ts),
                )
    finally:
        conn.close()


def log_safe_cells(user_id, cells):
    conn = _conn()
    try:
        with conn:
            ts = datetime.utcnow().isoformat()
            for row, col in cells:
                conn.execute(
                    "INSERT INTO safe_log (user_id, row, col, created_at) VALUES (?,?,?,?)",
                    (user_id, row, col, ts),
                )
    finally:
        conn.close()


def get_mine_counts(user_id):
    conn = _conn()
    try:
        rows = conn.execute(
            "SELECT row, col, COUNT(*) AS n FROM mine_log "
            "WHERE user_id=? GROUP BY row, col",
            (user_id,),
        ).fetchall()
        return {(r["row"], r["col"]): r["n"] for r in rows}
    finally:
        conn.close()


def get_safe_counts(user_id):
    conn = _conn()
    try:
        rows = conn.execute(
            "SELECT row, col, COUNT(*) AS n FROM safe_log "
            "WHERE user_id=? GROUP BY row, col",
            (user_id,),
        ).fetchall()
        return {(r["row"], r["col"]): r["n"] for r in rows}
    finally:
        conn.close()


def get_results(user_id):
    conn = _conn()
    try:
        rows = conn.execute(
            "SELECT result FROM games "
            "WHERE user_id=? AND result IN ('won','lost') ORDER BY id ASC",
            (user_id,),
        ).fetchall()
        return [r["result"] for r in rows]
    finally:
        conn.close()


def get_bank(user_id):
    conn = _conn()
    try:
        row = conn.execute(
            "SELECT bank FROM bank WHERE user_id=?", (user_id,)
        ).fetchone()
        return row["bank"] if row else None
    finally:
        conn.close()


def set_bank(user_id, amount):
    conn = _conn()
    try:
        with conn:
            conn.execute(
                """
                INSERT INTO bank (user_id, bank, updated_at) VALUES (?,?,?)
                ON CONFLICT(user_id) DO UPDATE SET
                    bank = excluded.bank,
                    updated_at = excluded.updated_at
                """,
                (user_id, amount, datetime.utcnow().isoformat()),
            )
    finally:
        conn.close()


def update_bank(user_id, delta):
    conn = _conn()
    try:
        with conn:
            cur = conn.execute(
                "SELECT bank FROM bank WHERE user_id=?", (user_id,)
            ).fetchone()
            if cur:
                new_bank = max(0, cur["bank"] + delta)
                conn.execute(
                    "UPDATE bank SET bank=?, updated_at=? WHERE user_id=?",
                    (new_bank, datetime.utcnow().isoformat(), user_id),
                )
    finally:
        conn.close()


def reset_user(user_id):
    conn = _conn()
    try:
        with conn:
            for table in ("cells", "games", "risk_stats", "mine_log", "safe_log", "bank", "stats"):
                conn.execute(
                    f"DELETE FROM {table} WHERE user_id=?", (user_id,)
                )
    finally:
        conn.close()
