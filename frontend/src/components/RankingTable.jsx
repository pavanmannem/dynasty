import React, { useMemo, useState } from 'react'

const COLS = [
  { key: 'rank', label: '#', w: '30px' },
  { key: 'name', label: 'Player', align: 'left' },
  { key: 'pos', label: 'Pos', align: 'left' },
  { key: 'age', label: 'Age' },
  { key: 'value', label: '$ Value' },
  { key: 'proj_pts', label: 'PTS' },
  { key: 'proj_reb', label: 'REB' },
  { key: 'proj_ast', label: 'AST' },
  { key: 'latest_fpg', label: "FP/G '25" },
  { key: 'proj_fpg', label: "Proj '26" },
  { key: 'production', label: 'Prod' },
  { key: 'raw_score', label: 'Comp' },
  { key: 'sleeper_rank', label: 'Sleeper' },
]
const eligOf = (p) => (p.elig_pos || p.sleeper_pos || '').split(',').map((x) => x.trim()).filter(Boolean)
const posDisplay = (p) => eligOf(p).join('/') || (p.position || '—')
const n1 = (x) => (x == null ? '—' : Number(x).toFixed(1))
const n0 = (x) => (x == null ? '—' : Math.round(x))
const posSort = (v) => ({ PG: 1, SG: 2, SF: 3, PF: 4, C: 5 }[v] || 9)

export default function RankingTable({ players, config, onConfigChange, onSelect }) {
  const [sortKey, setSortKey] = useState('value')
  const [sortDir, setSortDir] = useState('desc')
  const [search, setSearch] = useState('')
  const [pos, setPos] = useState('')
  const [team, setTeam] = useState('')
  const [hideDrafted, setHideDrafted] = useState(false)
  const [showConfig, setShowConfig] = useState(false)
  const cfg = config

  const positions = ['PG', 'SG', 'SF', 'PF', 'C']
  const teams = useMemo(() => Array.from(new Set(players.map((p) => p.team).filter(Boolean))).sort(), [players])

  const cellVal = (p, k) => (k === 'pos' ? posSort(eligOf(p)[0]) : p[k])

  const rows = useMemo(() => {
    let r = players
    if (search) { const q = search.toLowerCase(); r = r.filter((p) => (p.name || '').toLowerCase().includes(q) || (p.team || '').toLowerCase().includes(q)) }
    if (pos) r = r.filter((p) => eligOf(p).includes(pos))
    if (team) r = r.filter((p) => p.team === team)
    if (hideDrafted) r = r.filter((p) => !p.drafted)
    const dir = sortDir === 'asc' ? 1 : -1
    return [...r].sort((a, b) => {
      const av = cellVal(a, sortKey), bv = cellVal(b, sortKey)
      if (typeof av === 'string') return dir * (av || '').localeCompare(bv || '')
      return dir * ((av ?? -1) - (bv ?? -1))
    })
  }, [players, search, pos, team, hideDrafted, sortKey, sortDir])

  const clickSort = (k) => {
    if (k === sortKey) setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    else { setSortKey(k); setSortDir(k === 'name' || k === 'pos' || k === 'sleeper_rank' ? 'asc' : 'desc') }
  }
  const applyConfig = (patch) => {
    const [k, v] = Object.entries(patch)[0]
    if (cfg[k] === v) return       // ignore no-op / spurious slider events
    onConfigChange(patch)
  }

  return (
    <div className="fade">
      <div className="toolbar">
        <input className="search" placeholder="Search player or team…" value={search} onChange={(e) => setSearch(e.target.value)} />
        <select className="filter" value={pos} onChange={(e) => setPos(e.target.value)}>
          <option value="">All positions</option>
          {positions.map((p) => <option key={p} value={p}>{p}</option>)}
        </select>
        <select className="filter" value={team} onChange={(e) => setTeam(e.target.value)}>
          <option value="">All teams</option>
          {teams.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
        <button className={'btn sm toggle-btn' + (hideDrafted ? ' active' : '')} onClick={() => setHideDrafted((s) => !s)}>Hide drafted</button>
        <button className="btn sm" onClick={() => setShowConfig((s) => !s)}>{showConfig ? 'Hide' : 'Tune'} model</button>
      </div>

      {showConfig && (
        <div className="glass config-panel fade">
          <div className="config-grid">
            <Slider label="Teams" val={cfg.n_teams} min={6} max={20} step={1} onCh={(v) => applyConfig({ n_teams: v })} hint="sizes the pool & replacement level" />
            <Slider label="Rounds / roster" val={cfg.roster_spots} min={8} max={30} step={1} onCh={(v) => applyConfig({ roster_spots: v })} hint="how deep the draftable pool runs" />
            <div className="ctl">
              <label>Budget / team: <b>${cfg.budget_per_team}</b></label>
              <input type="number" value={cfg.budget_per_team} onChange={(e) => applyConfig({ budget_per_team: +e.target.value })} />
              <div className="hint">auction dollars each GM has</div>
            </div>
            <Slider label="Youth tilt (θ)" val={cfg.theta} min={0} max={1.6} step={0.05} fmt={(v) => v.toFixed(2)} onCh={(v) => applyConfig({ theta: v })} hint="0 win-now · 1 balanced · 1.6 heavy youth" />
            <Slider label="Availability (λ)" val={cfg.lambda_av} min={0} max={0.7} step={0.05} fmt={(v) => v.toFixed(2)} onCh={(v) => applyConfig({ lambda_av: v })} hint="how hard missed games discount value" />
            <Slider label="Top-heaviness" val={cfg.convexity} min={1} max={3.2} step={0.05} fmt={(v) => v.toFixed(2)} onCh={(v) => applyConfig({ convexity: v })} hint="stars-and-scrubs vs flat" />
          </div>
        </div>
      )}

      <div className="glass table-wrap">
        <table>
          <thead><tr>
            {COLS.map((c) => (
              <th key={c.key} className={c.align === 'left' ? 'left' : ''} style={c.w ? { width: c.w } : null} onClick={() => clickSort(c.key)}>
                {c.label}{sortKey === c.key && <span className="arrow"> {sortDir === 'asc' ? '↑' : '↓'}</span>}
              </th>
            ))}
          </tr></thead>
          <tbody>
            {rows.map((p) => (
              <tr key={p.id_player} onClick={() => onSelect(p.id_player)}>
                <td className="rank">{p.rank}</td>
                <td className="left">
                  <div className="pcell">
                    <div className="art">{p.headshot && <img src={p.headshot} alt="" loading="lazy" />}</div>
                    <div className="pmeta">
                      <span className="pname">{p.name}</span>
                      <span className="pteam-inline">{p.team}</span>
                      <span className={'tierpill tier-' + p.tier}>{p.tier}</span>
                      {p.drafted ? <span className="draftpill">drafted ${p.draft_price}</span> : null}
                    </div>
                  </div>
                </td>
                <td className="left pos-pill">{posDisplay(p)}</td>
                <td className="num">{p.age ?? '—'}</td>
                <td><span className="value"><span className="dollar">$</span>{Math.round(p.value)}</span></td>
                <td className="num">{n1(p.proj_pts)}</td>
                <td className="num">{n1(p.proj_reb)}</td>
                <td className="num">{n1(p.proj_ast)}</td>
                <td className="num">{n1(p.latest_fpg)}</td>
                <td className="num">{n1(p.proj_fpg)}</td>
                <td className="num">{n1(p.production)}</td>
                <td className="num">{n1(p.raw_score)}</td>
                <td className="num">{p.sleeper_rank ? '#' + p.sleeper_rank : '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="footer-hint">{rows.length} players · click any row for the deep dive · values recompute live as you tune the model</div>
    </div>
  )
}

function Slider({ label, val, min, max, step, fmt, onCh, hint }) {
  return (
    <div className="ctl">
      <label>{label}: <b>{fmt ? fmt(val) : val}</b></label>
      <input type="range" min={min} max={max} step={step} value={val} onChange={(e) => onCh(+e.target.value)} />
      <div className="hint">{hint}</div>
    </div>
  )
}
