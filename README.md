# Westlake 512 — Dynasty NBA Auction Valuation Engine

A GM-perspective tool that assigns a **draft dollar value to every NBA player** for the
Westlake 512 dynasty auction (12 teams · $400 · 24 rounds · custom points scoring). It
blends real box-score production with a qualitative layer (youth, upside, injuries, role)
and calibrates the dollar scale to **how this league is actually bidding**.

Data source: **ESPN** (current rosters, bios, and multi-season stats). One current source,
so form is fresh through 2025-26 with a look ahead to 2026-27 via the age curve.

---

## Two views
1. **Ranking table** — sortable, filterable, generative gradient art per player, the youth
   premium (`Age±`) inline, and live model-tuning sliders. Drafted players dim out with the
   price paid.
2. **Player deep-dive** — gradient hero + headshot, 3 seasons of stats with FP/G trend, a
   transparent value breakdown, **market verdict** (bargain / reach vs price paid), bio, and
   the editable GM override panel.

---

## The valuation model

```
Score  = production(recent FP/G, or projection) · availability · age · role · injury
$Value = convex Value-Above-Replacement, normalized to the $4,800 pool
```

| Layer | Captures | How |
|---|---|---|
| **Production** | Exact fantasy output | Your 13-line points formula on ESPN per-game stats → FP/G |
| **BPS** | Recent, stable form | Recency-weighted over 2025-26 / 24-25 / 23-24 (0.62 / 0.28 / 0.10) |
| **Availability** | Injuries / missed games | Games-played rate; `(1−λ)+λ·GP/82` |
| **Age** | Youth, upside, decline | NBA age curve × youth-tilt θ, with a **star floor** so elite vets resist decline |
| **Qualitative** | What stats miss | Prospect tier/projection, injury flag, role adj, manual pin, notes |
| **$ conversion** | Auction economics | VAR^`convexity`, budget-normalized — top-heavy like a real auction |

**Scoring formula (all 13 lines, ESPN has tech/flagrant):**
```
FP = 1·PTS + 1.2·REB + 1.8·AST + 3·STL + 3·BLK − 1.5·TOV
   + 1.6·FGM − 1.4·(FGA−FGM) + 0.75·FTM − 2.3·(FTA−FTM) + 1.3·3PM − 2·TECH − 2·FLAG
```

### Calibrated to the real market
The `convexity` (top-heaviness) was fit to the observed auction. Veteran prices follow a clean
power law (**R² = 0.98**): the model reproduces SGA ($163 vs $161 paid), Jokić ($150 vs $175),
Banchero, Holmgren — and flags the pure upside premiums (Flagg $236, Harper $125) as reaches.
Total allocated ≈ the $4,800 pool. Tune `convexity` in the UI to taste.

### Reading the model
- **Age±** — the youth premium/discount. Flagg +44%, Knueppel +34% (upside) vs Jokić −20% (age).
- **Market verdict** (deep-dive) — `bargain` / `reach` vs the price paid, for drafted players.
  Early marquee nominations tend to read as reaches; value emerges mid-draft.

---

## Setup & run
Requires Python 3.8+ (`fastapi`, `uvicorn`, `requests`) and Node 18+.

```bash
# 1. Ingest from ESPN (~15s, cached & resumable)
cd backend && python ingest.py

# 2. API  (terminal 1, from backend/)
python -m uvicorn server:app --port 8000

# 3. Frontend  (terminal 2, from frontend/)
npm install && npm run dev      # → http://localhost:5173  (proxies /api to :8000)
```

## Using it during the draft
- Sort by **$ Value** for the board, **Age±** to hunt youth/upside, or **Sleeper** to compare
  against the dynasty-ADP consensus.
- Filter by **position** (roster-slot eligibility) and **team**; toggle **Hide drafted**.
- **Tune model** — teams, rounds, budget, youth-tilt (θ), availability (λ), top-heaviness. Live,
  and your settings persist in the browser.
- Click any player for the deep dive: the FP/G category breakdown, the value pipeline
  (production → age → availability → $), 10 years of stats, and the vs-consensus comparison.

## Layout
```
api/index.py   Vercel entrypoint (re-exports the FastAPI app)
backend/       server.py (FastAPI)  scoring.py (model)  db.py  config.py
               espn.py + sleeper.py (clients)  ingest.py
frontend/      src/App.jsx  components/{RankingTable,PlayerView}.jsx  gradient.js  styles.css
data/          dynasty.sqlite  (committed; opened read-only in production)
vercel.json    requirements.txt
```
Values recompute on every request from the bundled stats + the config the browser passes —
tweak a slider and the whole board updates.

## Live draft feed
The board is wired to the league's **Sleeper auction draft** (`config.DRAFT_ID`, public — no
auth). The backend polls it server-side, so as picks happen players are marked **drafted $X**
with the owner, the $ curve re-calibrates on real prices, and the most recent pick shows top-right
(click it to open that player). The frontend re-polls every 15s. Point it at another league by
setting the `SLEEPER_DRAFT_ID` env var.

## Deploy to Vercel
The backend is stateless: SQLite ships read-only and all tunable config lives in the browser
(localStorage), passed per request — so it runs as a Vercel Python Function with no database.

1. Push to GitHub (below), then **Import the repo** on vercel.com.
2. Vercel reads `vercel.json`: it builds the Vite frontend to `frontend/dist` (served static) and
   deploys `api/index.py` as a Python function handling `/api/*`. Vercel's `VERCEL=1` env puts the
   app in read-only mode automatically — no configuration needed.
3. Deploy.

**Refresh prod data:** run `python ingest.py` locally, commit the updated `data/dynasty.sqlite`,
and push — Vercel redeploys with the new data.

## Refreshing data (local)
Re-run `cd backend && python ingest.py` (cheap; cached). Delete `data/cache/` to pull fresh.
