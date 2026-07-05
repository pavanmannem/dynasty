import React, { useMemo, useState, useRef, useEffect } from 'react'

// Anchored dropdown panel (date-picker style): opens under its chip, closes on
// outside click or Escape, commits only on submit.
function Popover({ chipLabel, active, open, setOpen, children }) {
  const ref = useRef(null)
  useEffect(() => {
    if (!open) return
    const onDoc = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false) }
    const onKey = (e) => { if (e.key === 'Escape') setOpen(false) }
    document.addEventListener('mousedown', onDoc)
    document.addEventListener('keydown', onKey)
    return () => { document.removeEventListener('mousedown', onDoc); document.removeEventListener('keydown', onKey) }
  }, [open, setOpen])
  return (
    <span className="popwrap" ref={ref}>
      <button className={'btn sm toggle-btn' + (active ? ' active' : '')} onClick={() => setOpen((o) => !o)}>{chipLabel} ▾</button>
      {open && <div className="popover">{children}</div>}
    </span>
  )
}

const COLS = [
  { key: 'rank', label: '#', w: '30px' },
  { key: 'name', label: 'Player', align: 'left' },
  { key: 'tier', label: 'Tier', align: 'left', hide: true },
  { key: 'pos', label: 'POS', align: 'left' },
  { key: 'age', label: 'Age', xs: true },
  { key: 's_pts', label: 'PTS', hide: true },
  { key: 's_reb', label: 'REB', hide: true },
  { key: 's_ast', label: 'AST', hide: true },
  { key: 's_blk', label: 'BLK', hide: true },
  { key: 's_stl', label: 'STL', hide: true },
  { key: 's_fga', label: 'FGA', hide: true },
  { key: 's_fg_pct', label: 'FG%', hide: true },
  { key: 's_fg3a', label: '3PA', hide: true },
  { key: 's_fg3_pct', label: '3P%', hide: true },
  { key: 's_ts', label: 'TS%', hide: true },
  { key: 's_fpg', label: 'FP/G' },
  { key: 'production', label: "Proj '27" },
  { key: 'roi', label: 'ROI', xs: true },
  { key: 'value', label: 'Value' },
  { key: 'draft_price', label: 'Paid', xs: true },
]
const TIER_ORDER = { elite: 1, star: 2, starter: 3, rotation: 4, flyer: 5 }
const PRICE_BANDS = [
  { id: 'lt10', label: 'Under $10', min: 0, max: 10 },
  { id: '10-30', label: '$10–30', min: 10, max: 30 },
  { id: '30-50', label: '$30–50', min: 30, max: 50 },
]
const ROI_BANDS = [
  { id: '0.5', label: '0.5+', min: 0.5 },
  { id: '1', label: '1+', min: 1 },
  { id: '2', label: '2+', min: 2 },
]

const eligOf = (p) => (p.elig_pos || p.sleeper_pos || '').split(',').map((x) => x.trim()).filter(Boolean)
const posDisplay = (p) => eligOf(p).join('/') || (p.position || '—')
const n1 = (x) => (x == null ? '—' : Number(x).toFixed(1))
const pctd = (x) => (x == null ? '—' : (Number(x) * 100).toFixed(1))
const posSort = (v) => ({ PG: 1, SG: 2, SF: 3, PF: 4, C: 5 }[v] || 9)

export default function RankingTable({ players, onSelect }) {
  const [sortKey, setSortKey] = useState('value')
  const [sortDir, setSortDir] = useState('desc')
  const [search, setSearch] = useState('')
  const [pos, setPos] = useState('')
  const [team, setTeam] = useState('')
  const [statusF, setStatusF] = useState('')        // '' | 'available' | 'drafted'
  const [watchedOnly, setWatchedOnly] = useState(false)
  const [rookiesOnly, setRookiesOnly] = useState(false)
  const [faOnly, setFaOnly] = useState(false)
  const [priceBand, setPriceBand] = useState('')
  const [priceMin, setPriceMin] = useState('')
  const [priceMax, setPriceMax] = useState('')
  const [roiBand, setRoiBand] = useState('')
  const [roiMin, setRoiMin] = useState('')
  // popover open state + draft values (committed on Apply)
  const [pricePop, setPricePop] = useState(false)
  const [roiPop, setRoiPop] = useState(false)
  const [tmpPriceMin, setTmpPriceMin] = useState('')
  const [tmpPriceMax, setTmpPriceMax] = useState('')
  const [tmpRoiMin, setTmpRoiMin] = useState('')

  const openPricePop = (o) => {
    if (typeof o === 'function' ? o(pricePop) : o) { setTmpPriceMin(priceMin); setTmpPriceMax(priceMax) }
    setPricePop(o)
  }
  const openRoiPop = (o) => {
    if (typeof o === 'function' ? o(roiPop) : o) { setTmpRoiMin(roiMin) }
    setRoiPop(o)
  }
  const applyPrice = (e) => {
    e.preventDefault()
    setPriceMin(tmpPriceMin); setPriceMax(tmpPriceMax)
    setPriceBand(tmpPriceMin === '' && tmpPriceMax === '' ? '' : 'custom')
    setPricePop(false)
  }
  const applyRoi = (e) => {
    e.preventDefault()
    setRoiMin(tmpRoiMin)
    setRoiBand(tmpRoiMin === '' ? '' : 'custom')
    setRoiPop(false)
  }

  const positions = ['PG', 'SG', 'SF', 'PF', 'C']
  const teams = useMemo(() => Array.from(new Set(players.map((p) => p.team).filter((t) => t && t !== 'FA'))).sort(), [players])

  const cellVal = (p, k) => (
    k === 'pos' ? posSort(eligOf(p)[0])
      : k === 'tier' ? (TIER_ORDER[p.tier] || 9)
        : k === 'draft_price' ? (p.draft_price ?? -1)
          : p[k])

  const [filtersOpen, setFiltersOpen] = useState(false)
  const nActive = [statusF, watchedOnly, rookiesOnly, faOnly, priceBand, roiBand].filter(Boolean).length
  const anyFilter = nActive > 0

  const rows = useMemo(() => {
    let r = players
    if (search) { const q = search.toLowerCase(); r = r.filter((p) => (p.name || '').toLowerCase().includes(q) || (p.team || '').toLowerCase().includes(q)) }
    if (pos) r = r.filter((p) => eligOf(p).includes(pos))
    if (team) r = r.filter((p) => p.team === team)
    if (statusF === 'available') r = r.filter((p) => !p.drafted)
    else if (statusF === 'drafted') r = r.filter((p) => p.drafted)
    if (watchedOnly) r = r.filter((p) => p.watched)
    if (rookiesOnly) r = r.filter((p) => p.experience === 0 && !p.n_seasons)  // true rookies: no NBA data yet
    if (faOnly) r = r.filter((p) => p.team === 'FA')
    if (priceBand) {
      let lo = 0, hi = Infinity
      if (priceBand === 'custom') {
        lo = priceMin === '' ? 0 : +priceMin
        hi = priceMax === '' ? Infinity : +priceMax
      } else {
        const b = PRICE_BANDS.find((x) => x.id === priceBand)
        lo = b.min; hi = b.max
      }
      r = r.filter((p) => { const c = p.drafted ? p.draft_price : p.value; return c >= lo && c < hi })
    }
    if (roiBand) {
      const min = roiBand === 'custom' ? (roiMin === '' ? 0 : +roiMin) : ROI_BANDS.find((x) => x.id === roiBand).min
      r = r.filter((p) => (p.roi ?? -1) >= min)
    }
    const dir = sortDir === 'asc' ? 1 : -1
    return [...r].sort((a, b) => {
      const av = cellVal(a, sortKey), bv = cellVal(b, sortKey)
      if (typeof av === 'string') return dir * (av || '').localeCompare(bv || '')
      return dir * ((av ?? -1) - (bv ?? -1))
    })
  }, [players, search, pos, team, statusF, watchedOnly, rookiesOnly, faOnly, priceBand, priceMin, priceMax, roiBand, roiMin, sortKey, sortDir])

  const clickSort = (k) => {
    if (k === sortKey) setSortDir((d) => (d === 'asc' ? 'desc' : 'asc'))
    else { setSortKey(k); setSortDir(k === 'name' || k === 'pos' || k === 'tier' || k === 'sleeper_rank' ? 'asc' : 'desc') }
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
          <option value="FA">Free agents</option>
          {teams.map((t) => <option key={t} value={t}>{t}</option>)}
        </select>
        <button className={'btn sm toggle-btn filters-toggle' + (filtersOpen || anyFilter ? ' active' : '')}
          onClick={() => setFiltersOpen((o) => !o)}>
          Filters{nActive ? ' · ' + nActive : ''}
        </button>
      </div>

      <div className={'toolbar filters2' + (filtersOpen ? ' open' : '')}>
        <button className={'btn sm toggle-btn' + (statusF === 'available' ? ' active' : '')}
          onClick={() => setStatusF((s) => (s === 'available' ? '' : 'available'))}>Available</button>
        <button className={'btn sm toggle-btn' + (statusF === 'drafted' ? ' active' : '')}
          onClick={() => setStatusF((s) => (s === 'drafted' ? '' : 'drafted'))}>Drafted</button>
        <button className={'btn sm toggle-btn' + (watchedOnly ? ' active' : '')}
          onClick={() => setWatchedOnly((w) => !w)}>Watched ★</button>
        <button className={'btn sm toggle-btn' + (rookiesOnly ? ' active' : '')}
          onClick={() => setRookiesOnly((w) => !w)}>Rookies</button>
        <button className={'btn sm toggle-btn' + (faOnly ? ' active' : '')}
          onClick={() => setFaOnly((w) => !w)}>Free agents</button>
        <span className="fdivider" />
        <span className="fgroup">Price</span>
        {PRICE_BANDS.map((b) => (
          <button key={b.id} className={'btn sm toggle-btn' + (priceBand === b.id ? ' active' : '')}
            onClick={() => setPriceBand((v) => (v === b.id ? '' : b.id))}>{b.label}</button>
        ))}
        <Popover
          chipLabel={priceBand === 'custom' ? `$${priceMin || '0'}–${priceMax || '∞'}` : 'Custom'}
          active={priceBand === 'custom'} open={pricePop} setOpen={openPricePop}>
          <form onSubmit={applyPrice}>
            <div className="pop-title">Price range</div>
            <div className="pop-row">
              <input type="number" className="mini-input" placeholder="from $" autoFocus
                value={tmpPriceMin} onChange={(e) => setTmpPriceMin(e.target.value)} />
              <span className="pop-dash">–</span>
              <input type="number" className="mini-input" placeholder="to $"
                value={tmpPriceMax} onChange={(e) => setTmpPriceMax(e.target.value)} />
            </div>
            <div className="pop-actions">
              <button type="button" className="btn sm ghost" onClick={() => { setTmpPriceMin(''); setTmpPriceMax('') }}>Reset</button>
              <button type="submit" className="btn sm primary">Apply</button>
            </div>
          </form>
        </Popover>
        <span className="fdivider" />
        <span className="fgroup">ROI</span>
        {ROI_BANDS.map((b) => (
          <button key={b.id} className={'btn sm toggle-btn' + (roiBand === b.id ? ' active' : '')}
            onClick={() => setRoiBand((v) => (v === b.id ? '' : b.id))}>{b.label}</button>
        ))}
        <Popover
          chipLabel={roiBand === 'custom' ? `≥ ${roiMin}` : 'Custom'}
          active={roiBand === 'custom'} open={roiPop} setOpen={openRoiPop}>
          <form onSubmit={applyRoi}>
            <div className="pop-title">Minimum ROI</div>
            <div className="pop-row">
              <input type="number" step="0.1" className="mini-input" placeholder="e.g. 1.5" autoFocus
                value={tmpRoiMin} onChange={(e) => setTmpRoiMin(e.target.value)} />
            </div>
            <div className="pop-actions">
              <button type="button" className="btn sm ghost" onClick={() => setTmpRoiMin('')}>Reset</button>
              <button type="submit" className="btn sm primary">Apply</button>
            </div>
          </form>
        </Popover>
        {anyFilter && (
          <button className="btn sm ghost" onClick={() => {
            setStatusF(''); setWatchedOnly(false); setRookiesOnly(false); setFaOnly(false)
            setPriceBand(''); setPriceMin(''); setPriceMax(''); setRoiBand(''); setRoiMin('')
          }}>Clear</button>
        )}
      </div>

      <div className="glass table-wrap">
        <table>
          <thead><tr>
            {COLS.map((c) => (
              <th key={c.key} className={(c.align === 'left' ? 'left ' : '') + (c.hide ? 'hide-sm ' : '') + (c.xs ? 'hide-xs' : '')} style={c.w ? { width: c.w } : null} onClick={() => clickSort(c.key)}>
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
                <td className="num hide-xs">{p.age != null ? Math.round(p.age) : '—'}</td>
                <td className="num hide-sm">{n1(p.s_pts)}</td>
                <td className="num hide-sm">{n1(p.s_reb)}</td>
                <td className="num hide-sm">{n1(p.s_ast)}</td>
                <td className="num hide-sm">{n1(p.s_blk)}</td>
                <td className="num hide-sm">{n1(p.s_stl)}</td>
                <td className="num hide-sm">{n1(p.s_fga)}</td>
                <td className="num hide-sm">{pctd(p.s_fg_pct)}</td>
                <td className="num hide-sm">{n1(p.s_fg3a)}</td>
                <td className="num hide-sm">{pctd(p.s_fg3_pct)}</td>
                <td className="num hide-sm">{pctd(p.s_ts)}</td>
                <td className="num">{n1(p.s_fpg)}</td>
                <td className="num">{n1(p.production)}</td>
                <td className="num hide-xs">{p.roi == null ? '—' : Number(p.roi).toFixed(2)}</td>
                <td><span className="value"><span className="dollar">$</span>{Math.round(p.value)}</span></td>
                <td className="num hide-xs">{p.drafted && p.draft_price != null ? <span className="paid">${Math.round(p.draft_price)}</span> : '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="footer-hint">{rows.length} players · click any row for the deep dive</div>
    </div>
  )
}
