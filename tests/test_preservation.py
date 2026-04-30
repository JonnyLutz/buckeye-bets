"""
Preservation Property Tests — Existing API and Startup Behavior Unchanged

**Validates: Requirements 3.1, 3.2, 3.3, 3.4**

These tests capture the EXISTING behavior of the unfixed code.
They MUST PASS on the unfixed code and continue to pass after the fix,
ensuring no regressions are introduced.

Observation-first methodology:
  Step 1: Observe startup refresh behavior
  Step 2: Observe manual scrape endpoint response shapes
  Step 3: Observe game data endpoint response structures
  Step 4: Observe error resilience during startup
"""

import pytest
from unittest.mock import patch, MagicMock, call
from hypothesis import given, settings, HealthCheck, assume
from hypothesis import strategies as st
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Strategies for property-based tests
# ---------------------------------------------------------------------------

ALLOWED_SORTS = [
    "name", "price", "top_prize", "overall_odds",
    "prizes_remaining", "game_number", "ev_value", "return_pct",
]

price_strategy = st.sampled_from([None, 1, 2, 3, 5, 10, 20, 30])
sort_strategy = st.sampled_from(ALLOWED_SORTS)
order_strategy = st.sampled_from(["asc", "desc"])

exception_strategy = st.sampled_from([
    RuntimeError("Network timeout"),
    ConnectionError("API unreachable"),
    ValueError("Bad response"),
    TimeoutError("Request timed out"),
    OSError("DNS resolution failed"),
])


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_scrape_functions():
    """Patch all scraper/DB functions to avoid real HTTP calls and DB writes."""
    with patch("backend.api.main.run_scrape", return_value=[{"game": 1}, {"game": 2}]) as m_scrape, \
         patch("backend.api.main.run_prize_scrape", return_value=[{"prize": 1}]) as m_prize, \
         patch("backend.api.main.calculate_all_ev", return_value=5) as m_ev, \
         patch("backend.api.main.init_db") as m_init, \
         patch("backend.api.main.get_conn") as m_conn:

        # Set up a mock connection that returns 0 EV snapshots (triggers refresh)
        mock_conn = MagicMock()
        mock_row = {"c": 0}
        mock_conn.execute.return_value.fetchone.return_value = mock_row
        m_conn.return_value = mock_conn

        yield {
            "run_scrape": m_scrape,
            "run_prize_scrape": m_prize,
            "calculate_all_ev": m_ev,
            "init_db": m_init,
            "get_conn": m_conn,
            "mock_conn": mock_conn,
        }


@pytest.fixture
def client_with_mocks(mock_scrape_functions):
    """Create a TestClient with all scrapers mocked."""
    from backend.api.main import app
    with TestClient(app) as client:
        yield client, mock_scrape_functions


@pytest.fixture
def client_with_data():
    """
    Create a TestClient with mocked scrapers but a real shared in-memory DB
    seeded with sample game data, so GET endpoints return meaningful results.
    Uses a shared named in-memory DB so each get_conn() call returns a fresh
    connection to the same database (avoiding "closed database" errors when
    the startup handler closes its connection).
    """
    import sqlite3
    from datetime import date

    DB_URI = "file:test_preservation_db?mode=memory&cache=shared"

    # Create the initial connection that keeps the shared DB alive
    keeper_conn = sqlite3.connect(DB_URI, uri=True, check_same_thread=False)
    keeper_conn.row_factory = sqlite3.Row
    keeper_conn.execute("PRAGMA foreign_keys = ON")

    # Read and execute schema
    from pathlib import Path
    schema_path = Path(__file__).parent.parent / "backend" / "db" / "schema.sql"
    keeper_conn.executescript(schema_path.read_text())

    # Insert sample games
    today = date.today().isoformat()
    sample_games = [
        ("001", "Lucky 7s", 1.0, "$5,000", 10.0, 1000, today),
        ("002", "Big Money", 5.0, "$100,000", 4.5, 500, today),
        ("003", "Gold Rush", 10.0, "$500,000", 3.2, 200, today),
        ("004", "Diamond Dazzle", 20.0, "$1,000,000", 2.8, 100, today),
        ("005", "Quick Cash", 2.0, "$10,000", 8.0, 800, today),
        ("006", "Triple Play", 3.0, "$25,000", 6.0, 600, today),
        ("007", "Mega Millions", 30.0, "$2,000,000", 2.5, 50, today),
    ]
    for g in sample_games:
        keeper_conn.execute(
            """INSERT INTO games (game_number, name, price, top_prize, overall_odds, prizes_remaining, scraped_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            g,
        )

    # Insert prize tiers for each game
    games = keeper_conn.execute("SELECT id, price FROM games").fetchall()
    for game in games:
        game_id = game["id"]
        price = game["price"]
        keeper_conn.execute(
            "INSERT INTO prize_tiers (game_id, prize_value, total_prizes, remaining_prizes, scraped_at) VALUES (?, ?, ?, ?, ?)",
            (game_id, price * 2, 1000, 500, today),
        )
        keeper_conn.execute(
            "INSERT INTO prize_tiers (game_id, prize_value, total_prizes, remaining_prizes, scraped_at) VALUES (?, ?, ?, ?, ?)",
            (game_id, price * 10, 100, 50, today),
        )

    # Insert EV snapshots
    for game in games:
        game_id = game["id"]
        price = game["price"]
        ev_val = round(price * 0.65, 4)  # Simulated EV
        keeper_conn.execute(
            "INSERT INTO ev_snapshots (game_id, ev_value, snapshot_date) VALUES (?, ?, ?)",
            (game_id, ev_val, today),
        )

    keeper_conn.commit()

    def mock_get_conn():
        """Return a new connection to the shared in-memory DB each time."""
        conn = sqlite3.connect(DB_URI, uri=True, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    with patch("backend.api.main.run_scrape", return_value=[{"g": 1}, {"g": 2}]) as m_scrape, \
         patch("backend.api.main.run_prize_scrape", return_value=[{"p": 1}]) as m_prize, \
         patch("backend.api.main.calculate_all_ev", return_value=5) as m_ev, \
         patch("backend.api.main.init_db"), \
         patch("backend.api.main.get_conn", side_effect=mock_get_conn):

        from backend.api.main import app
        with TestClient(app) as client:
            yield client, {
                "run_scrape": m_scrape,
                "run_prize_scrape": m_prize,
                "calculate_all_ev": m_ev,
            }

    keeper_conn.close()


# ===========================================================================
# Step 1: Startup Refresh Preservation
# ===========================================================================

class TestStartupRefreshPreservation:
    """
    **Validates: Requirements 3.1**

    Verify that when no EV snapshots exist for today, the startup handler
    calls run_scrape(), run_prize_scrape(), and calculate_all_ev().
    """

    def test_startup_calls_refresh_pipeline_when_no_snapshots(self, mock_scrape_functions):
        """When no EV snapshots exist for today, startup runs the full pipeline."""
        from backend.api.main import app
        with TestClient(app):
            pass  # startup fires during __enter__

        mock_scrape_functions["init_db"].assert_called()
        mock_scrape_functions["run_scrape"].assert_called_once()
        mock_scrape_functions["run_prize_scrape"].assert_called_once()
        mock_scrape_functions["calculate_all_ev"].assert_called_once()

    def test_startup_skips_refresh_when_snapshots_exist(self):
        """When EV snapshots exist for today, startup does NOT run the pipeline."""
        with patch("backend.api.main.run_scrape") as m_scrape, \
             patch("backend.api.main.run_prize_scrape") as m_prize, \
             patch("backend.api.main.calculate_all_ev") as m_ev, \
             patch("backend.api.main.init_db"), \
             patch("backend.api.main.get_conn") as m_conn:

            mock_conn = MagicMock()
            mock_conn.execute.return_value.fetchone.return_value = {"c": 5}  # snapshots exist
            m_conn.return_value = mock_conn

            from backend.api.main import app
            with TestClient(app):
                pass

            m_scrape.assert_not_called()
            m_prize.assert_not_called()
            m_ev.assert_not_called()


# ===========================================================================
# Step 2: Manual Scrape Endpoint Preservation
# ===========================================================================

class TestManualScrapePreservation:
    """
    **Validates: Requirements 3.2**

    Verify POST /api/scratchoff/scrape and POST /api/scratchoff/scrape-prizes
    return the expected response shapes.
    """

    def test_scrape_endpoint_returns_scraped_count(self, client_with_mocks):
        """POST /api/scratchoff/scrape returns {"scraped": N} with integer value."""
        client, mocks = client_with_mocks
        resp = client.post("/api/scratchoff/scrape")
        assert resp.status_code == 200
        data = resp.json()
        assert "scraped" in data
        assert isinstance(data["scraped"], int)
        assert data["scraped"] == 2  # matches mock return of 2 items

    def test_scrape_prizes_endpoint_returns_expected_shape(self, client_with_mocks):
        """POST /api/scratchoff/scrape-prizes returns {"games_with_prizes": N, "ev_calculated": N}."""
        client, mocks = client_with_mocks
        resp = client.post("/api/scratchoff/scrape-prizes")
        assert resp.status_code == 200
        data = resp.json()
        assert "games_with_prizes" in data
        assert "ev_calculated" in data
        assert isinstance(data["games_with_prizes"], int)
        assert isinstance(data["ev_calculated"], int)

    @given(data=st.data())
    @settings(
        max_examples=10,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_manual_scrape_response_keys_property(self, client_with_mocks, data):
        """
        **Validates: Requirements 3.2**

        Property: For all manual scrape calls, response contains expected keys
        with integer values.
        """
        client, mocks = client_with_mocks
        endpoint = data.draw(st.sampled_from([
            "/api/scratchoff/scrape",
            "/api/scratchoff/scrape-prizes",
        ]))

        resp = client.post(endpoint)
        assert resp.status_code == 200
        result = resp.json()

        if endpoint == "/api/scratchoff/scrape":
            assert "scraped" in result
            assert isinstance(result["scraped"], int)
        else:
            assert "games_with_prizes" in result
            assert "ev_calculated" in result
            assert isinstance(result["games_with_prizes"], int)
            assert isinstance(result["ev_calculated"], int)


# ===========================================================================
# Step 3: Game Data Endpoint Preservation
# ===========================================================================

class TestGameDataPreservation:
    """
    **Validates: Requirements 3.3**

    Verify GET /api/scratchoff/games, GET /api/scratchoff/games/{game_number},
    and GET /api/scratchoff/best return correct response structures.
    """

    def test_games_endpoint_returns_list(self, client_with_data):
        """GET /api/scratchoff/games returns a list of game dicts."""
        client, _ = client_with_data
        resp = client.get("/api/scratchoff/games")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) > 0

    def test_games_endpoint_dict_keys(self, client_with_data):
        """Each game dict has consistent keys including ev_value and return_pct."""
        client, _ = client_with_data
        resp = client.get("/api/scratchoff/games")
        data = resp.json()
        expected_keys = {"id", "game_number", "name", "price", "top_prize",
                         "overall_odds", "prizes_remaining", "scraped_at",
                         "ev_value", "return_pct"}
        for game in data:
            assert expected_keys.issubset(set(game.keys())), (
                f"Missing keys: {expected_keys - set(game.keys())}"
            )

    def test_games_endpoint_price_filter(self, client_with_data):
        """GET /api/scratchoff/games?price=5 returns only games with that price."""
        client, _ = client_with_data
        resp = client.get("/api/scratchoff/games", params={"price": 5})
        assert resp.status_code == 200
        data = resp.json()
        for game in data:
            assert game["price"] == 5.0

    def test_single_game_endpoint(self, client_with_data):
        """GET /api/scratchoff/games/{game_number} returns a single game with prize_tiers and ev_history."""
        client, _ = client_with_data
        resp = client.get("/api/scratchoff/games/001")
        assert resp.status_code == 200
        data = resp.json()
        assert data["game_number"] == "001"
        assert "prize_tiers" in data
        assert "ev_history" in data
        assert isinstance(data["prize_tiers"], list)
        assert isinstance(data["ev_history"], list)

    def test_single_game_not_found(self, client_with_data):
        """GET /api/scratchoff/games/{nonexistent} returns error."""
        client, _ = client_with_data
        resp = client.get("/api/scratchoff/games/999")
        # The unfixed code returns a tuple (dict, 404) but FastAPI serializes it as 200 with the tuple
        # Observe actual behavior
        assert resp.status_code == 200  # FastAPI doesn't auto-set status from tuple

    def test_best_games_endpoint(self, client_with_data):
        """GET /api/scratchoff/best returns a list of games sorted by EV/price."""
        client, _ = client_with_data
        resp = client.get("/api/scratchoff/best")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        # All returned games should have ev_value
        for game in data:
            assert "ev_value" in game
            assert game["ev_value"] is not None

    @given(
        price=price_strategy,
        sort=sort_strategy,
        order=order_strategy,
    )
    @settings(
        max_examples=50,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_games_endpoint_query_params_property(self, client_with_data, price, sort, order):
        """
        **Validates: Requirements 3.3**

        Property: For all valid combinations of query parameters
        (price in [None, 1, 2, 3, 5, 10, 20, 30], sort in allowed_sorts,
        order in ["asc", "desc"]), the games endpoint returns a list of dicts
        with consistent keys.
        """
        client, _ = client_with_data
        params = {"sort": sort, "order": order}
        if price is not None:
            params["price"] = price

        resp = client.get("/api/scratchoff/games", params=params)
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

        expected_keys = {"id", "game_number", "name", "price", "top_prize",
                         "overall_odds", "prizes_remaining", "scraped_at",
                         "ev_value", "return_pct"}

        for game in data:
            assert isinstance(game, dict)
            assert expected_keys.issubset(set(game.keys())), (
                f"Missing keys for sort={sort}, order={order}, price={price}: "
                f"{expected_keys - set(game.keys())}"
            )

        # If price filter is set, all returned games must match
        if price is not None:
            for game in data:
                assert game["price"] == float(price), (
                    f"Price filter {price} not applied: got {game['price']}"
                )


# ===========================================================================
# Step 4: Error Resilience Preservation
# ===========================================================================

class TestErrorResiliencePreservation:
    """
    **Validates: Requirements 3.4**

    Verify that if the refresh pipeline raises an exception during startup,
    the server still starts and serves cached data.
    """

    def test_server_starts_despite_refresh_error(self):
        """If run_scrape() raises during startup, the server still starts."""
        with patch("backend.api.main.run_scrape", side_effect=RuntimeError("Network down")), \
             patch("backend.api.main.run_prize_scrape") as m_prize, \
             patch("backend.api.main.calculate_all_ev") as m_ev, \
             patch("backend.api.main.init_db"), \
             patch("backend.api.main.get_conn") as m_conn:

            mock_conn = MagicMock()
            mock_conn.execute.return_value.fetchone.return_value = {"c": 0}
            m_conn.return_value = mock_conn

            from backend.api.main import app
            # Server should start without crashing
            with TestClient(app) as client:
                # Verify the server is responsive
                resp = client.get("/api/scratchoff/games")
                assert resp.status_code == 200

    @given(exc=exception_strategy)
    @settings(
        max_examples=5,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_server_resilient_to_any_exception_type(self, exc):
        """
        **Validates: Requirements 3.4**

        Property: For all exception types raised during refresh,
        the server continues running.
        """
        with patch("backend.api.main.run_scrape", side_effect=exc), \
             patch("backend.api.main.run_prize_scrape"), \
             patch("backend.api.main.calculate_all_ev"), \
             patch("backend.api.main.init_db"), \
             patch("backend.api.main.get_conn") as m_conn:

            mock_conn = MagicMock()
            mock_conn.execute.return_value.fetchone.return_value = {"c": 0}
            m_conn.return_value = mock_conn

            from backend.api.main import app
            with TestClient(app) as client:
                # Server should be responsive despite the startup error
                resp = client.get("/api/scratchoff/games")
                assert resp.status_code == 200
