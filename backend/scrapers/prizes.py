"""Scrape prize tier data from the Ohio Lottery public API."""
import requests
from datetime import datetime, timezone
from backend.db.database import get_conn, init_db

API_BASE = "https://api-solutions.ohiolottery.com/1.0"
LOGIN_URL = f"{API_BASE}/Authentication/Login"
PRIZES_URL = f"{API_BASE}/Games/ScratchOffs/ScratchOffGame/GetFullPrizesRemainingList"
CREDS = {"userName": "mobilepublic@mtllc.com", "password": "R7V5Sz8@"}


def get_token() -> str:
    resp = requests.post(LOGIN_URL, json=CREDS, timeout=15)
    resp.raise_for_status()
    return resp.json()["data"]["token"]


def fetch_prizes(token: str) -> list[dict]:
    resp = requests.get(PRIZES_URL, headers={"Authorization": f"Bearer {token}"}, timeout=30)
    resp.raise_for_status()
    return resp.json()["data"]


def save_prizes(games: list[dict]):
    conn = get_conn()
    now = datetime.now(timezone.utc).isoformat()

    for g in games:
        # Upsert game from API data (gameCode maps to game_number)
        row = conn.execute("SELECT id FROM games WHERE game_number = ?", (g["gameCode"],)).fetchone()
        if not row:
            # Game exists in API but not in our DB — insert it
            total_remaining = sum(t["prizesLeft"] for t in g["prizeRemainingValues"])
            conn.execute(
                """INSERT INTO games (game_number, name, price, top_prize, prizes_remaining, scraped_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (g["gameCode"], g["gameName"], g["ticketPrice"],
                 g["prizeRemainingValues"][-1]["description"].strip() if g["prizeRemainingValues"] else "N/A",
                 total_remaining, now),
            )
            row = conn.execute("SELECT id FROM games WHERE game_number = ?", (g["gameCode"],)).fetchone()

        game_id = row["id"]

        # Clear old prize tiers and insert fresh
        conn.execute("DELETE FROM prize_tiers WHERE game_id = ?", (game_id,))
        for t in g["prizeRemainingValues"]:
            conn.execute(
                """INSERT INTO prize_tiers (game_id, prize_value, total_prizes, remaining_prizes, scraped_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (game_id, t["prizeValue"], t["totalPrizes"], t["prizesLeft"], now),
            )

    conn.commit()
    conn.close()


def run():
    init_db()
    token = get_token()
    games = fetch_prizes(token)
    save_prizes(games)
    print(f"Saved prize tiers for {len(games)} games")
    return games


if __name__ == "__main__":
    run()
