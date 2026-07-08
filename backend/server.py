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

    # Live auction inflation: remaining room money vs remaining rosterable value.
    # Static values assume the full $4800 chases the full board; as picks land,
    # over/under-spending shifts what the REST of the board will actually cost.
    d_live = sleeper_draft.fetch_draft(_config.DRAFT_ID)
    st = d_live.get("settings") or {}
    n_teams = st.get("teams") or cfg.get("n_teams", 12)
    budget = st.get("budget") or cfg.get("budget_per_team", 400)
    rounds = st.get("rounds") or cfg.get("roster_spots", 24)
    picks = d_live.get("picks") or []
    slots_left = max(0, n_teams * rounds - len(picks))
    money_left = n_teams * budget - sum(p.get("amount") or 0 for p in picks)
    undrafted = sorted((s for s in ranked if not s.get("drafted")),
                       key=lambda s: -s["value"])[:slots_left]
    disc_value = sum(max(0.0, s["value"] - 1.0) for s in undrafted)
    disc_money = money_left - slots_left  # every open slot still costs >= $1
    inflation = round(max(0.5, min(2.0, disc_money / disc_value)), 3) if disc_value > 0 else 1.0
    for s in ranked:
        if s.get("drafted"):
            s["adj_value"] = None
            s["exp_price"] = None
        else:
            s["adj_value"] = round(s["value"] * inflation)
            # What the room will likely pay: the MARKET's number (ADP curve),
            # rescaled by the same live inflation. Our edge = adj_value - this.
            s["exp_price"] = max(1, round((s.get("market_value") or s["value"]) * inflation))
    return {"cfg": cfg, "ranked": ranked, "seasons": seasons, "live": d_live,
            "inflation": inflation, "room_totals": {
                "n_teams": n_teams, "budget": budget, "rounds": rounds,
                "slots_left": slots_left, "money_left": money_left,
                "value_left": round(disc_value + slots_left)}}


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
                "roi", "cost", "pos_rank", "name_premium", "model_value", "market_value", "fp_rank",
                "adj_value", "exp_price")


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


def _owners_state(live: Dict[str, Any], ranked: List[Dict[str, Any]],
                  budget: float, rounds: int) -> List[Dict[str, Any]]:
    """Per-owner room economics: spent, remaining, max bid and pick ledger."""
    val_by_key = {sleeper_draft.norm_name(s["name"]): s for s in ranked}
    owners: Dict[str, Dict[str, Any]] = {}
    for uid, name in (live.get("owners") or {}).items():
        owners[uid] = {"user_id": uid, "name": name,
                       "slot": (live.get("order") or {}).get(uid),
                       "spent": 0, "picks": [],
                       "me": uid == _config.MY_SLEEPER_USER_ID}
    for p in live.get("picks") or []:
        o = owners.get(p.get("owner_id"))
        if o is None:
            continue
        v = val_by_key.get(p["key"])
        amt = p.get("amount") or 0
        o["spent"] += amt
        o["picks"].append({"name": p["name"], "amount": amt,
                           "id_player": v["id_player"] if v else None,
                           "pos": (v.get("elig_pos") or v.get("sleeper_pos") or v.get("position") or "") if v else "",
                           "production": round(v["production"], 1) if v else None,
                           "value": round(v["value"]) if v else None,
                           "delta": round(v["value"] - amt) if v else None})
    out_owners = []
    for o in owners.values():
        left = budget - o["spent"]
        open_slots = max(0, rounds - len(o["picks"]))
        o.update(left=left, open_slots=open_slots,
                 max_bid=max(0, left - max(0, open_slots - 1)),
                 value_won=round(sum(p["value"] or 0 for p in o["picks"])),
                 surplus=round(sum(p["delta"] or 0 for p in o["picks"])))
        o["picks"].sort(key=lambda x: -(x["amount"] or 0))
        out_owners.append(o)
    out_owners.sort(key=lambda o: (o["slot"] or 99))
    return out_owners


@app.get("/api/room")
def room(config: Optional[str] = None) -> Dict[str, Any]:
    """Live auction-room intelligence: per-owner budgets/max bids, market
    inflation, the current lot, and target/nomination recommendations."""
    conn = db.connect()
    try:
        cfg = _cfg_from_request(config, conn)
        la = _load_all(conn, cfg)
        ranked, live, inflation = la["ranked"], la["live"], la["inflation"]
        totals = la["room_totals"]
        budget, rounds = totals["budget"], totals["rounds"]
        out_owners = _owners_state(live, ranked, budget, rounds)

        # The lot currently on the block (live auction metadata).
        meta = live.get("metadata") or {}
        lot = None
        pid = meta.get("nominated_player_id")
        if pid and live.get("status") in ("drafting", "paused"):
            row = conn.execute("SELECT id_player FROM projections WHERE sleeper_pid=?",
                               (str(pid),)).fetchone()
            ps = next((s for s in ranked if row and s["id_player"] == row["id_player"]), None)
            try:
                bid = int(meta.get("highest_offer") or 0)
            except (TypeError, ValueError):
                bid = 0
            lot = {"bid": bid,
                   "leader": (live.get("owners") or {}).get(meta.get("offering_user_id")),
                   "nominator": (live.get("owners") or {}).get(meta.get("nominating_user_id")),
                   "timer_end": meta.get("timer_end_at"),
                   "passed": len([x for x in (meta.get("passed_slots") or "").split(",") if x])}
            if ps:
                lot.update(id_player=ps["id_player"], name=ps["name"],
                           headshot=ps.get("headshot"), value=round(ps["value"]),
                           adj_value=ps.get("adj_value"), production=ps.get("production"))

        undrafted = [s for s in ranked if not s.get("drafted")]
        me = next((o for o in out_owners if o["me"]), None)
        my_max = me["max_bid"] if me else budget

        slim = lambda s: {"id_player": s["id_player"], "name": s["name"],
                          "headshot": s.get("headshot"), "value": round(s["value"]),
                          "adj_value": s.get("adj_value"), "exp_price": s.get("exp_price")}
        # Targets: our adjusted value beats the expected price, and we can afford it.
        targets = sorted((s for s in undrafted if s["exp_price"] <= my_max and s["value"] >= 5),
                         key=lambda s: -((s.get("adj_value") or 0) - s["exp_price"]))[:8]
        # Nominations: the room pays far above our number -> make rivals spend.
        noms = sorted((s for s in undrafted if s.get("market_value")),
                      key=lambda s: -(s["market_value"] - s["value"]))[:6]

        # Starter-or-better supply left at each position.
        supply = {}
        for pos in ("PG", "SG", "SF", "PF", "C"):
            pool = [s for s in undrafted if pos in (s.get("elig_pos") or s.get("sleeper_pos") or "")]
            supply[pos] = {"star": sum(1 for s in pool if s["value"] >= 60),
                           "starter": sum(1 for s in pool if 25 <= s["value"] < 60),
                           "top": [s["name"] for s in sorted(pool, key=lambda x: -x["value"])[:2]]}

        return {"inflation": inflation, "status": live.get("status"), **totals,
                "owners": out_owners, "lot": lot, "supply": supply,
                "targets": [slim(s) for s in targets],
                "nominate": [slim(s) for s in noms]}
    finally:
        conn.close()


_SLOT_GROUPS = {"G": ("PG", "SG"), "F": ("SF", "PF")}


@app.get("/api/strategy")
def strategy(config: Optional[str] = None) -> Dict[str, Any]:
    """My-team plan for the rest of the draft: what to target and what to pay,
    scored on market edge + minutes (depth chart) + age upside + health."""
    conn = db.connect()
    try:
        cfg = _cfg_from_request(config, conn)
        la = _load_all(conn, cfg)
        ranked, live, inflation = la["ranked"], la["live"], la["inflation"]
        totals = la["room_totals"]
        owners = _owners_state(live, ranked, totals["budget"], totals["rounds"])
        me = next((o for o in owners if o["me"]), None)
        if me is None:
            return {"me": None, "inflation": inflation}

        # Which starting slots do my picks already cover? (greedy, best value
        # into the most specific open slot; leftovers are bench)
        st = live.get("settings") or {}
        open_req = {"PG": st.get("slots_pg", 1), "SG": st.get("slots_sg", 1),
                    "SF": st.get("slots_sf", 1), "PF": st.get("slots_pf", 1),
                    "C": st.get("slots_c", 1), "G": st.get("slots_g", 1),
                    "F": st.get("slots_f", 1), "UTIL": st.get("slots_util", 3)}
        for p in sorted(me["picks"], key=lambda x: -(x["value"] or 0)):
            elig = [x.strip() for x in (p.get("pos") or "").split(",") if x.strip()]
            filled = next((pos for pos in elig if open_req.get(pos, 0) > 0), None)
            if not filled:
                filled = next((g for g, mem in _SLOT_GROUPS.items()
                               if open_req.get(g, 0) > 0 and any(x in mem for x in elig)), None)
            if not filled and open_req.get("UTIL", 0) > 0 and elig:
                filled = "UTIL"
            if filled:
                open_req[filled] -= 1
            p["fills"] = filled or "BN"
        needs = {k: v for k, v in open_req.items() if v > 0}

        # Depth-chart standing = minutes security (1st team > deep bench).
        depth = {}
        for r in conn.execute("SELECT id_player, pos, MIN(depth) AS depth "
                              "FROM depth_chart GROUP BY id_player").fetchall():
            depth[r["id_player"]] = {"pos": r["pos"], "depth": r["depth"]}

        my_max = max(1, me["max_bid"])
        cands = []
        for s in ranked:
            if s.get("drafted") or s["exp_price"] > my_max:
                continue
            edge = (s.get("adj_value") or 0) - s["exp_price"]
            if edge < 1 and s["value"] < 5:
                continue
            badges, bonus = [], 0.0
            dep = depth.get(s["id_player"])
            if dep and dep["depth"] <= 2:
                badges.append("{}{} on depth".format(dep["pos"], dep["depth"]))
                bonus += 3.0 if dep["depth"] == 1 else 1.5
            age = s.get("age")
            if age is not None and age <= 23:
                badges.append("age {}".format(int(round(age))))
                bonus += 2.0
            inj = s.get("injury_status") or ""
            if inj and inj != "Active":
                badges.append(inj)
                bonus -= 4.0 if inj in ("Out", "OFS") else 1.5
            elif s.get("n_seasons") and (s.get("gp_rate") or 0) >= 0.85:
                badges.append("durable")
                bonus += 1.0
            elig = [x.strip() for x in (s.get("elig_pos") or s.get("sleeper_pos") or "").split(",") if x.strip()]
            fills = next((p for p in elig if needs.get(p)), None) or \
                next((g for g, mem in _SLOT_GROUPS.items()
                      if needs.get(g) and any(x in mem for x in elig)), None)
            if fills:
                badges.append("fills " + fills)
                bonus += 2.0
            cands.append({"id_player": s["id_player"], "name": s["name"],
                          "headshot": s.get("headshot"), "pos": "/".join(elig) or s.get("position"),
                          "age": int(round(age)) if age is not None else None,
                          "production": round(s.get("production") or 0, 1),
                          "value": round(s["value"]), "adj_value": s.get("adj_value"),
                          "exp_price": s["exp_price"], "edge": round(edge + bonus, 1),
                          "badges": badges})
        cands.sort(key=lambda t: -t["edge"])

        # Budget walk: suggest a bid per remaining slot, always keeping $1 for
        # every slot still to fill afterwards.
        plan, rem = [], me["left"]
        for t in cands[: me["open_slots"]]:
            reserve = me["open_slots"] - len(plan) - 1
            bid = min(max(1, rem - reserve), t["exp_price"] + (1 if t["edge"] >= 10 else 0))
            plan.append(dict(t, suggest=bid))
            rem -= bid

        return {"inflation": inflation, "status": live.get("status"),
                "me": me, "needs": needs, "plan": plan,
                "more": cands[me["open_slots"]: me["open_slots"] + 12],
                "planned_spend": me["left"] - rem}
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
                        for i in range(min(5, max(len(v) for v in bypos.values())))]
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
