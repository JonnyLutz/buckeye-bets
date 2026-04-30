# Scheduled Data Refresh Bugfix Design

## Overview

The BuckeyeBets app's data refresh pipeline (scrape games → scrape prize tiers → calculate EV) only executes inside the FastAPI `startup()` event handler, which fires once when the process starts. On Railway, the service runs continuously without restarting, so data goes stale after the first day. The fix adds an in-process background scheduler using APScheduler so the refresh pipeline runs automatically on a daily cron schedule while the server is alive. The change is confined to `backend/api/main.py` (swap `@app.on_event("startup")` for a `lifespan` context manager that starts/stops the scheduler) and `requirements.txt` (add `APScheduler`).

## Glossary

- **Bug_Condition (C)**: The server has been running continuously for more than one calendar day without a restart, and no new refresh has been triggered since startup.
- **Property (P)**: The refresh pipeline (scrape games, scrape prizes, calculate EV) executes automatically on a daily schedule, producing fresh EV snapshots each day.
- **Preservation**: Existing startup-refresh behavior, manual scrape endpoints, game data API endpoints, and error resilience must remain unchanged by the fix.
- **startup()**: The current `@app.on_event("startup")` handler in `backend/api/main.py` that runs the refresh pipeline once at process start.
- **refresh pipeline**: The sequence: `run_scrape()` → `run_prize_scrape()` → `calculate_all_ev()`, as defined in `refresh.py` and replicated in the startup handler.
- **APScheduler**: Advanced Python Scheduler — a lightweight in-process job scheduling library that supports cron-style triggers.
- **lifespan**: FastAPI's recommended pattern (`@asynccontextmanager` yielded to `FastAPI(lifespan=...)`) for managing startup/shutdown logic, replacing the deprecated `on_event` hooks.

## Bug Details

### Bug Condition

The bug manifests when the FastAPI server has been running continuously across calendar-day boundaries without a process restart. The `startup()` event handler fires exactly once at process start, so no subsequent refresh is ever triggered. On Railway (restart policy `ON_FAILURE`), the process stays alive indefinitely, and data becomes stale.

**Formal Specification:**
```
FUNCTION isBugCondition(state)
  INPUT: state of type ServerState { uptime_days: int, last_refresh_date: date, today: date }
  OUTPUT: boolean

  RETURN state.uptime_days >= 1
         AND state.last_refresh_date < state.today
         AND NOT schedulerExists(state)
END FUNCTION
```

The condition is true whenever the server has been up for at least one full calendar day, the last refresh was on a previous date, and there is no scheduler to trigger a new refresh.

### Examples

- **Example 1**: Server starts Monday 6 AM, runs `startup()`, refreshes data. Tuesday 6 AM arrives — no refresh fires. Users see Monday's EV snapshots all day Tuesday. **Expected**: A scheduled job triggers the pipeline Tuesday morning, creating Tuesday's snapshots.
- **Example 2**: Server starts and Railway keeps it alive for a week. Only Monday's data exists. **Expected**: The scheduler fires daily, producing snapshots for each day.
- **Example 3**: Server restarts due to a crash on Wednesday. `startup()` fires, data refreshes. Thursday arrives — same stale-data problem. **Expected**: The scheduler handles Thursday's refresh automatically.
- **Edge case**: Server starts at 11:59 PM. `startup()` refreshes. At midnight the scheduler fires again for the new day. **Expected**: The `ON CONFLICT DO NOTHING` on `ev_snapshots` prevents duplicates; the scheduler simply produces the new day's snapshot.

## Expected Behavior

### Preservation Requirements

**Unchanged Behaviors:**
- The startup check ("if no EV snapshots for today, run the pipeline") must continue to work so that a fresh deploy or crash-restart still gets immediate data.
- `POST /api/scratchoff/scrape` and `POST /api/scratchoff/scrape-prizes` must continue to trigger on-demand scrapes and return results.
- `GET /api/scratchoff/games`, `GET /api/scratchoff/games/{game_number}`, and `GET /api/scratchoff/best` must continue to return game data with EV values.
- If the scheduled refresh raises an exception (network failure, API down), the server must continue running and serve the most recently cached data.

**Scope:**
All inputs and behaviors that do NOT involve the daily scheduling mechanism should be completely unaffected by this fix. This includes:
- All existing API request/response behavior
- Database schema and query patterns
- Frontend serving via the SPA catch-all route
- Manual scrape endpoint behavior
- Error handling in individual scrapers

## Hypothesized Root Cause

Based on the bug description and code analysis, the root cause is straightforward:

1. **Single-fire startup handler**: `@app.on_event("startup")` in `backend/api/main.py` runs exactly once when the ASGI server boots. There is no recurring mechanism to re-invoke the refresh pipeline.

2. **Railway's restart policy**: `railway.json` sets `restartPolicyType: "ON_FAILURE"`, meaning the process only restarts on crashes, not on a schedule. Combined with (1), the refresh never re-fires during normal operation.

3. **No scheduler or cron job**: The codebase has a standalone `refresh.py` script intended for manual or cron-based execution, but nothing in the deployment configuration invokes it on a schedule. Railway's free/hobby tier does not support cron jobs natively.

4. **Stale-data check is startup-only**: The "if no EV snapshots for today" guard is inside `startup()`, so it only helps on process start, not on subsequent days.

The fix is to introduce APScheduler inside the FastAPI process so the refresh pipeline runs on a daily cron trigger without depending on external cron infrastructure.

## Correctness Properties

Property 1: Bug Condition - Daily Scheduled Refresh Executes

_For any_ server state where the server has been running continuously past a calendar-day boundary (isBugCondition returns true), the fixed application SHALL have an APScheduler job registered with a daily cron trigger that invokes the full refresh pipeline (scrape games, scrape prizes, calculate EV), ensuring fresh EV snapshots are created for the current day.

**Validates: Requirements 2.1, 2.2, 2.3**

Property 2: Preservation - Existing Behavior Unchanged

_For any_ input that is NOT related to the daily scheduling mechanism (API requests, manual scrape triggers, startup refresh, error scenarios), the fixed code SHALL produce exactly the same behavior as the original code, preserving all existing API responses, startup refresh logic, manual scrape functionality, and error resilience.

**Validates: Requirements 3.1, 3.2, 3.3, 3.4**

## Fix Implementation

### Changes Required

Assuming our root cause analysis is correct:

**File**: `requirements.txt` (root-level)

**Change**: Add APScheduler dependency.

**Specific Changes**:
1. **Add dependency**: Append `APScheduler==3.10.4` to `requirements.txt`

---

**File**: `backend/requirements.txt`

**Change**: Mirror the same APScheduler dependency addition.

**Specific Changes**:
1. **Add dependency**: Append `APScheduler==3.10.4` to `backend/requirements.txt`

---

**File**: `backend/api/main.py`

**Function**: Replace `startup()` with a `lifespan` context manager

**Specific Changes**:

1. **Add imports**: Import `asynccontextmanager` from `contextlib`, `BackgroundScheduler` from `apscheduler.schedulers.background`, and `CronTrigger` from `apscheduler.triggers.cron`.

2. **Create refresh helper**: Extract the refresh pipeline into a standalone `_run_refresh()` function that calls `run_scrape()`, `run_prize_scrape()`, and `calculate_all_ev()` wrapped in a try/except so errors are logged but never crash the server.

3. **Create lifespan context manager**: Define an `async def lifespan(app)` context manager that:
   - Calls `init_db()` 
   - Runs the existing "if no snapshots for today" startup check using `_run_refresh()`
   - Creates a `BackgroundScheduler`, adds a cron job for `_run_refresh()` (e.g., daily at 6:00 AM UTC), starts the scheduler
   - Yields (server runs)
   - On shutdown, calls `scheduler.shutdown()`

4. **Wire lifespan to app**: Change `FastAPI(title="BuckeyeBets")` to `FastAPI(title="BuckeyeBets", lifespan=lifespan)`.

5. **Remove old startup handler**: Delete the `@app.on_event("startup")` function entirely, since its logic is now in the lifespan context manager.

## Testing Strategy

### Validation Approach

The testing strategy follows a two-phase approach: first, surface counterexamples that demonstrate the bug on unfixed code, then verify the fix works correctly and preserves existing behavior.

### Exploratory Bug Condition Checking

**Goal**: Surface counterexamples that demonstrate the bug BEFORE implementing the fix. Confirm or refute the root cause analysis. If we refute, we will need to re-hypothesize.

**Test Plan**: Inspect the unfixed `backend/api/main.py` to confirm there is no scheduler or recurring refresh mechanism. Write a test that boots the FastAPI app, mocks the date to advance by one day, and asserts that no new refresh is triggered.

**Test Cases**:
1. **No scheduler exists**: Inspect the app object for any background scheduler — confirm none is registered (will confirm bug on unfixed code)
2. **Startup-only refresh**: Boot the app, verify `startup()` runs the pipeline, then advance the mock date by one day and confirm no second refresh fires (will confirm bug on unfixed code)
3. **No cron job in deployment**: Inspect `railway.json`, `Procfile`, and `nixpacks.toml` for any cron configuration — confirm none exists (will confirm bug on unfixed code)

**Expected Counterexamples**:
- After advancing the date by one day, no refresh pipeline invocation occurs
- The app object has no scheduler attribute or background job registry

### Fix Checking

**Goal**: Verify that for all inputs where the bug condition holds, the fixed function produces the expected behavior.

**Pseudocode:**
```
FOR ALL state WHERE isBugCondition(state) DO
  app := create_fixed_app()
  scheduler := app.state.scheduler
  ASSERT scheduler IS NOT None
  ASSERT scheduler.running == True
  ASSERT len(scheduler.get_jobs()) >= 1
  job := scheduler.get_jobs()[0]
  ASSERT job.trigger matches daily cron
  
  # Simulate trigger
  job.func()
  ASSERT run_scrape was called
  ASSERT run_prize_scrape was called
  ASSERT calculate_all_ev was called
END FOR
```

### Preservation Checking

**Goal**: Verify that for all inputs where the bug condition does NOT hold, the fixed function produces the same result as the original function.

**Pseudocode:**
```
FOR ALL input WHERE NOT isBugCondition(input) DO
  ASSERT fixedApp.handle(input) == originalApp.handle(input)
END FOR
```

**Testing Approach**: Property-based testing is recommended for preservation checking because:
- It generates many combinations of API requests and query parameters automatically
- It catches edge cases in query parameter handling that manual tests might miss
- It provides strong guarantees that API behavior is unchanged for all non-scheduler inputs

**Test Plan**: Observe behavior on UNFIXED code first for API endpoints and manual scrape triggers, then write property-based tests capturing that behavior.

**Test Cases**:
1. **Startup Refresh Preservation**: Verify that when no EV snapshots exist for today, the lifespan handler still runs the pipeline immediately at startup, same as the old `startup()` handler
2. **Manual Scrape Preservation**: Verify `POST /api/scratchoff/scrape` and `POST /api/scratchoff/scrape-prizes` continue to work and return the same response shape
3. **Game Data API Preservation**: Verify `GET /api/scratchoff/games`, `GET /api/scratchoff/games/{game_number}`, and `GET /api/scratchoff/best` return the same data format and query behavior
4. **Error Resilience Preservation**: Verify that if the scheduled refresh raises an exception, the server continues running and cached data is still served

### Unit Tests

- Test that `_run_refresh()` calls `run_scrape()`, `run_prize_scrape()`, and `calculate_all_ev()` in order
- Test that `_run_refresh()` catches exceptions and logs them without re-raising
- Test that the lifespan context manager initializes the DB and runs the startup check
- Test that the scheduler is started during lifespan entry and shut down during lifespan exit

### Property-Based Tests

- Generate random server states (varying uptime, last refresh dates) and verify the scheduler job is always registered and callable
- Generate random API request parameters (price filters, sort columns, order directions) and verify the fixed app returns identical responses to the original app
- Generate random exception types for the refresh pipeline and verify none propagate to crash the server

### Integration Tests

- Boot the full FastAPI app with the lifespan, verify the scheduler is running, trigger the job manually, and confirm fresh EV snapshots are created
- Boot the app, call manual scrape endpoints, and verify they still work alongside the scheduler
- Boot the app with a mocked failing scraper, trigger the scheduled job, and verify the server continues to serve cached data
