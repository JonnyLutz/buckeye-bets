CREATE TABLE IF NOT EXISTS games (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    game_number TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    price REAL NOT NULL,
    top_prize TEXT NOT NULL,
    overall_odds REAL,
    prizes_remaining INTEGER NOT NULL,
    scraped_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Phase 2 stubs
CREATE TABLE IF NOT EXISTS prize_tiers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id INTEGER NOT NULL REFERENCES games(id),
    prize_value REAL NOT NULL,
    total_prizes INTEGER NOT NULL,
    remaining_prizes INTEGER NOT NULL,
    scraped_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS ev_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    game_id INTEGER NOT NULL REFERENCES games(id),
    ev_value REAL NOT NULL,
    snapshot_date TEXT NOT NULL DEFAULT (date('now')),
    UNIQUE(game_id, snapshot_date)
);
