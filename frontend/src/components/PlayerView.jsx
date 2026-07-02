import React, { useEffect, useState } from 'react'
import { getPlayer } from '../api.js'
import { playerGradient } from '../gradient.js'

function CareerBars({ seasons }) {
  const pts = [...seasons].reverse().map((s) => ({ label: s.season, fpg: s.fpg || 0 }))
  if (pts.length < 2) return null
  // viewBox + preserveAspectRatio="none" makes the drawing stretch to fill
  // whatever width/height CSS gives the <svg>, regardless of point count.
  const VW = 600, VH = 90, pad = 3, gap = 6
  const max = Math.max(...pts.map((p) => p.fpg), 1)
  const bw = (VW - pad * 2) / pts.length
  return (
    <svg className="spark" viewBox={`0 0 ${VW} ${VH}`} preserveAspectRatio="none">
      {pts.map((p, i) => {
        const h = Math.max(2, (p.fpg / max) * (VH - pad * 2))
        const x = pad + i * bw + gap / 2
        const w = Math.max(1, bw - gap)
        const isLatest = i === pts.length - 1
        return (
          <rect key={p.label} x={x} y={VH - pad - h} width={w} height={h} rx="2"
            fill={isLatest ? 'var(--gold)' : 'var(--accent)'} opacity={isLatest ? 1 : 0.85} />
        )
      })}
    </svg>
  )
}

const f1 = (x) => (x == null ? '—' : Number(x).toFixed(1))
const pctf = (x) => (x == null ? '—' : (x * 100).toFixed(1))
const pctc = (m, a) => (a ? ((m / a) * 100).toFixed(1) : '—')  // computed pct

function StatRow({ label, team, s, cls, computedPct }) {
  return (
    <tr className={cls}>
      <td className="left">{label}</td>
      <td className="left pteam">{team ?? '—'}</td>
      <td className="num">{s.gp ? Math.round(s.gp) : '—'}</td>
      <td className="num">{f1(s.mpg)}</td>
      <td className="num">{f1(s.pts)}</td>
      <td className="num">{f1(s.reb)}</td>
      <td className="num">{f1(s.ast)}</td>
      <td className="num">{f1(s.stl)}</td>
      <td className="num">{f1(s.blk)}</td>
      <td className="num">{f1(s.tov)}</td>
      <td className="num">{computedPct ? pctc(s.fgm, s.fga) : pctf(s.fg_pct)}</td>
      <td className="num">{computedPct ? pctc(s.fg3m, s.fg3a) : pctf(s.fg3_pct)}</td>
      <td className="num">{computedPct ? pctc(s.ftm, s.fta) : pctf(s.ft_pct)}</td>
      <td className="num fpg">{f1(s.fpg ?? s.proj_fpg)}</td>
    </tr>
  )
}

export default function PlayerView({ id, config, onBack, onOpen }) {
  const [d, setD] = useState(null)
  useEffect(() => { setD(null); getPlayer(id, config).then(setD) }, [id, config])
  useEffect(() => {
    const onKey = (e) => { if (e.key === 'Escape') onBack() }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onBack])

  const onBackdrop = (e) => { if (e.target === e.currentTarget) onBack() }
  const closeBtn = (
    <button className="modal-close" onClick={onBack} aria-label="Close (Esc)">
      <span className="x">✕</span><span className="esc">Esc</span>
    </button>
  )
  if (!d) return <div className="modal-backdrop" onClick={onBackdrop}>{closeBtn}<div className="loading">Loading…</div></div>

  const { player: p, score: sc, seasons, projection: proj, breakdown, basis_label, true_shooting: ts } = d
  const photo = p.headshot
  const md = sc.market_delta
  const maxBd = Math.max(...breakdown.map((b) => Math.abs(b[1])), 1)

  // consensus divergence
  const gap = sc.sleeper_rank ? sc.rank - sc.sleeper_rank : null
  const consensus = gap == null ? 'No consensus ADP for this player'
    : Math.abs(gap) <= 6 ? 'In line with the dynasty consensus'
    : gap < 0 ? `We rank him ${-gap} spots higher than consensus` : `We rank him ${gap} spots lower than consensus`

  return (
    <div className="modal-backdrop" onClick={onBackdrop}>
      {closeBtn}
      <div className="modal fade">
      <div className="pv-hero">
        <div className="pv-hero-art" style={{ backgroundImage: playerGradient(p.id_player) }} />
        <div className="pv-hero-inner">
          {photo ? <img className="pv-photo" src={photo} alt="" /> : <div className="pv-photo" />}
          <div className="pv-id">
            <h1>{p.name}</h1>
            <div className="pv-sub">
              {p.team_name} · {(sc.elig_pos || sc.sleeper_pos || p.position || '').split(',').join('/')} · Age {sc.age ?? '—'}
              {p.experience != null ? ` · ${p.experience === 0 ? 'Rookie' : p.experience + ' yr'}` : ''}
              {sc.production_source === 'projection' ? <span className="chip-mini proj">2026-27 projection</span>
                : sc.production_source === 'recent' ? <span className="chip-mini proj">2025-26 form</span>
                  : <span className="chip-mini">career avg</span>}
              {sc.drafted ? <span className="chip-mini gone">drafted ${sc.draft_price} · {sc.draft_owner}</span> : null}
              {p.injury_status && p.injury_status !== 'Active' ? <span className="chip-mini gone">{p.injury_status}</span> : null}
            </div>
          </div>
          <div className="pv-valuebox">
            <div className="v"><span className="dollar">$</span>{Math.round(sc.value)}</div>
            <div className="r">rank #{sc.rank} · {d.tier}</div>
          </div>
        </div>
      </div>

      <div className="metrics">
        <div className="glass metric"><div className="k">Auction value</div><div className="v money">${Math.round(sc.value)}</div><div className="sub">of $4,800 pool</div></div>
        <div className="glass metric"><div className="k">Position rank</div><div className="v">{sc.pos_rank || '—'}</div><div className="sub">at his slot, by value</div></div>
        <div className="glass metric"><div className="k">ROI</div><div className="v">{sc.roi != null ? Number(sc.roi).toFixed(2) : '—'}</div><div className="sub">FP/G per $ {sc.drafted ? 'paid' : 'of value'}</div></div>
        <div className="glass metric"><div className="k">Sleeper ADP</div><div className="v">{sc.sleeper_rank ? '#' + sc.sleeper_rank : '—'}</div><div className="sub">dynasty consensus</div></div>
        <div className="glass metric"><div className="k">True shooting</div><div className="v">{ts ? (ts * 100).toFixed(1) + '%' : '—'}</div><div className="sub">efficiency</div></div>
      </div>

      <div className="grid2">
        <div>
          <div className="glass card">
            <h3>Projected fantasy points per game</h3>
            {breakdown.map(([lbl, v]) => (
              <div className="bd-row" key={lbl}>
                <div className="bd-label">{lbl}</div>
                <div className="bd-track"><div className={'bd-bar ' + (v >= 0 ? 'pos' : 'neg')} style={{ width: (Math.abs(v) / maxBd) * 100 + '%' }} /></div>
                <div className="bd-val" style={{ color: v >= 0 ? 'var(--ink)' : 'var(--down)' }}>{v >= 0 ? '+' : ''}{v.toFixed(1)}</div>
              </div>
            ))}
            <div className="bd-total"><span style={{ color: 'var(--muted)' }}>Projected FP/G</span><span className="n">{f1(sc.production)}</span></div>
          </div>

          <div className="glass card">
            <h3>Season history · FP/G trend</h3>
            <CareerBars seasons={seasons} />
            <div className="scroll-x">
              <table className="stat-table">
                <thead><tr>
                  {['Season', 'Tm', 'GP', 'MPG', 'PTS', 'REB', 'AST', 'STL', 'BLK', 'TOV', 'FG%', '3P%', 'FT%', 'FP/G'].map((h, i) =>
                    <th key={h} className={i < 2 ? 'left' : ''}>{h}</th>)}
                </tr></thead>
                <tbody>
                  {proj && sc.from_projection && <StatRow label="2026-27" team="proj" s={{ ...proj }} cls="proj-row" computedPct />}
                  {seasons.map((s) => <StatRow key={s.season} label={s.season} team={s.team} s={s} />)}
                  {seasons.length === 0 && !proj && <tr><td colSpan="14" className="left" style={{ color: 'var(--muted)' }}>No stats or projection available.</td></tr>}
                </tbody>
              </table>
            </div>
          </div>
        </div>

        <div>
          <div className="glass card">
            <h3>How we get to the value</h3>
            <div className="pipe-row">
              <span className="lbl">Projected fantasy points / game</span>
              <span className="val">{f1(sc.production)}</span>
            </div>
            <div className="pipe-row">
              <span className="lbl"><span className="op">×</span>Age<span className="sub">age {sc.age ?? '—'}</span></span>
              <span className={'val ' + (sc.age_mult >= 1 ? 'up' : 'down')}>{sc.age_mult.toFixed(2)}</span>
            </div>
            <div className="pipe-row">
              <span className="lbl"><span className="op">×</span>Availability<span className="sub">{sc.gp_rate != null ? Math.round(sc.gp_rate * 100) + '% of games' : ''}</span></span>
              <span className="val">{sc.av_mult.toFixed(2)}</span>
            </div>
            <div className="pipe-row total">
              <span className="lbl">Composite score</span>
              <span className="val">{sc.raw_score.toFixed(1)}</span>
            </div>
            <div className="pipe-row final">
              <span className="lbl">Auction value
                <span className="tip">
                  <span className="tip-icon">?</span>
                  <span className="tip-body">The <b>composite score</b> above is ranked against every player. Only the amount <b>above the last draftable player</b> (replacement level) is worth money. That surplus is steepened so stars pull ahead, then scaled so all {config.n_teams} teams' bids add up to the <b>${config.n_teams * config.budget_per_team} league budget</b>. That is this player's dollar value.</span>
                </span>
              </span>
              <span className="val">${Math.round(sc.value)}</span>
            </div>
            {sc.drafted ? (
              <div className="market-line">
                <span style={{ color: 'var(--muted)' }}>Paid <b style={{ color: 'var(--ink)' }}>${sc.draft_price}</b> · {sc.draft_owner}</span>
                <span className={md > 8 ? 'up' : md < -8 ? 'down' : ''} style={{ fontWeight: 600 }}>
                  {md > 8 ? `bargain +$${Math.round(md)}` : md < -8 ? `reach −$${Math.abs(Math.round(md))}` : 'fair price'}
                </span>
              </div>
            ) : null}
          </div>

          <div className="glass card">
            <h3>Vs dynasty consensus</h3>
            <div className="compare">
              <div className="box"><div className="n">#{sc.rank}</div><div className="l">Our model</div></div>
              <div className="arrow">↔</div>
              <div className="box"><div className="n">{sc.sleeper_rank ? '#' + sc.sleeper_rank : '—'}</div><div className="l">Sleeper ADP</div></div>
            </div>
            <div className="verdict">{consensus}</div>
          </div>

          <div className="glass card">
            <h3>Bio</h3>
            <div className="bio-grid">
              <div><div className="k">Height</div><div className="val">{p.height || '—'}</div></div>
              <div><div className="k">Weight</div><div className="val">{p.weight || '—'}</div></div>
              <div><div className="k">College</div><div className="val">{p.college || '—'}</div></div>
              <div><div className="k">Exp</div><div className="val">{p.experience != null ? (p.experience === 0 ? 'Rookie' : p.experience + ' yr') : '—'}</div></div>
              <div><div className="k">Number</div><div className="val">{p.jersey ? '#' + p.jersey : '—'}</div></div>
              <div><div className="k">Seasons</div><div className="val">{sc.n_seasons}</div></div>
            </div>
          </div>
        </div>
      </div>

      {(d.comps?.cheaper?.length || d.comps?.pricier?.length) ? (
        <div className="glass card">
          <h3>Similar production, different price</h3>
          <div className="comps-grid">
            <div>
              <div className="comps-head up">Better value at ~{f1(sc.production)} FP/G</div>
              {d.comps.cheaper.length === 0 && <div className="comps-empty">Nobody cheaper at this level</div>}
              {d.comps.cheaper.map((c) => <CompRow key={c.id_player} c={c} onOpen={onOpen} />)}
            </div>
            <div>
              <div className="comps-head down">Pricier at the same level</div>
              {d.comps.pricier.length === 0 && <div className="comps-empty">Nobody pricier at this level</div>}
              {d.comps.pricier.map((c) => <CompRow key={c.id_player} c={c} onOpen={onOpen} />)}
            </div>
          </div>
        </div>
      ) : null}
      </div>
    </div>
  )
}

function CompRow({ c, onOpen }) {
  return (
    <button className="comp-row" onClick={() => onOpen && onOpen(c.id_player)}>
      <span className="art sm">{c.headshot && <img src={c.headshot} alt="" loading="lazy" />}</span>
      <span className="comp-name">{c.name}<span className="comp-team">{c.team}</span></span>
      <span className="comp-stats">
        <b>{Number(c.production).toFixed(1)}</b> FP/G · <b>${Math.round(c.cost)}</b>{c.drafted ? ' paid' : ''} · ROI <b>{Number(c.roi).toFixed(2)}</b>
      </span>
    </button>
  )
}
