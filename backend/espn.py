"""ESPN NBA data client — rate-limited and disk-cached.

ESPN's public endpoints are unauthenticated but expect a browser UA. We cache
every response to data/cache/ so re-runs are instant and resumable.

Season year convention: ESPN uses the ENDING year, e.g. season=2026 is the
2025-26 season. `season_label()` maps it to "2025-26" for display.

Key endpoints:
  teams   : site.api.espn.com/.../basketball/nba/teams
  roster  : site.api.espn.com/.../basketball/nba/teams/{id}/roster   (bios)
  byathlete: site.web.api.espn.com/.../statistics/byathlete?season=Y  (season stats, paginated)
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from typing import Any, Dict, List, Optional

import requests

import config

_last = 0.0
_session = requests.Session()
_session.headers.update({"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                                       "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122 Safari/537.36"})

SITE = "https://site.api.espn.com/apis/site/v2/sports/basketball/nba"
WEB = "https://site.web.api.espn.com/apis/common/v3/sports/basketball/nba"


def season_label(year: int) -> str:
    return "{}-{}".format(year - 1, str(year)[2:])


def _throttle() -> None:
    global _last
    dt = time.time() - _last
    if dt < config.MIN_REQUEST_INTERVAL:
        time.sleep(config.MIN_REQUEST_INTERVAL - dt)
    _last = time.time()


def _cache_path(url: str) -> str:
    os.makedirs(config.CACHE_DIR, exist_ok=True)
    return os.path.join(config.CACHE_DIR, "espn_" + hashlib.sha1(url.encode()).hexdigest() + ".json")


def _get(url: str, use_cache: bool = True, max_retries: int = 4) -> Optional[Any]:
    cf = _cache_path(url)
    if use_cache and os.path.exists(cf):
        with open(cf) as fh:
            return json.load(fh)
    for attempt in range(max_retries):
        _throttle()
        try:
            r = _session.get(url, timeout=30)
        except requests.RequestException:
            time.sleep(1.5 * (attempt + 1)); continue
        if r.status_code == 429:
            time.sleep(3.0 * (attempt + 1)); continue
        if r.status_code != 200:
            time.sleep(1.0 * (attempt + 1)); continue
        try:
            data = r.json()
        except ValueError:
            return None
        with open(cf, "w") as fh:
            json.dump(data, fh)
        return data
    print("  ! ESPN request failed: {}".format(url))
    return None


# --- teams & rosters -------------------------------------------------------

def get_teams() -> List[Dict[str, Any]]:
    d = _get(SITE + "/teams") or {}
    try:
        raw = d["sports"][0]["leagues"][0]["teams"]
    except (KeyError, IndexError):
        return []
    out = []
    for t in raw:
        tm = t["team"]
        logo = (tm.get("logos") or [{}])[0].get("href")
        out.append({"id": tm["id"], "name": tm.get("displayName"), "abbr": tm.get("abbreviation"),
                    "location": tm.get("location"), "color": tm.get("color"),
                    "alt_color": tm.get("alternateColor"), "logo": logo})
    return out


def get_roster(team_id: str) -> List[Dict[str, Any]]:
    d = _get("{}/teams/{}/roster".format(SITE, team_id)) or {}
    return d.get("athletes") or []


# --- season stats (byathlete, paginated) -----------------------------------

def _flatten_athlete(cats_def: List[Dict[str, Any]], athlete_cats: List[Dict[str, Any]]) -> Dict[str, float]:
    """Zip the top-level category name definitions with an athlete's values."""
    by_name = {c.get("name"): c for c in athlete_cats}
    flat: Dict[str, float] = {}
    for cdef in cats_def:
        name = cdef.get("name")
        names = cdef.get("names") or []
        vals = (by_name.get(name) or {}).get("values") or []
        for i, key in enumerate(names):
            if i < len(vals):
                try:
                    flat[key] = float(vals[i])
                except (TypeError, ValueError):
                    pass
    return flat


def get_season_stats(season_year: int, use_cache: bool = True) -> Dict[str, Dict[str, Any]]:
    """Return {espn_athlete_id: {stat_key: value, '_name':..., '_pos':...}} for a season."""
    out: Dict[str, Dict[str, Any]] = {}
    page = 1
    cats_def: List[Dict[str, Any]] = []
    while True:
        url = ("{}/statistics/byathlete?region=us&lang=en&contentorigin=espn"
               "&season={}&seasontype=2&limit=100&page={}").format(WEB, season_year, page)
        d = _get(url, use_cache=use_cache)
        if not d:
            break
        if not cats_def:
            cats_def = d.get("categories") or []
        athletes = d.get("athletes") or []
        for a in athletes:
            ath = a.get("athlete") or {}
            aid = str(ath.get("id"))
            flat = _flatten_athlete(cats_def, a.get("categories") or [])
            flat["_name"] = ath.get("displayName")
            flat["_pos"] = (ath.get("position") or {}).get("abbreviation")
            flat["_team"] = ath.get("teamShortName")   # team of THAT season
            flat["_headshot"] = (ath.get("headshot") or {}).get("href") if isinstance(ath.get("headshot"), dict) else ath.get("headshot")
            flat["_age"] = ath.get("age")
            flat["_debut"] = ath.get("debutYear")
            out[aid] = flat
        pag = d.get("pagination") or {}
        if page >= (pag.get("pages") or 1):
            break
        page += 1
    return out


# --- draft results (core API) ----------------------------------------------

CORE = "https://sports.core.api.espn.com/v2/sports/basketball/leagues/nba"


def get_draft_picks(draft_year: int, use_cache: bool = True) -> Dict[str, int]:
    """{player_display_name: overall_pick} for a draft year (both rounds).

    The draft API's athlete refs live in a prospect id-space that does NOT match
    NBA athlete ids, so we resolve each ref to a name and match on that."""
    url = "{}/seasons/{}/draft/rounds?limit=10".format(CORE, draft_year)
    d = _get(url, use_cache=use_cache) or {}
    out: Dict[str, int] = {}
    for rnd in d.get("items") or []:
        for pick in rnd.get("picks") or []:
            ref = ((pick.get("athlete") or {}).get("$ref") or "").replace("http://", "https://")
            overall = pick.get("overall")
            if not ref or not overall:
                continue
            a = _get(ref, use_cache=use_cache) or {}
            name = a.get("displayName") or "{} {}".format(a.get("firstName", ""), a.get("lastName", "")).strip()
            if name:
                out[name] = int(overall)
    return out
