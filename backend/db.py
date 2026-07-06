"""SQLite schema + access helpers (ESPN data source)."""
from __future__ import annotations

import json
import os
import sqlite3
from typing import Any, Dict, List, Optional

import config

# ESPN byathlete per-game keys -> our player_seasons columns.
# (technicalFouls / flagrantFouls are season totals -> converted to per-game on ingest.)
ESPN_STAT_MAP = {
    "gamesPlayed": "gp", "avgMinutes": "mpg",
    "avgPoints": "pts", "avgRebounds": "reb", "avgAssists": "ast",
    "avgSteals": "stl", "avgBlocks": "blk", "avgTurnovers": "tov",
    "avgFieldGoalsMade": "fgm", "avgFieldGoalsAttempted": "fga",
    "avgThreePointFieldGoalsMade": "fg3m",
    "avgThreePointFieldGoalsAttempted": "fg3a",
    "avgFreeThrowsMade": "ftm", "avgFreeThrowsAttempted": "fta",
    "fieldGoalPct": "fg_pct", "threePointFieldGoalPct": "fg3_pct", "freeThrowPct": "ft_pct",
    "doubleDouble": "dd", "tripleDouble": "td",
}
SEASON_NUMERIC_COLS = list(ESPN_STAT_MAP.values()) + ["tech", "flag"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS teams (
    id_team TEXT PRIMARY KEY,
    name TEXT, abbr TEXT, location TEXT, color TEXT, logo TEXT
);

CREATE TABLE IF NOT EXISTS players (
    id_player TEXT PRIMARY KEY,       -- ESPN athlete id
    name TEXT, id_team TEXT, team_name TEXT, team_abbr TEXT,
    position TEXT, date_born TEXT, age_espn REAL,
    height TEXT, weight TEXT, college TEXT, jersey TEXT,
    experience INTEGER, debut_year INTEGER,
    injury_status TEXT, status TEXT, headshot TEXT,
    draft_pick INTEGER, draft_year INTEGER
);

CREATE TABLE IF NOT EXISTS player_seasons (
    id_player TEXT, season TEXT, team TEXT,
    gp REAL, mpg REAL,
    pts REAL, reb REAL, ast REAL, stl REAL, blk REAL, tov REAL,
    fgm REAL, fga REAL, fg3m REAL, fg3a REAL, ftm REAL, fta REAL,
    fg_pct REAL, fg3_pct REAL, ft_pct REAL,
    tech REAL, flag REAL, dd REAL, td REAL,
    fpg REAL,
    PRIMARY KEY (id_player, season)
);

CREATE TABLE IF NOT EXISTS overrides (
    id_player TEXT PRIMARY KEY,
    prospect_tier TEXT, proj_fpg REAL, injury_risk TEXT,
    role_adj REAL DEFAULT 0, manual_value REAL, notes TEXT,
    drafted INTEGER DEFAULT 0, draft_price REAL, draft_owner TEXT,
    updated_at TEXT
);

CREATE TABLE IF NOT EXISTS projections (
    id_player TEXT PRIMARY KEY,
    adp_dynasty REAL, proj_fpg REAL, injury_status TEXT, sleeper_pos TEXT, elig_pos TEXT, sleeper_pid TEXT,
    pts REAL, reb REAL, ast REAL, stl REAL, blk REAL, tov REAL,
    fgm REAL, fga REAL, ftm REAL, fta REAL, fg3m REAL, fg3a REAL,
    dreb REAL, dd REAL, td REAL
);

CREATE TABLE IF NOT EXISTS config (
    id INTEGER PRIMARY KEY CHECK (id = 1), data TEXT
);

CREATE TABLE IF NOT EXISTS depth_chart (
    id_team TEXT NOT NULL, pos TEXT NOT NULL, depth INTEGER NOT NULL,
    id_player TEXT NOT NULL,
    PRIMARY KEY (id_team, pos, depth)
);

CREATE INDEX IF NOT EXISTS idx_seasons_player ON player_seasons(id_player);
"""

PROJ_COLS = ["pts", "reb", "ast", "stl", "blk", "tov", "fgm", "fga", "ftm", "fta",
             "fg3m", "fg3a", "dreb", "dd", "td"]


def connect() -> sqlite3.Connection:
    if config.READONLY:
        # Immutable read-only open: no lock/WAL files, safe on a read-only FS.
        conn = sqlite3.connect("file:{}?mode=ro&immutable=1".format(config.DB_PATH), uri=True)
    else:
        os.makedirs(config.DATA_DIR, exist_ok=True)
        conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    if conn.execute("SELECT 1 FROM config WHERE id=1").fetchone() is None:
        conn.execute("INSERT INTO config (id, data) VALUES (1, ?)", (json.dumps(config.DEFAULT_CONFIG),))
    conn.commit()


def to_float(v: Any) -> Optional[float]:
    if v is None:
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


# --- config ---------------------------------------------------------------

def get_config(conn: sqlite3.Connection) -> Dict[str, Any]:
    row = conn.execute("SELECT data FROM config WHERE id=1").fetchone()
    cfg = dict(config.DEFAULT_CONFIG)
    if row and row["data"]:
        cfg.update(json.loads(row["data"]))
    return cfg


def set_config(conn: sqlite3.Connection, cfg: Dict[str, Any]) -> None:
    conn.execute("UPDATE config SET data=? WHERE id=1", (json.dumps(cfg),))
    conn.commit()


# --- upserts ---------------------------------------------------------------

def upsert_team(conn: sqlite3.Connection, t: Dict[str, Any]) -> None:
    conn.execute(
        """INSERT INTO teams (id_team, name, abbr, location, color, logo)
           VALUES (?,?,?,?,?,?)
           ON CONFLICT(id_team) DO UPDATE SET name=excluded.name, abbr=excluded.abbr,
               location=excluded.location, color=excluded.color, logo=excluded.logo""",
        (str(t["id"]), t.get("name"), t.get("abbr"), t.get("location"), t.get("color"), t.get("logo")),
    )


def upsert_player(conn: sqlite3.Connection, p: Dict[str, Any]) -> None:
    cols = ["id_player", "name", "id_team", "team_name", "team_abbr", "position", "date_born",
            "age_espn", "height", "weight", "college", "jersey", "experience", "debut_year",
            "injury_status", "status", "headshot"]
    vals = [p.get(c) for c in cols]
    ph = ",".join(["?"] * len(cols))
    upd = ",".join("{c}=excluded.{c}".format(c=c) for c in cols if c != "id_player")
    conn.execute("INSERT INTO players ({}) VALUES ({}) ON CONFLICT(id_player) DO UPDATE SET {}".format(
        ",".join(cols), ph, upd), vals)


def upsert_player_season(conn: sqlite3.Connection, id_player: str, season: str, team: str,
                         stats: Dict[str, Any], fpg: float) -> None:
    cols = ["id_player", "season", "team"] + SEASON_NUMERIC_COLS + ["fpg"]
    vals: List[Any] = [id_player, season, team] + [stats.get(c) for c in SEASON_NUMERIC_COLS] + [fpg]
    ph = ",".join(["?"] * len(cols))
    upd = ",".join("{c}=excluded.{c}".format(c=c) for c in cols if c not in ("id_player", "season"))
    conn.execute("INSERT INTO player_seasons ({}) VALUES ({}) "
                 "ON CONFLICT(id_player, season) DO UPDATE SET {}".format(",".join(cols), ph, upd), vals)


# --- overrides -------------------------------------------------------------

_OVR_DEFAULT = {"prospect_tier": "", "proj_fpg": None, "injury_risk": "", "role_adj": 0.0,
                "manual_value": None, "notes": "", "drafted": 0, "draft_price": None, "draft_owner": None}


def get_override(conn: sqlite3.Connection, id_player: str) -> Dict[str, Any]:
    row = conn.execute("SELECT * FROM overrides WHERE id_player=?", (id_player,)).fetchone()
    if row is None:
        return dict(_OVR_DEFAULT, id_player=id_player)
    return dict(row)


def set_override(conn: sqlite3.Connection, id_player: str, data: Dict[str, Any]) -> None:
    import datetime
    cur = get_override(conn, id_player)
    cur.update({k: v for k, v in data.items() if k != "id_player"})
    conn.execute(
        """INSERT INTO overrides (id_player, prospect_tier, proj_fpg, injury_risk, role_adj,
               manual_value, notes, drafted, draft_price, draft_owner, updated_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(id_player) DO UPDATE SET prospect_tier=excluded.prospect_tier,
               proj_fpg=excluded.proj_fpg, injury_risk=excluded.injury_risk, role_adj=excluded.role_adj,
               manual_value=excluded.manual_value, notes=excluded.notes, drafted=excluded.drafted,
               draft_price=excluded.draft_price, draft_owner=excluded.draft_owner,
               updated_at=excluded.updated_at""",
        (id_player, cur.get("prospect_tier", ""), cur.get("proj_fpg"), cur.get("injury_risk", ""),
         cur.get("role_adj", 0.0) or 0.0, cur.get("manual_value"), cur.get("notes", ""),
         int(cur.get("drafted", 0) or 0), cur.get("draft_price"), cur.get("draft_owner"),
         datetime.datetime.utcnow().isoformat()),
    )
    conn.commit()


def all_overrides(conn: sqlite3.Connection) -> Dict[str, Dict[str, Any]]:
    return {r["id_player"]: dict(r) for r in conn.execute("SELECT * FROM overrides").fetchall()}


# --- projections (Sleeper) -------------------------------------------------

def upsert_projection(conn: sqlite3.Connection, id_player: str, proj: Dict[str, Any]) -> None:
    cols = ["id_player", "adp_dynasty", "proj_fpg", "injury_status", "sleeper_pos", "elig_pos", "sleeper_pid"] + PROJ_COLS
    stats = proj.get("stats") or {}
    elig = ",".join(proj.get("fantasy_positions") or ([] if not proj.get("position") else [proj["position"]]))
    vals = [id_player, proj.get("adp_dynasty"), proj.get("proj_fpg"),
            proj.get("injury_status"), proj.get("position"), elig, proj.get("sleeper_pid")]
    vals += [stats.get(c) for c in PROJ_COLS]
    ph = ",".join(["?"] * len(cols))
    upd = ",".join("{c}=excluded.{c}".format(c=c) for c in cols if c != "id_player")
    conn.execute("INSERT INTO projections ({}) VALUES ({}) ON CONFLICT(id_player) DO UPDATE SET {}".format(
        ",".join(cols), ph, upd), vals)


def all_projections(conn: sqlite3.Connection) -> Dict[str, Dict[str, Any]]:
    return {r["id_player"]: dict(r) for r in conn.execute("SELECT * FROM projections").fetchall()}
