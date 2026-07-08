"""Live Sleeper auction-draft feed (public GraphQL, no auth required).

Fetches the draft picks (player + amount + owner) as the draft happens. Cached
for a few seconds so the read-only serverless function can hit it on every
request without hammering Sleeper. Fails soft: on any error returns the last
cached result, else an empty draft.
"""
from __future__ import annotations

import json
import time
import unicodedata
import urllib.request
from typing import Any, Dict, List, Optional

GQL_URL = "https://sleeper.com/graphql"
CACHE_TTL = 12  # seconds
_cache: Dict[str, Any] = {"ts": 0.0, "draft_id": None, "data": None}

_QUERY = (
    'query get_draft {{ '
    'get_draft(sport: "nba", draft_id: "{did}"){{ status type settings metadata draft_order }} '
    'user_drafts_by_draft(draft_id: "{did}"){{ user_id user_display_name }} '
    'draft_picks(draft_id: "{did}"){{ pick_no picked_by player_id metadata }} '
    '}}'
)


def norm_name(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower().replace(".", "").replace("'", "").replace("-", " ")
    for suf in (" jr", " sr", " iii", " ii", " iv"):
        if s.endswith(suf):
            s = s[: -len(suf)]
    return " ".join(s.split())


def _empty() -> Dict[str, Any]:
    return {"picks": [], "status": None, "type": None,
            "owners": {}, "order": {}, "settings": {}, "metadata": {}}


def fetch_draft(draft_id: str, use_cache: bool = True) -> Dict[str, Any]:
    now = time.time()
    if (use_cache and _cache["data"] is not None and _cache["draft_id"] == draft_id
            and now - _cache["ts"] < CACHE_TTL):
        return _cache["data"]

    body = json.dumps({"operationName": "get_draft", "variables": {},
                       "query": _QUERY.format(did=draft_id)}).encode("utf-8")
    req = urllib.request.Request(GQL_URL, data=body, headers={
        "content-type": "application/json",
        "x-sleeper-graphql-op": "get_draft",
        "user-agent": "Mozilla/5.0",
    })
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            payload = json.load(resp)
    except Exception:
        return _cache["data"] or _empty()

    data = (payload or {}).get("data") or {}
    gd = data.get("get_draft") or {}
    owners = {u.get("user_id"): u.get("user_display_name")
              for u in (data.get("user_drafts_by_draft") or [])}
    picks: List[Dict[str, Any]] = []
    for p in (data.get("draft_picks") or []):
        m = p.get("metadata") or {}
        name = "{} {}".format(m.get("first_name", ""), m.get("last_name", "")).strip()
        if not name:
            continue
        amt = m.get("amount")
        try:
            amt = int(amt) if amt not in (None, "") else None
        except (TypeError, ValueError):
            amt = None
        picks.append({
            "name": name, "key": norm_name(name), "amount": amt,
            "owner": owners.get(p.get("picked_by")) or p.get("picked_by"),
            "owner_id": p.get("picked_by"),
            "pick_no": p.get("pick_no"),
        })
    out = {"picks": picks, "status": gd.get("status"), "type": gd.get("type"),
           "owners": owners, "order": gd.get("draft_order") or {},
           "settings": gd.get("settings") or {}, "metadata": gd.get("metadata") or {}}
    _cache.update(ts=now, draft_id=draft_id, data=out)
    return out


def drafted_map(draft_id: str) -> Dict[str, Dict[str, Any]]:
    """normalized-name -> {amount, owner, pick_no} for every drafted player."""
    return {p["key"]: p for p in fetch_draft(draft_id)["picks"]}


def latest_pick(draft_id: str) -> Optional[Dict[str, Any]]:
    picks = fetch_draft(draft_id)["picks"]
    return max(picks, key=lambda p: (p["pick_no"] or 0)) if picks else None


# --- watched players (user-specific, needs a token) ------------------------
_watched: Dict[str, Any] = {"ts": 0.0, "token": None, "ids": None}
WATCHED_TTL = 30


def fetch_watched(token: str, use_cache: bool = True) -> set:
    """Set of Sleeper player_ids the user has starred. Empty set if no token."""
    if not token:
        return set()
    now = time.time()
    if (use_cache and _watched["ids"] is not None and _watched["token"] == token
            and now - _watched["ts"] < WATCHED_TTL):
        return _watched["ids"]
    body = json.dumps({"operationName": "watched_players", "variables": {},
                       "query": 'query watched_players { watched_players(sport: "nba"){ player_id } }'
                       }).encode("utf-8")
    req = urllib.request.Request(GQL_URL, data=body, headers={
        "content-type": "application/json",
        "x-sleeper-graphql-op": "watched_players",
        "authorization": token,
        "user-agent": "Mozilla/5.0",
    })
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            payload = json.load(resp)
    except Exception:
        return _watched["ids"] or set()
    wp = ((payload or {}).get("data") or {}).get("watched_players") or []
    ids = {str(w.get("player_id")) for w in wp if w.get("player_id")}
    _watched.update(ts=now, token=token, ids=ids)
    return ids
