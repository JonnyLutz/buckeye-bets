import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from backend.db.database import get_conn, init_db

URL = "https://www.lottery.net/ohio/scratch-offs"


def scrape_games() -> list[dict]:
    resp = requests.get(URL, timeout=15)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    table = soup.select_one("table.scratchOffs")
    rows = table.select("tr:has(td)")
    games = []
    for row in rows:
        cells = row.find_all("td")
        odds_raw = cells[5]["data-order"]
        odds = float(odds_raw) if odds_raw and float(odds_raw) > 0 else None
        games.append({
            "name": cells[0]["data-order"],
            "game_number": cells[1]["data-order"],
            "price": float(cells[2]["data-order"]),
            "top_prize": cells[3]["data-order"],
            "prizes_remaining": int(cells[4]["data-order"]),
            "overall_odds": odds,
        })
    return games


def save_games(games: list[dict]):
    conn = get_conn()
    now = datetime.now(timezone.utc).isoformat()
    for g in games:
        conn.execute(
            """INSERT INTO games (game_number, name, price, top_prize, overall_odds, prizes_remaining, scraped_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(game_number) DO UPDATE SET
                 name=excluded.name, price=excluded.price, top_prize=excluded.top_prize,
                 overall_odds=excluded.overall_odds, prizes_remaining=excluded.prizes_remaining,
                 scraped_at=excluded.scraped_at""",
            (g["game_number"], g["name"], g["price"], g["top_prize"],
             g["overall_odds"], g["prizes_remaining"], now),
        )
    conn.commit()
    conn.close()


def run():
    init_db()
    games = scrape_games()
    save_games(games)
    print(f"Scraped {len(games)} games")
    return games


if __name__ == "__main__":
    run()
