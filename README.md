# NFL Team Stats (static site)

- `update_data.py` – fetches ESPN public JSON (teams, schedules, box scores of every FINAL regular-season game), computes points/yards/rush yards/pass yards per game for and against, ranks all 32 teams, cross-checks vs ESPN team season stats, writes `data.json`. Stdlib only.
- Win rates: `update_data.py` also scrapes ESPN Analytics' team win-rate table (PBWR, RBWR, PRWR, RSWR; NFL Next Gen Stats tracking data) from ESPN's "<season> NFL pass rush, run stop, blocking win rate rankings" article (found via ESPN's search API; ESPN updates it weekly, usually Tue). Values/ranks are ESPN's as published, with ESPN's "Last updated" note stored in `data.json` → `win_rates`. If that fetch fails, the previous win-rate data is carried forward (marked stale) and the rest of the refresh still succeeds.
- `index.html`, `style.css`, `app.js` – static front end rendering `data.json`.

Refresh weekly:

    python3 update_data.py          # current season (or --season 2027)
    python3 -m http.server 8765     # then open http://localhost:8765/

Deep links: `#ppg`, `#ypg`, `#papg`, `#yapg`, `#rypg`, `#pypg`, `#ryapg`, `#pyapg`, `#pbwr`, `#rbwr`, `#prwr`, `#rswr`, optionally with expanded teams e.g. `#ppg/BUF,KC`.
