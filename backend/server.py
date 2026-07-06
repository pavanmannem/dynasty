"""FastAPI serving layer (ESPN data).

Scores recompute per request from raw stats + current config + overrides, so
live config-slider and qualitative-override changes reflect immediately.

Run:  python -m uvicorn api:app --port 8000   (from backend/)
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

import db
import scoring

app = FastAPI(title="Dynasty NBA Valuation Engine")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


import json as _json
import config as _config
import sleeper_draft


def _cfg_from_request(config_param: Optional[str], conn) -> Dict[str, Any]:
    """Config is owned by the browser (localStorage) and passed per request, so
    the serverless function never has to write. Falls back to the bundled config."""
    if config_param:
        cfg = dict(_config.DEFAULT_CONFIG)
        try:
            cfg.update(_json.loads(config_param))
        except (ValueError, TypeError):
            pass
        return cfg
    return db.get_config(conn)


def _load_all(conn, cfg: Dict[str, Any]) -> Dict[str, Any]:
    players = {r["id_player"]: dict(r) for r in conn.execute("SELECT * FROM players").fetchall()}
    seasons: Dict[str, List[Dict[str, Any]]] = {}
    for r in conn.execute("SELECT * FROM player_seasons").fetchall():
        seasons.setdefault(r["id_player"], []).append(dict(r))
    overrides = db.all_overrides(conn)
    projections = db.all_projections(conn)
    # Rookie draft-slot curve, fit on the 2024/2025 classes' actual rookie seasons.
    samples = []
    for pid, p in players.items():
        if p.get("draft_year") in (2024, 2025) and p.get("draft_pick"):
            label = "2024-25" if p["draft_year"] == 2024 else "2025-26"
            for s in seasons.get(pid, []):
                if s["season"] == label and (s.get("gp") or 0) >= 15:
                    samples.append((p["draft_pick"], s.get("fpg") or 0))
    rookie_curve = scoring.fit_rookie_curve(samples)
    # Live Sleeper draft is the source of truth for who's drafted (and for how much);
    # it also re-calibrates the $ curve as real prices come in. Falls back to the
    # bundled seed if the feed is unavailable.
    live = sleeper_draft.drafted_map(_config.DRAFT_ID)
    watched_ids = sleeper_draft.fetch_watched(_config.SLEEPER_TOKEN)
    scores = []
    for pid, p in players.items():
        ov = dict(overrides.get(pid) or db.get_override(conn, pid))
        if live:
            pick = live.get(sleeper_draft.norm_name(p.get("name") or ""))
            ov["drafted"] = 1 if pick else 0
            ov["draft_price"] = pick["amount"] if pick else None
            ov["draft_owner"] = pick["owner"] if pick else None
        pr = projections.get(pid)
        s = scoring.player_score(p, seasons.get(pid, []), ov, pr, cfg, rookie_curve=rookie_curve)
        spid = (pr or {}).get("sleeper_pid")
        s["watched"] = 1 if (spid and str(spid) in watched_ids) else 0
        scores.append(s)
    ranked = scoring.assign_values(scores, cfg)
    # Attach the Sleeper dynasty-ADP consensus rank for divergence comparison.
    for i, s in enumerate(sorted([x for x in ranked if x.get("adp_dynasty")],
                                 key=lambda x: x["adp_dynasty"]), 1):
        s["sleeper_rank"] = i
    return {"cfg": cfg, "ranked": ranked, "seasons": seasons}


def _tier(v: float) -> str:
    if v >= 120:
        return "elite"
    if v >= 60:
        return "star"
    if v >= 25:
        return "starter"
    if v >= 8:
        return "rotation"
    return "flyer"


_LIST_FIELDS = ("rank", "id_player", "name", "team", "position", "age", "latest_fpg", "bps",
                "gp_rate", "av_mult", "age_mult", "production", "production_source", "from_projection",
                "proj_fpg", "proj_pts", "proj_reb", "proj_ast", "sleeper_pos", "elig_pos", "adp_dynasty",
                "s_pts", "s_reb", "s_ast", "s_blk", "s_stl", "s_fg_pct", "s_fga", "s_fg3a",
                "s_fg3_pct", "s_ts", "s_fpg",
                "raw_score", "value", "auto_value",
                "var", "drafted", "draft_price", "draft_owner", "market_delta",
                "n_seasons", "experience", "injury_status", "headshot", "sleeper_rank", "watched",
                "roi", "cost", "pos_rank", "name_premium", "model_value", "market_value", "fp_rank")


@app.get("/api/meta")
def meta() -> Dict[str, Any]:
    conn = db.connect()
    try:
        cfg = dict(_config.DEFAULT_CONFIG)  # canonical calibrated defaults (not a mutable DB row)
        counts = {
            "players": conn.execute("SELECT COUNT(*) FROM players").fetchone()[0],
            "with_stats": conn.execute("SELECT COUNT(DISTINCT id_player) FROM player_seasons").fetchone()[0],
            "teams": conn.execute("SELECT COUNT(*) FROM teams").fetchone()[0],
            "drafted": conn.execute("SELECT COUNT(*) FROM overrides WHERE drafted=1").fetchone()[0],
        }
        seasons = [r[0] for r in conn.execute(
            "SELECT DISTINCT season FROM player_seasons ORDER BY season DESC").fetchall()]
        return {"config": cfg, "counts": counts, "seasons": seasons}
    finally:
        conn.close()


@app.get("/api/draft")
def draft() -> Dict[str, Any]:
    """Live draft state from Sleeper + the most recent pick (with our player id)."""
    conn = db.connect()
    try:
        d = sleeper_draft.fetch_draft(_config.DRAFT_ID)
        picks = d["picks"]
        latest = max(picks, key=lambda p: (p["pick_no"] or 0)) if picks else None
        latest_out = None
        if latest:
            idx = {sleeper_draft.norm_name(r["name"]): r["id_player"]
                   for r in conn.execute("SELECT id_player, name FROM players").fetchall()}
            latest_out = {"name": latest["name"], "amount": latest["amount"],
                          "owner": latest["owner"], "pick_no": latest["pick_no"],
                          "id_player": idx.get(latest["key"])}
        return {"status": d["status"], "type": d["type"], "count": len(picks), "latest": latest_out}
    finally:
        conn.close()


@app.get("/api/players")
def list_players(config: Optional[str] = None) -> List[Dict[str, Any]]:
    conn = db.connect()
    try:
        cfg = _cfg_from_request(config, conn)
        out = []
        for s in _load_all(conn, cfg)["ranked"]:
            row = {k: s.get(k) for k in _LIST_FIELDS}
            row["tier"] = _tier(s["value"])
            out.append(row)
        return out
    finally:
        conn.close()


@app.get("/api/players/{id_player}")
def player_detail(id_player: str, config: Optional[str] = None) -> Dict[str, Any]:
    conn = db.connect()
    try:
        prow = conn.execute("SELECT * FROM players WHERE id_player=?", (id_player,)).fetchone()
        if prow is None:
            raise HTTPException(404, "player not found")
        player = dict(prow)
        cfg = _cfg_from_request(config, conn)
        seasons = [dict(r) for r in conn.execute(
            "SELECT * FROM player_seasons WHERE id_player=? ORDER BY season DESC", (id_player,)).fetchall()]
        ov = db.get_override(conn, id_player)
        prow2 = conn.execute("SELECT * FROM projections WHERE id_player=?", (id_player,)).fetchone()
        projection = dict(prow2) if prow2 else None
        ranked = _load_all(conn, cfg)["ranked"]
        me = next((s for s in ranked if s["id_player"] == id_player), None)
        score = me or scoring.player_score(player, seasons, ov, projection, cfg)

        # Comparables: players producing at a similar level, split by cost efficiency.
        comps = {"cheaper": [], "pricier": []}
        if me and me["production"] > 0:
            band = max(3.0, me["production"] * 0.12)
            similar = [s for s in ranked
                       if s["id_player"] != id_player and s.get("roi")
                       and abs(s["production"] - me["production"]) <= band]
            fields = ("id_player", "name", "team", "production", "cost", "roi",
                      "value", "drafted", "draft_price", "headshot")
            slim = lambda s: {k: s.get(k) for k in fields}
            my_roi = me.get("roi") or 0
            comps["cheaper"] = [slim(s) for s in sorted(
                (x for x in similar if x["roi"] > my_roi), key=lambda x: -x["roi"])[:5]]
            comps["pricier"] = [slim(s) for s in sorted(
                (x for x in similar if x["roi"] <= my_roi), key=lambda x: x["roi"])[:5]]

        # Explain the value: FP/G category breakdown of the production basis + TS%.
        w = cfg["scoring_weights"]
        if score.get("from_projection") and projection:
            basis, basis_label = projection, "2026-27 projection"
        elif seasons:
            basis, basis_label = seasons[0], seasons[0]["season"]
        else:
            basis, basis_label = None, None
        breakdown = scoring.fp_breakdown(basis, w) if basis else []
        ts = scoring.true_shooting(basis) if basis else None

        # Team depth chart as a grid: columns = positions, rows = 1st/2nd/... team.
        depth = None
        if player.get("id_team"):
            drows = [dict(r) for r in conn.execute(
                "SELECT d.pos, d.depth, d.id_player, p.name FROM depth_chart d "
                "JOIN players p ON p.id_player = d.id_player "
                "WHERE d.id_team=? ORDER BY d.depth", (player["id_team"],)).fetchall()]
            if drows:
                cols = [c for c in ("PG", "SG", "SF", "PF", "C") if any(r["pos"] == c for r in drows)]
                bypos = {c: [r for r in drows if r["pos"] == c] for c in cols}
                grid = [[({"id_player": bypos[c][i]["id_player"], "name": bypos[c][i]["name"]}
                          if i < len(bypos[c]) else None) for c in cols]
                        for i in range(max(len(v) for v in bypos.values()))]
                depth = {"positions": cols, "grid": grid}

        team = conn.execute("SELECT * FROM teams WHERE id_team=?", (player.get("id_team"),)).fetchone()
        return {"player": player, "team": dict(team) if team else None, "score": score,
                "seasons": seasons, "projection": projection, "breakdown": breakdown,
                "basis_label": basis_label, "true_shooting": ts, "comps": comps,
                "depth": depth, "tier": _tier(score.get("value", 0))}
    finally:
        conn.close()


class ConfigPatch(BaseModel):
    n_teams: Optional[int] = None
    roster_spots: Optional[int] = None
    budget_per_team: Optional[float] = None
    min_bid: Optional[float] = None
    lambda_av: Optional[float] = None
    theta: Optional[float] = None
    star_floor: Optional[float] = None
    convexity: Optional[float] = None
    market_blend: Optional[float] = None
    recency_weights: Optional[List[float]] = None


@app.get("/api/config")
def get_cfg() -> Dict[str, Any]:
    conn = db.connect()
    try:
        return db.get_config(conn)
    finally:
        conn.close()


@app.put("/api/config")
def put_cfg(patch: ConfigPatch) -> Dict[str, Any]:
    if _config.READONLY:
        raise HTTPException(405, "config is client-side in this deployment; pass ?config=")
    conn = db.connect()
    try:
        cfg = db.get_config(conn)
        for k, v in patch.dict(exclude_none=True).items():
            cfg[k] = v
        db.set_config(conn, cfg)
        return cfg
    finally:
        conn.close()


class OverridePatch(BaseModel):
    prospect_tier: Optional[str] = None
    proj_fpg: Optional[float] = None
    injury_risk: Optional[str] = None
    role_adj: Optional[float] = None
    manual_value: Optional[float] = None
    notes: Optional[str] = None
    drafted: Optional[int] = None
    draft_price: Optional[float] = None
    draft_owner: Optional[str] = None
    clear_manual_value: Optional[bool] = None
    clear_proj_fpg: Optional[bool] = None


@app.put("/api/overrides/{id_player}")
def put_override(id_player: str, patch: OverridePatch) -> Dict[str, Any]:
    if _config.READONLY:
        raise HTTPException(405, "read-only deployment")
    conn = db.connect()
    try:
        data = patch.dict(exclude_none=True)
        if data.pop("clear_manual_value", False):
            data["manual_value"] = None
        if data.pop("clear_proj_fpg", False):
            data["proj_fpg"] = None
        db.set_override(conn, id_player, data)
        prow = dict(conn.execute("SELECT * FROM players WHERE id_player=?", (id_player,)).fetchone())
        seasons = [dict(r) for r in conn.execute(
            "SELECT * FROM player_seasons WHERE id_player=?", (id_player,)).fetchall()]
        cfg = db.get_config(conn)
        ov = db.get_override(conn, id_player)
        prow2 = conn.execute("SELECT * FROM projections WHERE id_player=?", (id_player,)).fetchone()
        projection = dict(prow2) if prow2 else None
        return {"override": ov, "score": scoring.player_score(prow, seasons, ov, projection, cfg)}
    finally:
        conn.close()


import os
_DIST = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend", "dist")
if os.path.isdir(_DIST):
    from fastapi.staticfiles import StaticFiles
    app.mount("/", StaticFiles(directory=_DIST, html=True), name="frontend")
