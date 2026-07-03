"""Ingest NBA data from ESPN into SQLite.

    python ingest.py            # teams -> rosters(bios) -> season stats -> seed draft
    python ingest.py --force    # bypass HTTP cache

Universe = current NBA rosters (bios + team). Stats joined by ESPN athlete id
across SEASON_YEARS. Resumable via the on-disk cache in data/cache/.
"""
from __future__ import annotations

import sys
import time
import unicodedata
from typing import Any, Dict, List

import config
import db
import espn
from db import ESPN_STAT_MAP
from scoring import season_fp


def norm_name(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.lower().strip()


def bio_from_athlete(a: Dict[str, Any], team: Dict[str, Any]) -> Dict[str, Any]:
    inj = a.get("injuries") or []
    injury = ""
    if inj:
        injury = (inj[0].get("status") or (inj[0].get("type") or {}).get("description") or "")
    return {
        "id_player": str(a.get("id")),
        "name": a.get("displayName"),
        "id_team": str(team["id"]), "team_name": team.get("name"), "team_abbr": team.get("abbr"),
        "position": (a.get("position") or {}).get("abbreviation"),
        "date_born": (a.get("dateOfBirth") or "")[:10] or None,
        "age_espn": a.get("age"),
        "height": a.get("displayHeight"), "weight": a.get("displayWeight"),
        "college": (a.get("college") or {}).get("name"),
        "jersey": a.get("jersey"),
        "experience": (a.get("experience") or {}).get("years"),
        "debut_year": a.get("debutYear"),
        "injury_status": injury,
        "status": (a.get("status") or {}).get("type"),
        "headshot": (a.get("headshot") or {}).get("href"),
    }


def season_row(flat: Dict[str, Any]) -> Dict[str, Any]:
    row: Dict[str, Any] = {}
    for espn_key, col in ESPN_STAT_MAP.items():
        v = flat.get(espn_key)
        if col in ("fg_pct", "fg3_pct", "ft_pct") and v is not None:
            v = v / 100.0            # ESPN gives 47.5 -> store 0.475
        row[col] = v
    gp = flat.get("gamesPlayed") or 0
    row["tech"] = (flat.get("technicalFouls") or 0) / gp if gp else 0.0
    row["flag"] = (flat.get("flagrantFouls") or 0) / gp if gp else 0.0
    return row


def main() -> None:
    force = "--force" in sys.argv
    start = time.time()
    conn = db.connect()
    db.init_schema(conn)

    print("== ESPN teams ==")
    teams = espn.get_teams()
    for t in teams:
        db.upsert_team(conn, t)
    conn.commit()
    print("teams:", len(teams))

    print("== rosters (bios) ==")
    players: List[str] = []
    id_to_team: Dict[str, Dict[str, Any]] = {}
    for i, t in enumerate(teams, 1):
        roster = espn.get_roster(t["id"])
        for a in roster:
            bio = bio_from_athlete(a, t)
            db.upsert_player(conn, bio)
            players.append(bio["id_player"])
            id_to_team[bio["id_player"]] = t
        conn.commit()
        print("  [{}/{}] {}: {}".format(i, len(teams), t["abbr"], len(roster)))
    players = list(dict.fromkeys(players))
    print("total players:", len(players))

    print("== season stats ==")
    w = config.SCORING_WEIGHTS
    player_set = set(players)
    for yr in config.SEASON_YEARS:
        label = espn.season_label(yr)
        stats = espn.get_season_stats(yr, use_cache=not force)
        n = 0
        for aid, flat in stats.items():
            if aid not in player_set:
                continue
            row = season_row(flat)
            if not row.get("gp"):
                continue
            fpg = season_fp(row, w)
            team = (id_to_team.get(aid) or {}).get("abbr")
            db.upsert_player_season(conn, aid, label, team, row, round(fpg, 2))
            n += 1
        conn.commit()
        print("  {}: {} players".format(label, n))

    print("== 2025-26 playoff stats (momentum signal) ==")
    po = espn.get_season_stats(2026, use_cache=not force, seasontype=3)
    n_po = 0
    for aid, flat in po.items():
        if aid not in player_set:
            continue
        row = season_row(flat)
        if not row.get("gp"):
            continue
        db.upsert_playoffs(conn, aid, "2025-26", row["gp"], round(season_fp(row, w), 2))
        n_po += 1
    conn.commit()
    print("  playoff lines stored: {}".format(n_po))

    print("== draft slots (rookie model + curve calibration) ==")
    import sleeper as _sl
    name_to_pid = {_sl.norm_name(r["name"]): r["id_player"]
                   for r in conn.execute("SELECT id_player, name FROM players").fetchall()}
    n_dp = 0
    for yr in (2024, 2025, 2026):
        for nm, pick in espn.get_draft_picks(yr, use_cache=not force).items():
            pid = name_to_pid.get(_sl.norm_name(nm))
            if pid:
                conn.execute("UPDATE players SET draft_pick=?, draft_year=? WHERE id_player=?",
                             (pick, yr, pid))
                n_dp += 1
    conn.commit()
    print("  draft slots mapped: {}".format(n_dp))

    print("== seed draft results ==")
    name_index: Dict[str, str] = {}
    for r in conn.execute("SELECT id_player, name FROM players").fetchall():
        name_index[norm_name(r["name"])] = r["id_player"]
    seeded = 0
    for d in config.DRAFT_RESULTS:
        pid = name_index.get(norm_name(d["name"]))
        if pid:
            db.set_override(conn, pid, {"drafted": 1, "draft_price": d["price"], "draft_owner": d["owner"]})
            seeded += 1
        else:
            print("  ! draft name not matched:", d["name"])
    print("  seeded {}/{} drafted players".format(seeded, len(config.DRAFT_RESULTS)))

    print("== Sleeper 2026-27 projections + dynasty ADP ==")
    import sleeper
    projs = sleeper.load_projections(config.SCORING_WEIGHTS, use_cache=not force)
    espn_idx = {sleeper.norm_name(r["name"]): r["id_player"]
                for r in conn.execute("SELECT id_player, name FROM players").fetchall()}
    matched = 0
    unmatched = []
    for key, proj in projs.items():
        pid = espn_idx.get(key)
        if pid:
            db.upsert_projection(conn, pid, proj)
            matched += 1
        else:
            unmatched.append(proj)
    conn.commit()
    print("  matched {}/{} projections to rostered players".format(matched, len(projs)))

    # ESPN's team rosters miss anyone without a team (free agents like LeBron in
    # July 2026). Create player rows from Sleeper for every unmatched player with
    # a real projection, so the whole draftable universe is on the board.
    meta = sleeper.fetch_players_meta(use_cache=not force)
    added = 0
    for proj in unmatched:
        if not (proj.get("proj_fpg") or 0) > 0:
            continue  # skip the G-league/zero-projection tail
        spid = str(proj.get("sleeper_pid") or "")
        if not spid:
            continue
        m = meta.get(spid) or {}
        db.upsert_player(conn, {
            "id_player": "sl" + spid,
            "name": proj["name"],
            "id_team": None,
            "team_name": m.get("team") or proj.get("team") or "Free Agent",
            "team_abbr": m.get("team") or proj.get("team") or "FA",
            "position": proj.get("position"),
            "date_born": m.get("birth_date"),
            "age_espn": m.get("age"),
            "height": m.get("height"), "weight": m.get("weight"),
            "college": m.get("college"), "jersey": m.get("number"),
            "experience": proj.get("years_exp"),
            "debut_year": None,
            "injury_status": proj.get("injury_status") or "",
            "status": "FA",
            "headshot": "https://sleepercdn.com/content/nba/players/{}.jpg".format(spid),
        })
        db.upsert_projection(conn, "sl" + spid, proj)
        added += 1
    conn.commit()
    print("  added {} Sleeper-only players (free agents etc.)".format(added))

    np = conn.execute("SELECT COUNT(*) FROM players").fetchone()[0]
    ws = conn.execute("SELECT COUNT(DISTINCT id_player) FROM player_seasons").fetchone()[0]
    conn.close()
    print("\nDone in {:.0f}s — {} players, {} with stats.".format(time.time() - start, np, ws))


if __name__ == "__main__":
    main()
