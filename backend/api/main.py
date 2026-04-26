from typing import Optional
from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from backend.db.database import get_conn, init_db
from backend.scrapers.scratchoff import run as run_scrape
from backend.scrapers.prizes import run as run_prize_scrape
from backend.ev import calculate_all_ev

app = FastAPI(title="BuckeyeBets")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.on_event("startup")
def startup():
    init_db()
    # Auto-refresh if data is stale (no EV snapshot from today)
    from datetime import date
    conn = get_conn()
    row = conn.execute(
        "SELECT COUNT(*) as c FROM ev_snapshots WHERE snapshot_date = ?",
        (date.today().isoformat(),),
    ).fetchone()
    conn.close()
    if row["c"] == 0:
        try:
            run_scrape()
            run_prize_scrape()
            calculate_all_ev()
        except Exception as e:
            print(f"Auto-refresh failed: {e}")


def row_to_dict(row):
    return dict(row)


@app.get("/api/scratchoff/games")
def list_games(
    price: Optional[float] = Query(None),
    sort: str = Query("overall_odds"),
    order: str = Query("asc"),
):
    conn = get_conn()
    allowed_sorts = {"name", "price", "top_prize", "overall_odds", "prizes_remaining", "game_number", "ev_value", "return_pct"}
    sort_col = sort if sort in allowed_sorts else "overall_odds"
    direction = "DESC" if order.lower() == "desc" else "ASC"

    query = """SELECT g.*, ev.ev_value, 
               CASE WHEN g.price > 0 THEN ROUND(100.0 * ev.ev_value / g.price, 1) ELSE NULL END as return_pct
               FROM games g
               LEFT JOIN ev_snapshots ev ON ev.game_id = g.id 
                 AND ev.snapshot_date = (SELECT MAX(snapshot_date) FROM ev_snapshots WHERE game_id = g.id)"""
    params = []
    if price is not None:
        query += " WHERE g.price = ?"
        params.append(price)

    if sort_col in ("ev_value", "return_pct"):
        query += f" ORDER BY {sort_col} IS NULL, {sort_col} {direction}"
    elif sort_col == "overall_odds":
        query += f" ORDER BY g.overall_odds IS NULL, g.overall_odds {direction}"
    else:
        query += f" ORDER BY g.{sort_col} {direction}"

    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [row_to_dict(r) for r in rows]


@app.get("/api/scratchoff/games/{game_number}")
def get_game(game_number: str):
    conn = get_conn()
    row = conn.execute("""
        SELECT g.*, ev.ev_value,
               CASE WHEN g.price > 0 THEN ROUND(100.0 * ev.ev_value / g.price, 1) ELSE NULL END as return_pct
        FROM games g
        LEFT JOIN ev_snapshots ev ON ev.game_id = g.id
          AND ev.snapshot_date = (SELECT MAX(snapshot_date) FROM ev_snapshots WHERE game_id = g.id)
        WHERE g.game_number = ?""", (game_number,)).fetchone()
    if not row:
        conn.close()
        return {"error": "Game not found"}, 404

    game = row_to_dict(row)

    # Include prize tiers
    tiers = conn.execute(
        "SELECT prize_value, total_prizes, remaining_prizes FROM prize_tiers WHERE game_id = ? ORDER BY prize_value DESC",
        (game["id"],),
    ).fetchall()
    game["prize_tiers"] = [row_to_dict(t) for t in tiers]

    # Include EV history
    history = conn.execute(
        "SELECT ev_value, snapshot_date FROM ev_snapshots WHERE game_id = ? ORDER BY snapshot_date",
        (game["id"],),
    ).fetchall()
    game["ev_history"] = [row_to_dict(h) for h in history]

    conn.close()
    return game


@app.get("/api/scratchoff/best")
def best_games(limit: int = Query(10)):
    conn = get_conn()
    rows = conn.execute("""
        SELECT g.*, ev.ev_value,
               CASE WHEN g.price > 0 THEN ROUND(100.0 * ev.ev_value / g.price, 1) ELSE NULL END as return_pct
        FROM games g
        LEFT JOIN ev_snapshots ev ON ev.game_id = g.id
          AND ev.snapshot_date = (SELECT MAX(snapshot_date) FROM ev_snapshots WHERE game_id = g.id)
        WHERE ev.ev_value IS NOT NULL
        ORDER BY (ev.ev_value / g.price) DESC LIMIT ?""",
        (limit,),
    ).fetchall()
    conn.close()
    return [row_to_dict(r) for r in rows]


@app.post("/api/scratchoff/scrape")
def trigger_scrape():
    games = run_scrape()
    return {"scraped": len(games)}


@app.post("/api/scratchoff/scrape-prizes")
def trigger_prize_scrape():
    games = run_prize_scrape()
    count = calculate_all_ev()
    return {"games_with_prizes": len(games), "ev_calculated": count}
