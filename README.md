# 🎰 BuckeyeBets

Find the best Ohio Lottery scratch-off tickets using math, not luck.

Scrapes live data from the Ohio Lottery, calculates **expected value (EV)** for every active game, and ranks them so you can see which tickets give you the most bang for your buck.

## Features

- **EV per game** — see exactly how much you'd get back on average per ticket
- **Return %** — compare value across price points ($1–$50)
- **Tier ratings** — 🔥 HOT, 💎 SOLID, 😐 MEH, 🧊 COLD at a glance
- **Today's Best Bets** — top 3 games highlighted with podium cards
- **Prize tier breakdown** — click any game to see remaining prizes at every level
- **Auto-refresh** — data updates from the Ohio Lottery API on each server start

## Quick Start

```bash
# Backend
cd backend
pip install -r requirements.txt
cd ..
uvicorn backend.api.main:app --reload

# Frontend (separate terminal)
cd frontend
npm install
npm run dev
```

Open http://localhost:5173

## How It Works

1. **Scrapes** game list from lottery.net and prize tier data from the Ohio Lottery API
2. **Calculates EV** using: `EV = Σ(prize_value × remaining_prizes / estimated_remaining_tickets)`
3. **Ranks games** by return percentage (EV ÷ ticket price)
4. Data refreshes automatically on API startup if today's data hasn't been fetched yet

## Tech Stack

- **Backend:** Python, FastAPI, SQLite, BeautifulSoup
- **Frontend:** React, Vite
- **Data source:** Ohio Lottery public API + lottery.net
