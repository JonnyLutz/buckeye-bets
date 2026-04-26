#!/usr/bin/env python3
"""Daily data refresh: scrape games, fetch prize tiers, calculate EV."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from backend.scrapers.scratchoff import run as scrape_games
from backend.scrapers.prizes import run as scrape_prizes
from backend.ev import calculate_all_ev

if __name__ == "__main__":
    scrape_games()
    scrape_prizes()
    calculate_all_ev()
