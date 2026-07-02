"""Sleeper NBA projections client (public endpoint, no auth needed).

Provides 2026-27 per-game projections + dynasty ADP (consensus draft position
across many leagues). We convert the projected per-game stats into a projected
FP/G using the league's exact scoring, and match to ESPN players by name.
"""
from __future__ import annotations

import json
import os
import unicodedata
from typing import Any, Dict, Optional

import requests

import config

PROJ_URL = ("https://api.sleeper.com/projections/nba/{year}?season_type=regular"
            "&position[]=C&position[]=PF&position[]=PG&position[]=SF&position[]=SG"
            "&order_by=adp_dynasty")
CACHE_FILE = os.path.join(config.DATA_DIR, "sleeper_2026.json")


def norm_name(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower().replace(".", "").replace("'", "").replace("-", " ")
    for suf in (" jr", " sr", " iii", " ii", " iv"):
        if s.endswith(suf):
            s = s[: -len(suf)]
    return " ".join(s.split())


def _fetch(year: int, use_cache: bool = True) -> list:
    if use_cache and os.path.exists(CACHE_FILE):
        with open(CACHE_FILE) as fh:
            return json.load(fh)
    r = requests.get(PROJ_URL.format(year=year), headers={"accept": "application/json",
                     "user-agent": "Mozilla/5.0"}, timeout=30)
    r.raise_for_status()
    data = r.json()
    os.makedirs(config.DATA_DIR, exist_ok=True)
    with open(CACHE_FILE, "w") as fh:
        json.dump(data, fh)
    return data


def _proj_fpg(s: Dict[str, Any], w: Dict[str, float]) -> float:
    def n(k):
        try:
            return float(s.get(k) or 0)
        except (TypeError, ValueError):
            return 0.0
    return (w["pts"] * n("pts") + w["reb"] * n("reb") + w["ast"] * n("ast")
            + w["stl"] * n("stl") + w["blk"] * n("blk") + w["tov"] * n("to")
            + w["fgm"] * n("fgm") + w["fg_miss"] * n("fgmi")
            + w["ftm"] * n("ftm") + w["ft_miss"] * n("ftmi")
            + w["fg3m"] * n("tpm"))


# per-game projection fields we keep for the deep dive
PROJ_FIELDS = {"pts": "pts", "reb": "reb", "ast": "ast", "stl": "stl", "blk": "blk",
               "to": "tov", "fgm": "fgm", "fga": "fga", "ftm": "ftm", "fta": "fta",
               "tpm": "fg3m", "tpa": "fg3a", "dreb": "dreb", "dd": "dd", "td": "td"}


def load_projections(weights: Dict[str, float], use_cache: bool = True,
                     year: int = 2026) -> Dict[str, Dict[str, Any]]:
    """Return {normalized_name: {adp_dynasty, proj_fpg, injury_status, stats:{...}}}."""
    raw = _fetch(year, use_cache=use_cache)
    out: Dict[str, Dict[str, Any]] = {}
    for rec in raw:
        p = rec.get("player") or {}
        s = rec.get("stats") or {}
        name = "{} {}".format(p.get("first_name", ""), p.get("last_name", "")).strip()
        if not name:
            continue
        adp = s.get("adp_dynasty")
        fpg = _proj_fpg(s, weights)
        if not fpg and (adp is None):
            continue
        stats = {col: s.get(src) for src, col in PROJ_FIELDS.items()}
        fpos = p.get("fantasy_positions") or []
        out[norm_name(name)] = {
            "name": name, "adp_dynasty": adp, "proj_fpg": round(fpg, 2),
            "injury_status": p.get("injury_status"), "years_exp": p.get("years_exp"),
            "position": p.get("position") or (fpos[0] if fpos else None),
            "fantasy_positions": fpos,
            "sleeper_pid": rec.get("player_id"),
            "team": p.get("team"),
            "stats": stats,
        }
    return out


PLAYERS_META_CACHE = os.path.join(config.DATA_DIR, "cache", "sleeper_players_meta.json")


def fetch_players_meta(use_cache: bool = True) -> Dict[str, Dict[str, Any]]:
    """Sleeper's full NBA players dump (public): pid -> {birth_date, team, ...}.
    Used to backfill birth dates for players ESPN's team rosters miss (free agents)."""
    if use_cache and os.path.exists(PLAYERS_META_CACHE):
        with open(PLAYERS_META_CACHE) as fh:
            return json.load(fh)
    r = requests.get("https://api.sleeper.app/v1/players/nba",
                     headers={"user-agent": "Mozilla/5.0"}, timeout=60)
    r.raise_for_status()
    data = r.json()
    os.makedirs(os.path.dirname(PLAYERS_META_CACHE), exist_ok=True)
    with open(PLAYERS_META_CACHE, "w") as fh:
        json.dump(data, fh)
    return data
