"""Calculate expected value for scratch-off games."""
from typing import Optional
from datetime import date
from backend.db.database import get_conn


def calculate_ev(game_id: int, conn=None) -> Optional[float]:
    """Calculate EV for a single game. Returns EV per ticket or None if insufficient data."""
    close = conn is None
    if close:
        conn = get_conn()

    game = conn.execute("SELECT price, overall_odds FROM games WHERE id = ?", (game_id,)).fetchone()
    if not game or not game["overall_odds"]:
        if close:
            conn.close()
        return None

    tiers = conn.execute(
        "SELECT prize_value, total_prizes, remaining_prizes FROM prize_tiers WHERE game_id = ?",
        (game_id,),
    ).fetchall()

    if not tiers:
        if close:
            conn.close()
        return None

    odds = game["overall_odds"]
    price = game["price"]

    # Estimate remaining tickets from remaining winning tickets × overall odds
    remaining_winners = sum(t["remaining_prizes"] for t in tiers)
    est_remaining_tickets = remaining_winners * odds

    if est_remaining_tickets <= 0:
        if close:
            conn.close()
        return None

    # EV = sum(prize × remaining / est_remaining_tickets)
    ev = sum(t["prize_value"] * t["remaining_prizes"] / est_remaining_tickets for t in tiers)

    if close:
        conn.close()
    return round(ev, 4)


def calculate_all_ev():
    """Calculate and store EV for all games."""
    conn = get_conn()
    games = conn.execute("SELECT id FROM games WHERE overall_odds IS NOT NULL").fetchall()
    today = date.today().isoformat()
    count = 0

    for g in games:
        ev = calculate_ev(g["id"], conn)
        if ev is not None:
            conn.execute(
                """INSERT INTO ev_snapshots (game_id, ev_value, snapshot_date)
                   VALUES (?, ?, ?)
                   ON CONFLICT DO NOTHING""",
                (g["id"], ev, today),
            )
            count += 1

    conn.commit()
    conn.close()
    print(f"Calculated EV for {count} games")
    return count


if __name__ == "__main__":
    calculate_all_ev()
