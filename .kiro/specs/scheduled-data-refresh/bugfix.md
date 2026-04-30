# Bugfix Requirements Document

## Introduction

The BuckeyeBets app scrapes Ohio Lottery scratch-off data, calculates expected values, and displays them. The data refresh pipeline (scrape games, scrape prizes, calculate EV) only runs inside the FastAPI `startup()` event handler, which fires once when the server process starts. On Railway, the service runs continuously without restarting, so the startup event never re-fires and data goes stale indefinitely. The fix is to add an in-process background scheduler so the refresh pipeline runs automatically on a daily schedule while the server is running.

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN the FastAPI server has been running continuously for more than one day without a restart THEN the system does not execute the data refresh pipeline, and lottery data (games, prize tiers, EV snapshots) becomes stale

1.2 WHEN Railway keeps the service process alive across calendar days THEN the system has no mechanism to trigger a new data refresh, because the `startup()` event handler only runs once at process start

1.3 WHEN a new calendar day begins while the server is already running THEN the system does not create new EV snapshots for that day, leaving users viewing outdated expected value calculations

### Expected Behavior (Correct)

2.1 WHEN the FastAPI server has been running continuously for more than one day THEN the system SHALL automatically execute the data refresh pipeline (scrape games, scrape prize tiers, calculate EV) on a daily schedule without requiring a server restart

2.2 WHEN a new calendar day begins while the server is running THEN the system SHALL run the refresh pipeline via an in-process background scheduler (e.g., APScheduler) so that fresh EV snapshots are created for the current day

2.3 WHEN the background scheduler triggers a refresh THEN the system SHALL execute the same pipeline as the startup handler: scrape games, scrape prize tiers, and calculate all EV values

### Unchanged Behavior (Regression Prevention)

3.1 WHEN the server starts up and no EV snapshots exist for today THEN the system SHALL CONTINUE TO run the data refresh pipeline immediately during startup, as it does currently

3.2 WHEN a user calls the existing manual scrape endpoints (`POST /api/scratchoff/scrape` and `POST /api/scratchoff/scrape-prizes`) THEN the system SHALL CONTINUE TO execute the scrape pipeline on demand and return results

3.3 WHEN a user queries game data via the API (`GET /api/scratchoff/games`, `GET /api/scratchoff/games/{game_number}`, `GET /api/scratchoff/best`) THEN the system SHALL CONTINUE TO return game data with EV values as before

3.4 WHEN the scheduled refresh encounters an error (e.g., network failure, API unavailability) THEN the system SHALL CONTINUE TO serve the most recently cached data without crashing
