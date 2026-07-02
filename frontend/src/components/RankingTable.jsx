import React, { useMemo, useState } from 'react'

const COLS = [
  { key: 'rank', label: '#', w: '30px' },
  { key: 'name', label: 'Player', align: 'left' },
  { key: 'tier', label: 'Tier', align: 'left', hide: true },
  { key: 'pos', label: 'POS', align: 'left' },
  { key: 'age', label: 'Age' },
  { key: 's_pts', label: 'PTS', hide: true },
  { key: 's_reb', label: 'REB', hide: true },
  { key: 's_ast', label: 'AST', hide: true },
  { key: 's_blk', label: 'BLK', hide: true },
  { key: 's_stl', label: 'STL', hide: true },
  { key: 's_fg_pct', label: 'FG%', hide: true },
  { key: 's_fg3_pct', label: '3P%', hide: true },
  { key: 's_ts', label: 'TS%', hide: true },
  { key: 's_fpg', label: 'FP/G' },
  { key: 'roi', label: 'ROI' },
  { key: 'value', label: 'Value' },
  { key: 'draft_price', label: 'Paid' },
]
const TIER_ORDER = { elite: 1, star: 2, starter: 3, rotation: 4, flyer: 5 }
const eligOf = (p) => (p.elig_pos || p.sleeper_pos || '').split(',').map((x) => x.trim()).filter(Boolean)
const posDisplay = (p) => eligOf(p).join('/') || (p.position || '—')
const n1 = (x) => (x == null ? '—' : Number(x).toFixed(1))
const pctd = (x) => (x == null ? '—' : (Number(x) * 100).toFixed(1))
const posSort = (v) => ({ PG: 1, SG: 2, SF: 3, PF: 4, C: 5 }[v] || 9)

export default function RankingTable({ players, config, onConfigChange, onSelect }) {
  const [sortKey, setSortKey] = useState('value')
  const [sortDir, setSortDir] = useState('desc')
  const [search, setSearch] = useState('')
  const [pos, setPos] = useState('')
  const [team, setTeam] = useState('')
  const [statusF, setStatusF] = useState('')        // '' | 'available' | 'drafted'
  const [watchedOnly, setWatchedOnly] = useState(false)
  const [minVal, setMinVal] = useState('')
  const [maxVal, setMaxVal] = useState('')
  const [minRoi, setMinRoi] = useState('')
  const [showConfig, setShowConfig] = useState(false)
  const cfg = config

  const positions = ['PG', 'SG', 'SF', 'PF', 'C']
  const teams = useMemo(() => Array.from(new Set(players.map((p) => p.team).filter(Boolean))).sort(), [players])

  const cellVal = (p, k) => (
    k === 'pos' ? posSort(eligOf(p)[0])
      : k === 'tier' ? (TIER_ORDER[p.tier] || 9)
        : k === 'draft_price' ? (p.draft_price ?? -1)
          : p[k])

  const rows = useMemo(() => {
    let r = players
    if (search) { const q = search.toLowerCase(); r = r.filter((p) => (p.name || '').toLowerCase().includes(q) || (p.team || '').toLowerCase().includes(q)) }
    if (pos) r = r.filter((p) => eligOf(p).includes(pos))
    if (team) r = r.filter((p) => p.team === team)
    if (statusF === 'available') r = r.filter((p) => !p.drafted)
    else if (statusF === 'drafted') r = r.filter((p) => p.drafted)
    if (watchedOnly) r = r.filter((p) => p.watched)
    if (minVal !== '') r = r.filter((p) => (p.drafted ? p.draft_price : p.value) >= +minVal)
    if (maxVal !== '') r = r.filter((p) => (p.drafted ? p.draft_price : p.value) <= +maxVal)
    if (minRoi !== '') r = r.filter((p) => (p.roi ?? -1) >= +minRoi)
    const dir = sortDir === 'asc' ? 1 : -1
    return [...r].sort((a, b) => {
      const av = cellVal(a, sortKey), bv = cellVal(b, sortKey)
      if (typeof av === 'string') return dir * (av || '').localeCompare(bv || '')
      return dir * ((av ?? -1) - (bv ?? -1))
    })
  }, [players, search, pos, team, statusF, watchedOnly, minVal, maxVal, minRoi, sortKey, sortDir])

  const clickSort = (k) => {
    if (k === sortKey) setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    else { setSortKey(k); setSortDir(k === 'name' || k === 'pos' || k === 'tier' || k === 'sleeper_rank' ? 'asc' : 'desc') }
  }
  const applyConfig = (patch) => {
    const [k, v] = Object.entries(patch)[0]
    if (cfg[k] === v) return       // ignore no-op / spurious slider events
    onConfigChange(patch)
  }

  return (
    <div className="fade">
      <div className="toolbar">
        <input className="search" placeholder="Search player" value={search} onChange={(e) => setSearch(e.target.value)} />
        <select className="filter" value={pos} onChange={(e) => setPos(e.target.value)}>
          <option value="">All positions</option>
          {positions.map((p) => <option key={p} value={p}>{p}</option>)}
        </select>
        <select className="filter" value={team} onChange={(e) => setTeam(e.target.value)}>
          <option value="">All teams</option>
          {teams.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
        <button className="btn sm" onClick={() => setShowConfig((s) => !s)}>{showConfig ? 'Hide' : 'Tune'} model</button>
      </div>

      <div className="toolbar filters2">
        <button className={'btn sm toggle-btn' + (statusF === 'available' ? ' active' : '')}
          onClick={() => setStatusF((s) => (s === 'available' ? '' : 'available'))}>Available</button>
        <button className={'btn sm toggle-btn' + (statusF === 'drafted' ? ' active' : '')}
          onClick={() => setStatusF((s) => (s === 'drafted' ? '' : 'drafted'))}>Drafted</button>
        <button className={'btn sm toggle-btn' + (watchedOnly ? ' active' : '')}
          onClick={() => setWatchedOnly((w) => !w)}>Watched ★</button>
        <span className="fdivider" />
        <label className="mini-filter">$
          <input type="number" className="mini-input" placeholder="min" value={minVal} onChange={(e) => setMinVal(e.target.value)} />
          –
          <input type="number" className="mini-input" placeholder="max" value={maxVal} onChange={(e) => setMaxVal(e.target.value)} />
        </label>
        <label className="mini-filter">ROI ≥
          <input type="number" step="0.1" className="mini-input" placeholder="any" value={minRoi} onChange={(e) => setMinRoi(e.target.value)} />
        </label>
        {(statusF || watchedOnly || minVal || maxVal || minRoi) && (
          <button className="btn sm ghost" onClick={() => { setStatusF(''); setWatchedOnly(false); setMinVal(''); setMaxVal(''); setMinRoi('') }}>Clear</button>
        )}
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
            <Slider label="Name premium" val={cfg.market_blend ?? 0.5} min={0} max={1} step={0.05} fmt={(v) => v.toFixed(2)} onCh={(v) => applyConfig({ market_blend: v })} hint="big names get bid toward their market ADP price" />
          </div>
        </div>
      )}

      <div className="glass table-wrap">
        <table>
          <thead><tr>
            {COLS.map((c) => (
              <th key={c.key} className={(c.align === 'left' ? 'left ' : '') + (c.hide ? 'hide-sm' : '')} style={c.w ? { width: c.w } : null} onClick={() => clickSort(c.key)}>
                {c.label}{sortKey === c.key && <span className="arrow"> {sortDir === 'asc' ? '↑' : '↓'}</span>}
              </th>
            ))}
          </tr></thead>
          <tbody>
            {rows.map((p, i) => (
              <tr key={p.id_player} onClick={() => onSelect(p.id_player)}>
                <td className="rank">{i + 1}</td>
                <td className="left">
                  <div className="pcell">
                    <div className="art">{p.headshot && <img src={p.headshot} alt="" loading="lazy" />}</div>
                    <div className="pmeta">
                      <span className="pname">{p.name}</span>
                      <span className="pteam-inline">{p.team}</span>
                    </div>
                  </div>
                </td>
                <td className="left hide-sm"><span className={'tierpill tier-' + p.tier}>{p.tier}</span></td>
                <td className="left pos-pill">{posDisplay(p)}</td>
                <td className="num">{p.age != null ? Math.round(p.age) : '—'}</td>
                <td className="num hide-sm">{n1(p.s_pts)}</td>
                <td className="num hide-sm">{n1(p.s_reb)}</td>
                <td className="num hide-sm">{n1(p.s_ast)}</td>
                <td className="num hide-sm">{n1(p.s_blk)}</td>
                <td className="num hide-sm">{n1(p.s_stl)}</td>
                <td className="num hide-sm">{pctd(p.s_fg_pct)}</td>
                <td className="num hide-sm">{pctd(p.s_fg3_pct)}</td>
                <td className="num hide-sm">{pctd(p.s_ts)}</td>
                <td className="num">{n1(p.s_fpg)}</td>
                <td className="num">{p.roi == null ? '—' : Number(p.roi).toFixed(2)}</td>
                <td><span className="value"><span className="dollar">$</span>{Math.round(p.value)}</span></td>
                <td className="num">{p.drafted && p.draft_price != null ? <span className="paid">${Math.round(p.draft_price)}</span> : '—'}</td>
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
