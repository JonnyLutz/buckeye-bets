"""
Bug Condition Exploration Test — No Recurring Refresh After Startup

**Validates: Requirements 1.1, 1.2, 1.3**

This test encodes the EXPECTED behavior: the FastAPI app should have an
APScheduler BackgroundScheduler registered on app.state with a daily cron
job that invokes the refresh pipeline.

On the UNFIXED code, this test is EXPECTED TO FAIL because no scheduler
exists — confirming the bug (data goes stale after the first startup refresh).

Bug Condition (from design):
    isBugCondition(state) is true when:
        state.uptime_days >= 1
        AND state.last_refresh_date < state.today
        AND NOT schedulerExists(state)
"""

import pytest
from unittest.mock import patch, MagicMock
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st
from fastapi.testclient import TestClient


@pytest.fixture
def app_client():
    """Boot the FastAPI app with mocked scrapers to avoid real HTTP calls."""
    with patch("backend.api.main.run_scrape", return_value=[]), \
         patch("backend.api.main.run_prize_scrape", return_value=[]), \
         patch("backend.api.main.calculate_all_ev", return_value=0), \
         patch("backend.api.main.init_db"):
        from backend.api.main import app
        with TestClient(app) as client:
            yield client, app


def test_scheduler_exists_on_app_state(app_client):
    """
    After startup, the app SHOULD have a scheduler attribute on app.state.
    On unfixed code, this will FAIL because no scheduler is registered.
    """
    client, app = app_client
    assert hasattr(app.state, "scheduler"), (
        "Bug confirmed: app.state has no 'scheduler' attribute. "
        "No background scheduler is registered, so no daily refresh can fire."
    )


def test_scheduler_is_running(app_client):
    """
    The scheduler SHOULD be actively running so it can fire cron jobs.
    On unfixed code, this will FAIL because no scheduler exists.
    """
    client, app = app_client
    scheduler = getattr(app.state, "scheduler", None)
    assert scheduler is not None, (
        "Bug confirmed: No scheduler instance found on app.state."
    )
    assert scheduler.running, (
        "Bug confirmed: Scheduler exists but is not running."
    )


def test_scheduler_has_daily_cron_job(app_client):
    """
    The scheduler SHOULD have at least one job with a daily cron trigger
    that calls the refresh pipeline.
    On unfixed code, this will FAIL because no scheduler exists.
    """
    client, app = app_client
    scheduler = getattr(app.state, "scheduler", None)
    assert scheduler is not None, (
        "Bug confirmed: No scheduler instance found on app.state."
    )
    jobs = scheduler.get_jobs()
    assert len(jobs) >= 1, (
        "Bug confirmed: Scheduler has no jobs registered. "
        "No daily cron job exists to trigger the refresh pipeline."
    )
    # Verify at least one job has a CronTrigger
    from apscheduler.triggers.cron import CronTrigger
    cron_jobs = [j for j in jobs if isinstance(j.trigger, CronTrigger)]
    assert len(cron_jobs) >= 1, (
        "Bug confirmed: No cron-triggered job found. "
        "The scheduler has no daily cron job for the refresh pipeline."
    )


@given(uptime_days=st.integers(min_value=1, max_value=30))
@settings(
    max_examples=20,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
def test_no_scheduled_refresh_fires_for_any_uptime(app_client, uptime_days):
    """
    **Validates: Requirements 1.1, 1.2, 1.3**

    Property: For any server state where uptime_days >= 1, the app SHOULD
    have a scheduler registered that can trigger a refresh.

    On unfixed code, this will FAIL for every generated uptime_days value
    because no scheduler exists — confirming the bug condition holds for
    all uptime durations >= 1 day.
    """
    client, app = app_client
    # The bug condition: server has been up for uptime_days >= 1
    # Expected behavior: a scheduler should exist and be running
    scheduler = getattr(app.state, "scheduler", None)
    assert scheduler is not None, (
        f"Bug confirmed (uptime_days={uptime_days}): No scheduler exists. "
        f"After {uptime_days} day(s) of uptime, no automatic refresh "
        f"mechanism is available to produce fresh EV snapshots."
    )
    assert scheduler.running, (
        f"Bug confirmed (uptime_days={uptime_days}): Scheduler is not running."
    )
    jobs = scheduler.get_jobs()
    assert len(jobs) >= 1, (
        f"Bug confirmed (uptime_days={uptime_days}): Scheduler has no jobs. "
        f"No daily refresh will fire after {uptime_days} day(s) of uptime."
    )
