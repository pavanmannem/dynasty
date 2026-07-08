"""Central configuration for the Dynasty NBA valuation engine (ESPN data source)."""
from __future__ import annotations

import os

# --- Paths -----------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(BASE_DIR)
DATA_DIR = os.path.join(PROJECT_DIR, "data")
CACHE_DIR = os.path.join(DATA_DIR, "cache")
# DB path can be overridden (Vercel bundles it via includeFiles).
DB_PATH = os.environ.get("DYNASTY_DB", os.path.join(DATA_DIR, "dynasty.sqlite"))

# Read-only mode: the deployed serverless function ships a bundled, immutable DB
# and never writes (config is passed per-request from the browser).
READONLY = bool(os.environ.get("DYNASTY_READONLY") or os.environ.get("VERCEL"))

# --- ESPN ------------------------------------------------------------------
# ESPN uses the season's ENDING year. 2026 => 2025-26 (most recent complete).
SEASON_YEARS = list(range(2026, 2016, -1))  # 10 seasons: 2025-26 back to 2016-17
MIN_REQUEST_INTERVAL = 0.12                 # polite spacing between ESPN calls
SLEEPER_YEAR = 2026                         # 2026-27 projections
# Live Sleeper auction draft (public, no auth). Overridable via env for other leagues.
DRAFT_ID = os.environ.get("SLEEPER_DRAFT_ID", "1375883645973176320")
# Watched-players list is user-specific -> needs a Sleeper session token. Set via
# env only (never commit it). Empty => the watched filter is simply disabled.
SLEEPER_TOKEN = os.environ.get("SLEEPER_TOKEN", "")
# Which draft slot is "me" in the room panel (pavannextdoor).
MY_SLEEPER_USER_ID = os.environ.get("MY_SLEEPER_USER_ID", "334510166290468864")

# --- League scoring (Westlake 512 — exact points settings) -----------------
# Applied to per-game averages. Missed FG/FT are derived (attempts - makes).
SCORING_WEIGHTS = {
    "pts": 1.0,        # Points Scored
    "reb": 1.2,        # Rebound (total)
    "ast": 1.8,        # Assist
    "stl": 3.0,        # Steal
    "blk": 3.0,        # Block
    "tov": -1.5,       # Turnover
    "fgm": 1.6,        # Field Goals Made
    "fg_miss": -1.4,   # Missed FG = FGA - FGM
    "ftm": 0.75,       # Free Throws Made
    "ft_miss": -2.3,   # Missed FT = FTA - FTM
    "fg3m": 1.3,       # 3-point Shots Made
    "tech": -2.0,      # Technical Foul  (now available from ESPN)
    "flag": -2.0,      # Flagrant Foul   (now available from ESPN)
}

# --- Default valuation config (tunable live in the UI) ---------------------
DEFAULT_CONFIG = {
    "n_teams": 12,
    "roster_spots": 24,        # Westlake 512 is a 24-round draft
    "budget_per_team": 400,
    "min_bid": 1,
    # Recency weights for the historical fallback (used when no Sleeper projection).
    "recency_weights": [0.62, 0.28, 0.10],
    "lambda_av": 0.15,         # availability discount — light (projections already price health)
    "theta": 1.10,             # youth tilt on top of projections (dynasty multi-year runway)
    "star_floor": 0.80,        # elite producers resist age decline (min age mult for high BPS)
    "convexity": 2.55,         # $ curve steepness — fit to veteran auction prices
    "market_blend": 0.5,       # name premium: pull toward the price at a player's ADP rank (uplift only)

    "scoring_weights": SCORING_WEIGHTS,
}

# --- Observed auction results (Westlake 512, first 9 nominations) -----------
# Used to (a) mark drafted players and (b) calibrate the $ curve to this market.
# name is matched case-insensitively against ESPN displayName.
DRAFT_RESULTS = [
    {"name": "Victor Wembanyama",       "price": 253, "owner": "rahulgorti"},
    {"name": "Cooper Flagg",            "price": 236, "owner": "Graydog20"},
    {"name": "Nikola Jokic",            "price": 175, "owner": "pavannextdoor", "you": True},
    {"name": "Shai Gilgeous-Alexander", "price": 161, "owner": "stephenokamoto"},
    {"name": "Dylan Harper",            "price": 125, "owner": "rahulgorti"},
    {"name": "Paolo Banchero",          "price": 92,  "owner": "Hcorbett1"},
    {"name": "Kon Knueppel",            "price": 72,  "owner": "pavannextdoor", "you": True},
    {"name": "Jalen Brunson",           "price": 66,  "owner": "likkir"},
    {"name": "Chet Holmgren",           "price": 61,  "owner": "eejj13"},
]

# Player-detail image base (ESPN headshots come as full URLs already).
