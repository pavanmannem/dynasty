"""The valuation model (ESPN data). Pure, config-driven, recomputed per request.

    Score  = production(BPS or projection) · availability · age · role · injury
    $Value = convex curve calibrated to THIS league's observed auction prices

Key upgrades vs the first cut:
  - full 13-line scoring incl. technical & flagrant fouls (ESPN has them)
  - recency anchored on 2025-26 (most predictive of 2026-27)
  - STAR FLOOR: elite producers resist the age-decline penalty (fixes Jokic)
  - convex $ curve whose level is calibrated to the drafted anchors (fixes flat/low $)
"""
from __future__ import annotations

import datetime
from typing import Any, Dict, List, Optional

PROSPECT_TIER_FPG = {"elite": 46.0, "starter": 34.0, "deep": 24.0, "flyer": 15.0, "": None}
INJURY_RISK_MULT = {"": 1.0, "low": 0.97, "medium": 0.90, "high": 0.80}

# Age curve anchors (delta at theta=1). Multiplier = 1 + theta*delta.
_AGE_ANCHORS = [
    (19, 0.40), (20, 0.36), (21, 0.29), (22, 0.20), (23, 0.11),
    (24, 0.03), (25, 0.0), (27, 0.0), (28, -0.05), (29, -0.11), (30, -0.18),
    (31, -0.26), (32, -0.34), (33, -0.43), (34, -0.52), (35, -0.58), (38, -0.66),
]


def _n(x: Any) -> float:
    try:
        return float(x) if x is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


# --- Layer 1: exact fantasy points (per game) ------------------------------

def season_fp(s: Dict[str, Any], w: Dict[str, float]) -> float:
    fgm, fga = _n(s.get("fgm")), _n(s.get("fga"))
    ftm, fta = _n(s.get("ftm")), _n(s.get("fta"))
    return (
        w["pts"] * _n(s.get("pts")) + w["reb"] * _n(s.get("reb")) + w["ast"] * _n(s.get("ast"))
        + w["stl"] * _n(s.get("stl")) + w["blk"] * _n(s.get("blk")) + w["tov"] * _n(s.get("tov"))
        + w["fgm"] * fgm + w["fg_miss"] * max(0.0, fga - fgm)
        + w["ftm"] * ftm + w["ft_miss"] * max(0.0, fta - ftm)
        + w["fg3m"] * _n(s.get("fg3m"))
        + w.get("tech", 0.0) * _n(s.get("tech")) + w.get("flag", 0.0) * _n(s.get("flag"))
    )


def fp_breakdown(s: Dict[str, Any], w: Dict[str, float]):
    """Per-category fantasy-point contributions for a per-game line.
    Returns ordered [(label, fp_value)] summing to FP/G — explains the number."""
    fgm, fga = _n(s.get("fgm")), _n(s.get("fga"))
    ftm, fta = _n(s.get("ftm")), _n(s.get("fta"))
    rows = [
        ("Points", w["pts"] * _n(s.get("pts"))),
        ("Rebounds", w["reb"] * _n(s.get("reb"))),
        ("Assists", w["ast"] * _n(s.get("ast"))),
        ("Steals", w["stl"] * _n(s.get("stl"))),
        ("Blocks", w["blk"] * _n(s.get("blk"))),
        ("3-Pointers", w["fg3m"] * _n(s.get("fg3m"))),
        ("FG made", w["fgm"] * fgm),
        ("FT made", w["ftm"] * ftm),
        ("Turnovers", w["tov"] * _n(s.get("tov"))),
        ("FG missed", w["fg_miss"] * max(0.0, fga - fgm)),
        ("FT missed", w["ft_miss"] * max(0.0, fta - ftm)),
    ]
    return [(lbl, round(v, 2)) for lbl, v in rows]


def true_shooting(s: Dict[str, Any]) -> Optional[float]:
    fga, fta, pts = _n(s.get("fga")), _n(s.get("fta")), _n(s.get("pts"))
    denom = 2.0 * (fga + 0.44 * fta)
    return round(pts / denom, 3) if denom > 0 else None


# --- Layer 4: age curve ----------------------------------------------------

def age_from_dob(dob: Optional[str], as_of: Optional[datetime.date] = None) -> Optional[float]:
    if not dob:
        return None
    as_of = as_of or datetime.date.today()
    try:
        b = datetime.datetime.strptime(dob[:10], "%Y-%m-%d").date()
    except ValueError:
        return None
    return round((as_of - b).days / 365.25, 1)


def age_multiplier(age: Optional[float], theta: float) -> float:
    if age is None:
        return 1.0
    if age <= _AGE_ANCHORS[0][0]:
        d = _AGE_ANCHORS[0][1]
    elif age >= _AGE_ANCHORS[-1][0]:
        d = _AGE_ANCHORS[-1][1]
    else:
        d = 0.0
        for (a0, d0), (a1, d1) in zip(_AGE_ANCHORS, _AGE_ANCHORS[1:]):
            if a0 <= age <= a1:
                f = 0.0 if a1 == a0 else (age - a0) / (a1 - a0)
                d = d0 + f * (d1 - d0)
                break
    return max(0.25, min(1.7, 1.0 + theta * d))


# --- Layers 2 & 3 ----------------------------------------------------------

def _recent(seasons: List[Dict[str, Any]], k: int) -> List[Dict[str, Any]]:
    return sorted(seasons, key=lambda s: s.get("season", ""), reverse=True)[:k]


def base_production(seasons: List[Dict[str, Any]], w: Dict[str, float],
                    recency_weights: List[float]) -> Dict[str, Any]:
    recent = _recent(seasons, len(recency_weights))
    if not recent:
        return {"bps": 0.0, "gp_rate": 0.0, "latest_fpg": 0.0, "n_seasons": 0, "latest_season": None}
    fpgs = [season_fp(s, w) for s in recent]
    # Weight each season by recency AND sample size, so a small-sample (injury)
    # season doesn't distort a proven producer's RATE and fluky short samples
    # don't over-inflate. A ~58+ game season carries full weight.
    def sample_w(s):
        return 0.35 + 0.65 * min(1.0, _n(s.get("gp")) / 58.0)
    eff = [rw * sample_w(s) for rw, s in zip(recency_weights[:len(recent)], recent)]
    wsum = sum(eff) or 1.0
    bps = sum(e * fp for e, fp in zip(eff, fpgs)) / wsum
    # Availability keeps the plain recency-weighted games rate (durability still matters).
    rw = recency_weights[:len(recent)]
    rwsum = sum(rw) or 1.0
    gp_rate = sum(w0 * min(1.0, _n(s.get("gp")) / 82.0) for w0, s in zip(rw, recent)) / rwsum
    return {"bps": round(bps, 2), "gp_rate": round(gp_rate, 3), "latest_fpg": round(fpgs[0], 2),
            "n_seasons": len(seasons), "latest_season": recent[0].get("season")}


def availability_multiplier(gp_rate: float, lam: float) -> float:
    return (1.0 - lam) + lam * gp_rate


# --- Layer 5+: composite score for one player ------------------------------

def player_score(player: Dict[str, Any], seasons: List[Dict[str, Any]],
                 override: Dict[str, Any], projection: Optional[Dict[str, Any]],
                 cfg: Dict[str, Any]) -> Dict[str, Any]:
    w = cfg["scoring_weights"]
    prod = base_production(seasons, w, cfg["recency_weights"])
    age = age_from_dob(player.get("date_born")) or (_n(player.get("age_espn")) or None)

    # Production base = Sleeper's 2026-27 projection (forward-looking consensus,
    # covers rookies and prices health/aging) — else recent historical FP/G.
    proj = projection or {}
    proj_fpg = proj.get("proj_fpg")
    adp = proj.get("adp_dynasty")
    latest = prod["latest_fpg"]
    if proj_fpg and float(proj_fpg) > 0:
        pf = float(proj_fpg)
        # Use the BETTER of the 2026-27 projection and the most recent actual season,
        # so a conservative projection never assumes a player in form will decline.
        if latest and latest > pf:
            production, source = latest, "recent"
        else:
            production, source = pf, "projection"
    else:
        production, source = prod["bps"], "history"

    # Light availability (durability signal from recent games; rookies untouched).
    av_basis = prod["gp_rate"] if prod["n_seasons"] else 1.0
    av_mult = availability_multiplier(av_basis, cfg["lambda_av"])

    # Age curve (dynasty multi-year runway) with a star floor for elite producers.
    age_mult = age_multiplier(age, cfg["theta"])
    star_floor = cfg.get("star_floor", 0.8)
    if age_mult < star_floor and production > 30:
        lift = max(0.0, min(1.0, (production - 30.0) / 20.0))
        age_mult = age_mult + (star_floor - age_mult) * lift

    # Most-recent actual season (2025-26) — for DISPLAY only, not the value math.
    recent_row = _recent(seasons, 1)
    rs = recent_row[0] if recent_row else {}

    raw = production * av_mult * age_mult
    return {
        "id_player": player.get("id_player"), "name": player.get("name"),
        "team": player.get("team_abbr") or player.get("team_name"), "position": player.get("position"),
        "age": age, "bps": prod["bps"], "latest_fpg": prod["latest_fpg"],
        "latest_season": prod["latest_season"], "n_seasons": prod["n_seasons"],
        "gp_rate": prod["gp_rate"], "production": round(production, 2),
        "production_source": source, "from_projection": source == "projection",
        "proj_fpg": round(float(proj_fpg), 2) if proj_fpg else None,
        "proj_pts": proj.get("pts"), "proj_reb": proj.get("reb"), "proj_ast": proj.get("ast"),
        "s_pts": rs.get("pts"), "s_reb": rs.get("reb"), "s_ast": rs.get("ast"),
        "s_blk": rs.get("blk"), "s_stl": rs.get("stl"), "s_fg_pct": rs.get("fg_pct"),
        "s_fg3_pct": rs.get("fg3_pct"), "s_ts": true_shooting(rs) if rs else None,
        "s_fpg": rs.get("fpg"), "s_season": rs.get("season"),
        "sleeper_pos": proj.get("sleeper_pos"), "elig_pos": proj.get("elig_pos"), "adp_dynasty": adp,
        "av_mult": round(av_mult, 3), "age_mult": round(age_mult, 3),
        "raw_score": round(max(0.0, raw), 3),
        "experience": player.get("experience"), "injury_status": player.get("injury_status"),
        "headshot": player.get("headshot"),
        "manual_value": override.get("manual_value"), "drafted": int(override.get("drafted") or 0),
        "draft_price": override.get("draft_price"), "draft_owner": override.get("draft_owner"),
    }


# --- Layer 6: convex, market-calibrated auction dollars ---------------------

def assign_values(scores: List[Dict[str, Any]], cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Convex Value-Above-Replacement, normalized to the auction budget.

    Replacement = the (n_teams*roster_spots)-th best score. Value above that is
    raised to `convexity` (top-heaviness) then scaled so the rostered pool sums
    to the league budget. Sub-replacement players get a fractional $ for ordering.
    """
    n_ros = int(cfg["n_teams"]) * int(cfg["roster_spots"])
    min_bid = float(cfg["min_bid"])
    total_pool = float(cfg["n_teams"]) * float(cfg["budget_per_team"])
    conv = float(cfg.get("convexity", 1.6))

    ranked = sorted(scores, key=lambda s: s["raw_score"], reverse=True)
    if not ranked:
        return ranked
    replacement = ranked[min(n_ros, len(ranked)) - 1]["raw_score"]

    for s in ranked:
        s["var"] = max(0.0, s["raw_score"] - replacement)
        s["w"] = s["var"] ** conv
    sum_w = sum(s["w"] for s in ranked) or 1.0
    budget_stars = max(0.0, total_pool - n_ros * min_bid)

    for s in ranked:
        if s["w"] > 0:
            auto = min_bid + s["w"] * budget_stars / sum_w
        else:  # below replacement -> fractional $ just for ordering
            auto = round(min_bid * (s["raw_score"] / replacement), 1) if replacement > 0 else 0.0
        s["auto_value"] = round(auto, 1)
        s["value"] = round(float(s["manual_value"]), 1) if s["manual_value"] is not None else s["auto_value"]
        s.pop("w", None)

    # Name premium: big names get bid up regardless of what the production model
    # says (KD, Steph, Harden...). The market's opinion — name value included —
    # lives in Sleeper's dynasty ADP, so when the market ranks a player HIGHER
    # than we do, pull his price toward what our own curve pays at that market
    # rank. Uplift only: players the market undervalues keep our (higher) value,
    # so bargains stay visible.
    blend = float(cfg.get("market_blend", 0.5))
    curve = sorted((s["value"] for s in ranked), reverse=True)
    with_adp = sorted((s for s in ranked if s.get("adp_dynasty") is not None),
                      key=lambda s: s["adp_dynasty"])
    for mkt_rank, s in enumerate(with_adp, start=1):
        s["market_value"] = round(curve[min(mkt_rank - 1, len(curve) - 1)], 1)
    for s in ranked:
        mv = s.get("market_value")
        premium = blend * max(0.0, mv - s["value"]) if (mv and blend > 0) else 0.0
        s["name_premium"] = round(premium, 1)
        s["model_value"] = s["value"]
        if premium > 0:
            s["value"] = round(s["value"] + premium, 1)
        s["market_delta"] = round(s["value"] - float(s["draft_price"]), 1) if s.get("draft_price") else None

    ranked.sort(key=lambda s: s["value"], reverse=True)
    pos_counts: Dict[str, int] = {}
    for rank, s in enumerate(ranked, start=1):
        s["rank"] = rank
        # ROI: projected production per auction dollar. Cost basis is what was
        # actually paid if drafted, else the model's value (floored at $1).
        cost = float(s["draft_price"]) if s.get("draft_price") else max(1.0, s["value"])
        s["cost"] = round(cost, 1)
        s["roi"] = round(s["production"] / cost, 2) if cost > 0 else None
        # Rank within primary position (by value).
        pos = (s.get("elig_pos") or s.get("sleeper_pos") or s.get("position") or "").split(",")[0].strip()
        if pos:
            pos_counts[pos] = pos_counts.get(pos, 0) + 1
            s["pos_rank"] = "{} #{}".format(pos, pos_counts[pos])
        else:
            s["pos_rank"] = None
    return ranked
