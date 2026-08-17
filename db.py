import json
import os
import sqlite3
from datetime import datetime, timedelta

SESSION_TIMEOUT = timedelta(minutes=7)

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
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS user_state (
                    user_id INTEGER PRIMARY KEY,
                    last_activity TEXT,
                    session_start TEXT,
                    mode TEXT DEFAULT 'normal',
                    meta_bank INTEGER,
                    meta_target INTEGER
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


def get_results_since(user_id, since_iso):
    conn = _conn()
    try:
        rows = conn.execute(
            "SELECT result FROM games "
            "WHERE user_id=? AND result IN ('won','lost') AND created_at >= ? "
            "ORDER BY id ASC",
            (user_id, since_iso),
        ).fetchall()
        return [r["result"] for r in rows]
    finally:
        conn.close()


def update_activity(user_id):
    now = datetime.utcnow()
    now_iso = now.isoformat()
    conn = _conn()
    try:
        with conn:
            row = conn.execute(
                "SELECT last_activity, session_start FROM user_state WHERE user_id=?",
                (user_id,),
            ).fetchone()
            if row is None:
                conn.execute(
                    "INSERT INTO user_state (user_id, last_activity, session_start, mode) "
                    "VALUES (?,?,?,'normal')",
                    (user_id, now_iso, now_iso),
                )
                return True, now_iso
            last = datetime.fromisoformat(row["last_activity"])
            if now - last > SESSION_TIMEOUT:
                conn.execute(
                    "UPDATE user_state SET last_activity=?, session_start=? WHERE user_id=?",
                    (now_iso, now_iso, user_id),
                )
                return True, now_iso
            conn.execute(
                "UPDATE user_state SET last_activity=? WHERE user_id=?",
                (now_iso, user_id),
            )
            return False, row["session_start"]
    finally:
        conn.close()


def get_user_state(user_id):
    conn = _conn()
    try:
        row = conn.execute(
            "SELECT mode, meta_bank, meta_target, session_start FROM user_state WHERE user_id=?",
            (user_id,),
        ).fetchone()
        if row:
            return {
                "mode": row["mode"],
                "meta_bank": row["meta_bank"],
                "meta_target": row["meta_target"],
                "session_start": row["session_start"],
            }
        return {"mode": "normal", "meta_bank": None, "meta_target": None, "session_start": None}
    finally:
        conn.close()


def set_meta(user_id, meta_bank, meta_target):
    now_iso = datetime.utcnow().isoformat()
    conn = _conn()
    try:
        with conn:
            conn.execute(
                """
                INSERT INTO user_state (user_id, last_activity, session_start, mode, meta_bank, meta_target)
                VALUES (?,?,?,'meta',?,?)
                ON CONFLICT(user_id) DO UPDATE SET
                    mode = 'meta',
                    meta_bank = excluded.meta_bank,
                    meta_target = excluded.meta_target
                """,
                (user_id, now_iso, now_iso, meta_bank, meta_target),
            )
    finally:
        conn.close()


def clear_meta(user_id):
    conn = _conn()
    try:
        with conn:
            conn.execute(
                "UPDATE user_state SET mode='normal', meta_bank=NULL, meta_target=NULL WHERE user_id=?",
                (user_id,),
            )
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
            for table in ("cells", "games", "risk_stats", "mine_log", "safe_log", "bank", "user_state", "stats"):
                conn.execute(
                    f"DELETE FROM {table} WHERE user_id=?", (user_id,)
                )
    finally:
        conn.close()
