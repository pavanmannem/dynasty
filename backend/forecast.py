"""Our own 2026-27 FP/G forecast.

Built from the discovery pass (July 2026, this repo's 10-season DB):

1. Sleeper's 2026-27 projections carry real signal (role/team/injury context)
   but have a systematic AGE-SHAPED bias vs 2025-26 actuals:
       sophomores  implied -5.3%  vs actual rookie->Y2 median +13.8%
       Y2->Y3      implied -14.0% vs age-22/23 median +9.1%
       Y3-5        implied -11.5% vs age-24/25 median +3.9%
       exp 6-9     implied  -8.7% vs age-26/29 median ~0%
       exp 10+     implied  -1.8% vs age-30/33 median ~-4.7%
   We correct HALF the measured gap (damped: part of the bearishness is
   legitimate mean-reversion).

2. A from-scratch trajectory model (last season x empirical age curve +
   damped trend) only matched naive carry-forward in backtest (MAE ~5 FP/G),
   so it's a blend component, not a replacement.

3. Playoff momentum is real but small: 2024-25 playoff overperformers (>=8
   games, +3..8 FP/G above regular season) grew +10.2% next season vs +3-6%
   baseline. Small, capped, positive-only bump.

4. Availability must be CALENDAR-aware: a fully missed season (Dame/Kyrie/
   Kawhi 2025-26) counts as zero games, and the FP/G base decays for rust.

5. Rookies with no NBA data are projected from a draft-slot curve fit on the
   2024 + 2025 classes' actual rookie seasons in this DB.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Tuple

# Empirical median YoY FP/G change by age (Q2 of discovery; >=25gp pairs, n=1294).
AGE_CURVE = [(20, 0.187), (22, 0.091), (24, 0.039), (26, 0.019),
             (28, -0.025), (30, -0.039), (32, -0.056), (34, -0.064)]

# Damped cohort corrections to Sleeper's implied YoY (half the measured gap).
def _sleeper_correction(exp: Optional[int]) -> float:
    if exp is None:
        return 0.0
    if exp <= 1:
        return 0.095
    if exp == 2:
        return 0.115
    if exp <= 4:
        return 0.077
    if exp <= 9:
        return 0.043
    return -0.015


RUST = 0.85          # FP/G decay for a fully missed most-recent season
PO_MIN_GAMES = 8     # playoff momentum needs a real sample
PO_WEIGHT = 0.25     # fraction of playoff overperformance that bleeds forward
PO_CAP = 6.0         # max playoff bump in FP/G
ROOKIE_GP = 0.72     # default availability for incoming rookies

SEASONS_ORDER = ["2025-26", "2024-25", "2023-24"]
AV_WEIGHTS = [0.60, 0.28, 0.12]


def age_yoy(age: Optional[float]) -> float:
    if age is None:
        return 0.0
    if age <= AGE_CURVE[0][0]:
        return AGE_CURVE[0][1]
    if age >= AGE_CURVE[-1][0]:
        return AGE_CURVE[-1][1]
    for (a0, v0), (a1, v1) in zip(AGE_CURVE, AGE_CURVE[1:]):
        if a0 <= age <= a1:
            f = (age - a0) / (a1 - a0)
            return v0 + f * (v1 - v0)
    return 0.0


def fit_rookie_curve(samples: List[Tuple[int, float]]) -> Tuple[float, float]:
    """Fit fpg = a + b*ln(pick) on (pick, rookie fpg) samples. Falls back to a
    sane prior if the sample is thin."""
    pts = [(p, f) for p, f in samples if p and f and f > 5]
    if len(pts) < 15:
        return 38.0, -6.5
    xs = [math.log(p) for p, _ in pts]
    ys = [f for _, f in pts]
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    b = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / (sum((x - mx) ** 2 for x in xs) or 1)
    a = my - b * mx
    return a, b


def rookie_fpg(pick: Optional[int], curve: Tuple[float, float]) -> float:
    a, b = curve
    p = pick or 45  # undrafted/unknown -> treat as a late-second value
    return max(8.0, a + b * math.log(max(1, p)))


def build_forecast(player: Dict[str, Any], seasons: List[Dict[str, Any]],
                   projection: Optional[Dict[str, Any]],
                   playoff: Optional[Dict[str, Any]],
                   rookie_curve: Tuple[float, float],
                   age: Optional[float]) -> Dict[str, Any]:
    """Returns {fpg, gp_rate, source, parts:{...}} for 2026-27."""
    by = {s["season"]: s for s in seasons}
    exp = player.get("experience")
    proj_fpg = (projection or {}).get("proj_fpg")
    parts: Dict[str, Any] = {}

    # --- calendar-aware availability -----------------------------------
    yrs_in_league = exp if exp is not None else 3
    expected = SEASONS_ORDER[:max(1, min(3, yrs_in_league))]
    if yrs_in_league and yrs_in_league > 0:
        w = AV_WEIGHTS[:len(expected)]
        tot = sum(w)
        gp_rate = sum(wi * min(1.0, ((by.get(s) or {}).get("gp") or 0) / 82.0)
                      for wi, s in zip(w, expected)) / tot
    else:
        gp_rate = ROOKIE_GP

    # --- rookies with no NBA seasons ------------------------------------
    played = [s for s in seasons if (s.get("gp") or 0) >= 15]
    if not played:
        if proj_fpg and proj_fpg > 0:  # sleeper covers a couple of rookies
            fpg = float(proj_fpg) * (1 + _sleeper_correction(exp))
            parts["sleeper_adj"] = round(fpg, 1)
            src = "market"
        else:
            fpg = rookie_fpg(player.get("draft_pick"), rookie_curve)
            parts["rookie_curve"] = round(fpg, 1)
            parts["draft_pick"] = player.get("draft_pick")
            src = "rookie-curve"
        return {"fpg": round(fpg, 2), "gp_rate": round(max(gp_rate, ROOKIE_GP if not by else gp_rate), 3),
                "source": src, "parts": parts}

    # --- veteran trajectory ----------------------------------------------
    played.sort(key=lambda s: s["season"], reverse=True)
    last = played[0]
    base = last["fpg"] or 0.0
    # damped momentum from the season before that
    if len(played) > 1 and int(played[0]["season"][:4]) - int(played[1]["season"][:4]) == 1:
        base += 0.30 * ((played[0]["fpg"] or 0) - (played[1]["fpg"] or 0)) * 0.5
    trajectory = base * (1 + age_yoy(age))
    missed = last["season"] != "2025-26"
    if missed:
        # apply the age curve for each missed year + rust
        yrs_missed = min(2, 2026 - 1 - int(last["season"][:4]))
        for _ in range(max(0, yrs_missed)):
            trajectory *= (1 + age_yoy(age))
        trajectory *= RUST
        parts["rust_years"] = yrs_missed
    parts["trajectory"] = round(trajectory, 1)

    # --- de-biased sleeper ------------------------------------------------
    sleeper_adj = None
    if proj_fpg and proj_fpg > 0:
        sleeper_adj = float(proj_fpg) * (1 + _sleeper_correction(exp))
        parts["sleeper_adj"] = round(sleeper_adj, 1)

    # --- blend -------------------------------------------------------------
    if sleeper_adj is not None:
        # if he missed 2025-26, the market number knows things (injury, new team
        # role) that stale stats don't -> trust it more
        wt = 0.65 if missed else 0.50
        fpg = wt * sleeper_adj + (1 - wt) * trajectory
        src = "blend"
    else:
        fpg, src = trajectory, "trajectory"

    # --- playoff momentum ---------------------------------------------------
    if playoff and (playoff.get("gp") or 0) >= PO_MIN_GAMES and by.get("2025-26"):
        excess = (playoff.get("fpg") or 0) - (by["2025-26"].get("fpg") or 0)
        if excess > 0:
            bump = min(PO_CAP, PO_WEIGHT * excess)
            fpg += bump
            parts["playoff_bump"] = round(bump, 1)

    return {"fpg": round(fpg, 2), "gp_rate": round(gp_rate, 3), "source": src, "parts": parts}
