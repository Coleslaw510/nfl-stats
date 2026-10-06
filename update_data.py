#!/usr/bin/env python3
"""Fetch current NFL regular-season team data from ESPN's public JSON APIs and
write data.json for the static site.

Rerunnable: just run `python3 update_data.py` (optionally `--season 2027`).
Stdlib only.

Method
------
* Teams:     site.api.espn.com/apis/site/v2/sports/football/nfl/teams
* Schedules: site.api.espn.com/.../teams/{id}/schedule?season=YYYY&seasontype=2
* Box scores for every FINAL game: site.api.espn.com/.../summary?event={id}
  -> points (final score) and total net yards (box-score "totalYards") for
     both teams, so offense AND defense (allowed) numbers come from the same
     game-level data.
* Cross-check: sports.core.api.espn.com team season statistics
  (totalPointsPerGame, netYardsPerGame) are compared with our computed
  offense numbers; mismatches are reported (stored in data.json too).
Only games with status FINAL are counted. In-progress / scheduled games are
shown on schedules without affecting stats.
"""
import argparse
import datetime as dt
import json
import os
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

SITE = "https://site.api.espn.com/apis/site/v2/sports/football/nfl"
CORE = "https://sports.core.api.espn.com/v2/sports/football/leagues/nfl"
HERE = os.path.dirname(os.path.abspath(__file__))


def get_json(url, retries=4):
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 nfl-stats-site"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:  # network hiccup -> retry with backoff
            last = e
            time.sleep(1.5 * (i + 1))
    raise RuntimeError(f"Failed to fetch {url}: {last}")


def score_of(comp):
    s = comp.get("score")
    if isinstance(s, dict):
        s = s.get("value", s.get("displayValue"))
    try:
        return int(float(s)) if s is not None and s != "" else None
    except (TypeError, ValueError):
        return None


def rank(values, higher_is_better):
    """Competition ranking (1,2,2,4). values: {abbr: float|None}."""
    items = [(k, v) for k, v in values.items() if v is not None]
    items.sort(key=lambda kv: -kv[1] if higher_is_better else kv[1])
    out, prev, prev_rank = {}, None, 0
    for i, (k, v) in enumerate(items, 1):
        r = prev_rank if prev is not None and round(v, 6) == round(prev, 6) else i
        out[k] = r
        prev, prev_rank = v, r
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--season", type=int, default=None, help="season year (default: ESPN current)")
    ap.add_argument("--out", default=os.path.join(HERE, "data.json"))
    args = ap.parse_args()

    # ---- teams --------------------------------------------------------------
    tj = get_json(f"{SITE}/teams")
    league = tj["sports"][0]["leagues"][0]
    season = args.season or int(league["season"]["year"])
    teams = {}
    for t in league["teams"]:
        t = t["team"]
        if not t.get("isActive", True):
            continue
        logo = (t.get("logos") or [{}])[0].get("href")
        teams[t["id"]] = {
            "id": t["id"], "abbr": t["abbreviation"], "name": t["displayName"],
            "short": t.get("shortDisplayName") or t.get("name"),
            "color": "#" + (t.get("color") or "888888"), "logo": logo,
        }
    if len(teams) != 32:
        print(f"WARNING: expected 32 teams, got {len(teams)}", file=sys.stderr)
    print(f"Season {season}: {len(teams)} teams")

    # ---- schedules ------------------------------------------------------------
    def fetch_sched(tid):
        return tid, get_json(f"{SITE}/teams/{tid}/schedule?season={season}&seasontype=2")

    with ThreadPoolExecutor(8) as ex:
        scheds = dict(ex.map(fetch_sched, teams))

    events = {}   # event id -> normalized game
    byes = {}
    for tid, sj in scheds.items():
        rs = sj.get("requestedSeason") or sj.get("season") or {}
        if int(rs.get("year", season)) != season or int(rs.get("type", 2)) != 2:
            print(f"WARNING: schedule for {teams[tid]['abbr']} returned season {rs}", file=sys.stderr)
        byes[tid] = sj.get("byeWeek")
        for e in sj.get("events", []):
            if e["id"] in events:
                continue
            c = e["competitions"][0]
            st = c.get("status", e.get("status", {})).get("type", {})
            g = {"id": e["id"], "week": e.get("week", {}).get("number"), "date": e.get("date"),
                 "neutral": bool(c.get("neutralSite")), "state": st.get("state"),
                 "status": st.get("name"), "completed": bool(st.get("completed")),
                 "detail": st.get("shortDetail") or st.get("detail"), "teams": {}}
            for comp in c["competitors"]:
                g["teams"][comp["team"]["id"]] = {"homeAway": comp.get("homeAway"), "score": score_of(comp)}
            events[e["id"]] = g

    final_ids = [eid for eid, g in events.items()
                 if g["completed"] and g["status"] in ("STATUS_FINAL", "STATUS_FINAL_OVERTIME", "STATUS_FINAL_OT")
                 or (g["completed"] and g["state"] == "post")]
    print(f"{len(events)} games on schedule, {len(final_ids)} final")

    # ---- box scores for finals -----------------------------------------------
    def fetch_box(eid):
        sj = get_json(f"{SITE}/summary?event={eid}")
        yards = {}
        for bt in sj.get("boxscore", {}).get("teams", []):
            for s in bt.get("statistics", []):
                if s.get("name") == "totalYards":
                    try:
                        yards[bt["team"]["id"]] = int(str(s["displayValue"]).replace(",", ""))
                    except ValueError:
                        pass
        # final scores from header too (authoritative for the game)
        for comp in sj.get("header", {}).get("competitions", [{}])[0].get("competitors", []):
            sc = score_of(comp)
            if sc is not None:
                events[eid]["teams"].setdefault(comp["id"], {})["score"] = sc
        return eid, yards

    gaps = []
    with ThreadPoolExecutor(8) as ex:
        for eid, yards in ex.map(fetch_box, final_ids):
            for tid in events[eid]["teams"]:
                y = yards.get(tid)
                events[eid]["teams"][tid]["yards"] = y
                if y is None:
                    gaps.append(f"Missing total yards for team {teams.get(tid, {}).get('abbr', tid)} in event {eid}")

    # ---- aggregate ---------------------------------------------------------------
    agg = {tid: {"gp": 0, "pf": 0, "pa": 0, "yf": 0, "ya": 0, "ygp": 0} for tid in teams}
    for eid in final_ids:
        g = events[eid]
        tids = list(g["teams"])
        if len(tids) != 2:
            continue
        for me, opp in ((tids[0], tids[1]), (tids[1], tids[0])):
            if me not in agg:
                continue
            a, m, o = agg[me], g["teams"][me], g["teams"][opp]
            a["gp"] += 1
            a["pf"] += m["score"] or 0
            a["pa"] += o["score"] or 0
            if m.get("yards") is not None and o.get("yards") is not None:
                a["ygp"] += 1
                a["yf"] += m["yards"]
                a["ya"] += o["yards"]

    def per(n, d):
        return round(n / d, 2) if d else None

    stats = {}
    for tid, a in agg.items():
        stats[tid] = {"gp": a["gp"], "pf": a["pf"], "pa": a["pa"], "yf": a["yf"], "ya": a["ya"],
                      "ppg": per(a["pf"], a["gp"]), "ypg": per(a["yf"], a["ygp"]),
                      "papg": per(a["pa"], a["gp"]), "yapg": per(a["ya"], a["ygp"])}
    ranks = {
        "ppg": rank({t: s["ppg"] for t, s in stats.items()}, True),
        "ypg": rank({t: s["ypg"] for t, s in stats.items()}, True),
        "papg": rank({t: s["papg"] for t, s in stats.items()}, False),
        "yapg": rank({t: s["yapg"] for t, s in stats.items()}, False),
    }

    # ---- cross-check vs ESPN core team stats ----------------------------------
    def fetch_core(tid):
        try:
            j = get_json(f"{CORE}/seasons/{season}/types/2/teams/{tid}/statistics")
        except Exception as e:
            return tid, {"error": str(e)}
        vals = {}
        for cat in j.get("splits", {}).get("categories", []):
            for s in cat.get("stats", []):
                vals.setdefault(s["name"], s.get("value"))
        return tid, {"gp": vals.get("gamesPlayed"), "ppg": vals.get("totalPointsPerGame"),
                     "ypg": vals.get("netYardsPerGame")}

    with ThreadPoolExecutor(8) as ex:
        core = dict(ex.map(fetch_core, teams))
    mismatches, checked = [], 0
    for tid, c in core.items():
        s, ab = stats[tid], teams[tid]["abbr"]
        if "error" in c or c.get("gp") in (None, 0):
            mismatches.append(f"{ab}: core stats unavailable")
            continue
        if int(c["gp"]) != s["gp"]:
            # core stats may lag/lead by a game (e.g. game in progress); note but don't compare
            mismatches.append(f"{ab}: games played differ (box {s['gp']} vs core {int(c['gp'])}) - not compared")
            continue
        checked += 1
        for k in ("ppg", "ypg"):
            if c.get(k) is not None and s[k] is not None and abs(c[k] - s[k]) > 0.05:
                mismatches.append(f"{ab}: {k} box={s[k]} core={round(c[k], 2)}")
    print(f"Cross-check vs ESPN core team stats: {checked} teams compared, {len(mismatches)} notes")
    for m in mismatches:
        print("  -", m)

    # ---- schedules for output --------------------------------------------------
    out_teams = []
    for tid, t in teams.items():
        games = []
        for g in sorted((g for g in events.values() if tid in g["teams"]), key=lambda g: (g["week"] or 0, g["date"] or "")):
            opp = next((o for o in g["teams"] if o != tid), None)
            me, op = g["teams"][tid], g["teams"].get(opp, {})
            row = {"week": g["week"], "date": g["date"], "opp": teams[opp]["abbr"] if opp in teams else None,
                   "home": me.get("homeAway") == "home", "neutral": g["neutral"],
                   "final": g["id"] in final_ids, "state": g["state"], "detail": g["detail"]}
            if row["final"] or g["state"] == "in":
                row["pf"], row["pa"] = me.get("score"), op.get("score")
            if row["final"]:
                pf, pa = row["pf"], row["pa"]
                row["result"] = "W" if pf > pa else "L" if pf < pa else "T"
                row["yf"], row["ya"] = me.get("yards"), op.get("yards")
            games.append(row)
        # Derive bye week(s) from gaps in the week sequence (ESPN's byeWeek field
        # has been seen to be wrong); fall back to byeWeek if no gap is found.
        weeks = {g["week"] for g in games if g["week"]}
        max_wk = max(max(weeks, default=0), 18)
        bye_weeks = [w for w in range(1, max_wk + 1) if w not in weeks] or ([int(byes[tid])] if byes.get(tid) else [])
        if byes.get(tid) and bye_weeks and int(byes[tid]) not in bye_weeks:
            print(f"  note: {t['abbr']} ESPN byeWeek={byes[tid]} but schedule gap is week {bye_weeks}", file=sys.stderr)
        for w in bye_weeks:
            games.append({"week": w, "bye": True})
        if bye_weeks:
            games.sort(key=lambda r: r["week"] or 0)
        out_teams.append({**t, **stats[tid], "rank": {k: ranks[k].get(tid) for k in ranks}, "schedule": games})

    finals = [events[e] for e in final_ids]
    last_week = max((g["week"] for g in finals), default=None)
    pending_in_last = sorted(
        "@".join(teams[x]["abbr"] for x in sorted(g["teams"], key=lambda x: g["teams"][x]["homeAway"] != "away"))
        for g in events.values() if g["week"] == last_week and g["id"] not in final_ids)
    now = dt.datetime.now(dt.timezone.utc)
    data = {
        "season": season,
        "generated_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "through_week": last_week,
        "pending_games_in_week": pending_in_last,
        "games_final": len(final_ids),
        "source": "ESPN public JSON APIs (team schedules + game box scores); cross-checked vs ESPN team season statistics",
        "notes": [
            "Yards = box-score total net yards (passing net of sacks + rushing), the standard NFL definition.",
            "Only final games are counted; per-game values use games played.",
        ],
        "data_gaps": gaps,
        "crosscheck": {"teams_compared": checked, "notes": mismatches},
        "teams": sorted(out_teams, key=lambda t: t["abbr"]),
    }
    tmp = args.out + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f, indent=1)
    os.replace(tmp, args.out)
    print(f"Wrote {args.out}: through week {last_week}, pending {pending_in_last}, gaps={len(gaps)}")
    for k, label in (("ppg", "PPG"), ("ypg", "YPG"), ("papg", "Pts allowed/G"), ("yapg", "Yds allowed/G")):
        top = sorted(out_teams, key=lambda t: t["rank"][k] or 99)[:3]
        print(f"  Top 3 {label}: " + ", ".join(f"{t['abbr']} {t[k]}" for t in top))


if __name__ == "__main__":
    main()
