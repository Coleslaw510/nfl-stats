# NFL Team Stats (static site)

- `update_data.py` – fetches ESPN public JSON (teams, schedules, box scores of every FINAL regular-season game), computes points/yards per game for and against, ranks all 32 teams, cross-checks vs ESPN team season stats, writes `data.json`. Stdlib only.
- `index.html`, `style.css`, `app.js` – static front end rendering `data.json`.

Refresh weekly:

    python3 update_data.py          # current season (or --season 2027)
    python3 -m http.server 8765     # then open http://localhost:8765/

Deep links: `#ppg`, `#ypg`, `#papg`, `#yapg`, optionally with expanded teams e.g. `#ppg/BUF,KC`.
