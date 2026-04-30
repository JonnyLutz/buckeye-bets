# Implementation Plan

- [x] 1. Write bug condition exploration test
  - **Property 1: Bug Condition** - No Recurring Refresh After Startup
  - **CRITICAL**: This test MUST FAIL on unfixed code - failure confirms the bug exists
  - **DO NOT attempt to fix the test or the code when it fails**
  - **NOTE**: This test encodes the expected behavior - it will validate the fix when it passes after implementation
  - **GOAL**: Surface counterexamples that demonstrate the bug exists
  - **Scoped PBT Approach**: Scope the property to the concrete failing case: server running past a calendar-day boundary with no scheduler registered
  - Test that after the FastAPI app starts (triggering `startup()`), there is no background scheduler or recurring job registered on the app
  - Assert that for any server state where `uptime_days >= 1 AND last_refresh_date < today`, no automatic refresh is triggered (from Bug Condition `isBugCondition` in design)
  - Specifically: boot the app using the TestClient, verify no `scheduler` attribute exists on `app.state`, and confirm no APScheduler `BackgroundScheduler` instance is running
  - Generate random `uptime_days` (1..30) and confirm no scheduled refresh fires for any of them
  - Run test on UNFIXED code
  - **EXPECTED OUTCOME**: Test FAILS (this is correct - it proves the bug exists: no scheduler means no daily refresh)
  - Document counterexamples found (e.g., "After 1+ days uptime, app has no scheduler and no mechanism to trigger refresh")
  - Mark task complete when test is written, run, and failure is documented
  - _Requirements: 1.1, 1.2, 1.3_

- [x] 2. Write preservation property tests (BEFORE implementing fix)
  - **Property 2: Preservation** - Existing API and Startup Behavior Unchanged
  - **IMPORTANT**: Follow observation-first methodology
  - **Step 1 - Observe startup refresh**: Boot the unfixed app, confirm that when no EV snapshots exist for today the startup handler calls `run_scrape()`, `run_prize_scrape()`, and `calculate_all_ev()`
  - **Step 2 - Observe manual scrape endpoints**: Call `POST /api/scratchoff/scrape` and `POST /api/scratchoff/scrape-prizes` on unfixed code, record response shapes (`{"scraped": N}` and `{"games_with_prizes": N, "ev_calculated": N}`)
  - **Step 3 - Observe game data endpoints**: Call `GET /api/scratchoff/games` with various query params (price, sort, order), `GET /api/scratchoff/games/{game_number}`, and `GET /api/scratchoff/best` on unfixed code, record response structures
  - **Step 4 - Observe error resilience**: Mock the refresh pipeline to raise an exception during startup, confirm the server still starts and serves cached data
  - Write property-based tests:
    - For all valid combinations of query parameters (price in [None, 1, 2, 3, 5, 10, 20, 30], sort in allowed_sorts, order in ["asc", "desc"]), the games endpoint returns a list of dicts with consistent keys
    - For all manual scrape calls, response contains expected keys with integer values
    - For all exception types raised during refresh, the server continues running
  - Verify all tests PASS on UNFIXED code
  - **EXPECTED OUTCOME**: Tests PASS (this confirms baseline behavior to preserve)
  - Mark task complete when tests are written, run, and passing on unfixed code
  - _Requirements: 3.1, 3.2, 3.3, 3.4_

- [x] 3. Implement scheduled data refresh fix

  - [x] 3.1 Add APScheduler dependency to requirements files
    - Append `APScheduler==3.10.4` to root `requirements.txt`
    - Append `APScheduler==3.10.4` to `backend/requirements.txt`
    - _Requirements: 2.1, 2.2_

  - [x] 3.2 Refactor `backend/api/main.py` to use lifespan with APScheduler
    - Add imports: `from contextlib import asynccontextmanager`, `from apscheduler.schedulers.background import BackgroundScheduler`, `from apscheduler.triggers.cron import CronTrigger`
    - Extract refresh logic into a standalone `_run_refresh()` function that calls `run_scrape()`, `run_prize_scrape()`, `calculate_all_ev()` wrapped in try/except (log errors, never crash)
    - Create `lifespan` async context manager that: calls `init_db()`, runs startup stale-data check via `_run_refresh()`, creates and starts a `BackgroundScheduler` with a daily cron job (e.g., 6:00 AM UTC) calling `_run_refresh()`, stores scheduler on `app.state`, yields, then shuts down the scheduler on exit
    - Change `FastAPI(title="BuckeyeBets")` to `FastAPI(title="BuckeyeBets", lifespan=lifespan)`
    - Remove the `@app.on_event("startup")` decorated `startup()` function entirely
    - _Bug_Condition: isBugCondition(state) where state.uptime_days >= 1 AND state.last_refresh_date < state.today AND NOT schedulerExists(state)_
    - _Expected_Behavior: APScheduler BackgroundScheduler registered with daily CronTrigger calling _run_refresh(), ensuring fresh EV snapshots each day_
    - _Preservation: Startup refresh, manual scrape endpoints, game data APIs, and error resilience remain unchanged_
    - _Requirements: 1.1, 1.2, 1.3, 2.1, 2.2, 2.3, 3.1, 3.2, 3.3, 3.4_

  - [x] 3.3 Verify bug condition exploration test now passes
    - **Property 1: Expected Behavior** - Daily Scheduled Refresh Executes
    - **IMPORTANT**: Re-run the SAME test from task 1 - do NOT write a new test
    - The test from task 1 encodes the expected behavior (scheduler exists and has a daily cron job)
    - When this test passes, it confirms the expected behavior is satisfied
    - Run bug condition exploration test from step 1
    - **EXPECTED OUTCOME**: Test PASSES (confirms bug is fixed - scheduler is now registered)
    - _Requirements: 2.1, 2.2, 2.3_

  - [x] 3.4 Verify preservation tests still pass
    - **Property 2: Preservation** - Existing API and Startup Behavior Unchanged
    - **IMPORTANT**: Re-run the SAME tests from task 2 - do NOT write new tests
    - Run preservation property tests from step 2
    - **EXPECTED OUTCOME**: Tests PASS (confirms no regressions)
    - Confirm all tests still pass after fix (no regressions)
    - _Requirements: 3.1, 3.2, 3.3, 3.4_

- [x] 4. Checkpoint - Ensure all tests pass
  - Run the full test suite (exploration + preservation tests)
  - Verify all tests pass on the fixed codebase
  - Ensure no regressions in API behavior, startup logic, or error handling
  - Ask the user if questions arise
