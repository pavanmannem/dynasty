import React, { useEffect, useState } from 'react'
import { getPlayer } from '../api.js'

// One backdrop for everyone (bd1: the warm ASCII gradient).
const backdropFor = () => '/backdrops/bd1.jpg'

function CareerBars({ seasons }) {
  const pts = [...seasons].reverse().map((s) => ({ season: s.season, fpg: s.fpg || 0 }))
  if (pts.length < 2) return null
  const max = Math.max(...pts.map((p) => p.fpg), 1)
  return (
    <div className="cbars">
      {pts.map((p, i) => (
        <div className="cbar" key={p.season}>
          <div className="cbar-val">{p.fpg.toFixed(1)}</div>
          <div className="cbar-track">
            <div className={'cbar-fill' + (i === pts.length - 1 ? ' latest' : '')}
              style={{ height: Math.max(3, (p.fpg / max) * 100) + '%' }} />
          </div>
          <div className="cbar-year">{p.season}</div>
        </div>
      ))}
    </div>
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
      <td className="num">{f1(s.fga)}</td>
      <td className="num">{computedPct ? pctc(s.fgm, s.fga) : pctf(s.fg_pct)}</td>
      <td className="num">{f1(s.fg3a)}</td>
      <td className="num">{computedPct ? pctc(s.fg3m, s.fg3a) : pctf(s.fg3_pct)}</td>
      <td className="num">{computedPct ? pctc(s.ftm, s.fta) : pctf(s.ft_pct)}</td>
      <td className="num fpg">{f1(s.fpg ?? s.proj_fpg)}</td>
    </tr>
  )
}

function CompsTable({ title, cls, rows, onOpen }) {
  return (
    <div>
      <div className={'comps-head ' + cls}>{title}</div>
      {rows.length === 0 ? <div className="comps-empty">Nobody at this level</div> : (
        <table className="stat-table comps-table">
          <thead><tr>
            <th className="left">Player</th><th>FP/G</th><th>Cost</th><th>ROI</th>
          </tr></thead>
          <tbody>
            {rows.map((c) => (
              <tr key={c.id_player} onClick={() => onOpen && onOpen(c.id_player)}>
                <td className="left">
                  <span className="comp-cell">
                    <span className="art sm">{c.headshot && <img src={c.headshot} alt="" loading="lazy" />}</span>
                    <span className="comp-name">{c.name}</span>
                    <span className="comp-team">{c.team}</span>
                  </span>
                </td>
                <td className="num">{Number(c.production).toFixed(1)}</td>
                <td className="num">${Math.round(c.cost)}{c.drafted ? ' paid' : ''}</td>
                <td className="num">{Number(c.roi).toFixed(2)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
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

  const { player: p, score: sc, seasons, projection: proj, breakdown } = d
  const photo = p.headshot
  const maxBd = Math.max(...breakdown.map((b) => Math.abs(b[1])), 1)

  const bio = [p.height, p.weight, p.college, p.jersey ? '#' + p.jersey : null,
    sc.n_seasons ? sc.n_seasons + ' seasons' : null].filter(Boolean).join(' · ')
  const gap = sc.sleeper_rank ? sc.rank - sc.sleeper_rank : null
  const consensus = gap == null ? null
    : Math.abs(gap) <= 6 ? 'matches consensus'
    : gap < 0 ? `${-gap} above consensus` : `${gap} below consensus`

  return (
    <div className="modal-backdrop" onClick={onBackdrop}>
      {closeBtn}
      <div className="modal fade">
      <div className="pv-hero">
        <div className="pv-hero-art" style={{ backgroundImage: `url(${backdropFor(p.id_player)})` }} />
        <div className="pv-hero-inner">
          {photo ? <img className="pv-photo" src={photo} alt="" /> : <div className="pv-photo" />}
          <div className="pv-id">
            <h1>{p.name}</h1>
            <div className="pv-sub">
              {p.team_name} · {(sc.elig_pos || sc.sleeper_pos || p.position || '').split(',').join('/')} · Age {sc.age ?? '—'}
              {p.experience != null ? ` · ${p.experience === 0 ? 'Rookie' : p.experience + ' yr'}` : ''}
              {p.injury_status && p.injury_status !== 'Active' ? <span className="chip-mini gone">{p.injury_status}</span> : null}
            </div>
            {bio && <div className="pv-sub2">{bio}</div>}
          </div>
          <div className="pv-valuebox">
            <div className="v"><span className="dollar">$</span>{Math.round(sc.value)}</div>
            <div className="r">rank #{sc.rank} · {d.tier}</div>
            {sc.sleeper_rank ? <div className="r">Sleeper #{sc.sleeper_rank}{consensus ? ' · ' + consensus : ''}</div> : null}
          </div>
        </div>
      </div>

      <div className="metrics">
        <div className="glass metric"><div className="k">FP/G rank</div><div className="v">{sc.fp_rank ? '#' + sc.fp_rank : '—'}</div><div className="sub">by projected fantasy points</div></div>
        <div className="glass metric"><div className="k">Position rank</div><div className="v">{sc.pos_rank || '—'}</div><div className="sub">at his slot, by value</div></div>
        <div className="glass metric"><div className="k">ROI</div><div className="v">{sc.roi != null ? Number(sc.roi).toFixed(2) : '—'}</div><div className="sub">FP/G per $ {sc.drafted ? 'paid' : 'of value'}</div></div>
        <div className="glass metric"><div className="k">Drafted</div><div className="v">{sc.drafted && sc.draft_price != null ? '$' + Math.round(sc.draft_price) : '—'}</div><div className="sub">{sc.drafted ? 'by ' + (sc.draft_owner || '?') : 'still available'}</div></div>
        <div className="glass metric"><div className="k">Δ to value</div>
          <div className={'v ' + (sc.drafted && sc.market_delta != null ? (sc.market_delta > 0 ? 'up' : sc.market_delta < 0 ? 'down' : '') : '')}>
            {sc.drafted && sc.market_delta != null ? (sc.market_delta > 0 ? '+$' + Math.round(sc.market_delta) : '−$' + Math.abs(Math.round(sc.market_delta))) : '—'}
          </div>
          <div className="sub">{sc.drafted ? 'our value minus price paid' : 'not drafted yet'}</div>
        </div>
      </div>

      <div className="grid2 stretch">
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
          {(sc.name_premium || 0) >= 1 && (
            <div className="pipe-row">
              <span className="lbl"><span className="op">+</span>Name premium<span className="sub">market drafts him #{sc.sleeper_rank} (${Math.round(sc.market_value)})</span></span>
              <span className="val up">+${Math.round(sc.name_premium)}</span>
            </div>
          )}
          <div className="pipe-row final">
            <span className="lbl">Auction value
              <span className="tip">
                <span className="tip-icon">?</span>
                <span className="tip-body">The <b>composite score</b> above is ranked against every player. Only the amount <b>above the last draftable player</b> (replacement level) is worth money. That surplus is steepened so stars pull ahead, then scaled so all {config.n_teams} teams' bids add up to the <b>${config.n_teams * config.budget_per_team} league budget</b>. That is this player's dollar value.</span>
              </span>
            </span>
            <span className="val">${Math.round(sc.value)}</span>
          </div>
        </div>
      </div>

      <div className="glass card">
        <h3>Season history · FP/G trend</h3>
        <CareerBars seasons={seasons} />
        <div className="scroll-x">
          <table className="stat-table">
            <thead><tr>
              {['Season', 'Tm', 'GP', 'MPG', 'PTS', 'REB', 'AST', 'STL', 'BLK', 'TOV', 'FGA', 'FG%', '3PA', '3P%', 'FT%', 'FP/G'].map((h, i) =>
                <th key={h} className={i < 2 ? 'left' : ''}>{h}</th>)}
            </tr></thead>
            <tbody>
              {proj && sc.from_projection && <StatRow label="2026-27" team="proj" s={{ ...proj }} cls="proj-row" computedPct />}
              {seasons.map((s) => <StatRow key={s.season} label={s.season} team={s.team} s={s} />)}
              {seasons.length === 0 && !proj && <tr><td colSpan="16" className="left" style={{ color: 'var(--muted)' }}>No stats or projection available.</td></tr>}
            </tbody>
          </table>
        </div>
      </div>

      {(d.comps?.cheaper?.length || d.comps?.pricier?.length) ? (
        <div className="glass card">
          <h3>Comparable players · ~{f1(sc.production)} FP/G</h3>
          <div className="comps-grid">
            <CompsTable title="Better value" cls="up" rows={d.comps.cheaper} onOpen={onOpen} />
            <CompsTable title="Pricier" cls="down" rows={d.comps.pricier} onOpen={onOpen} />
          </div>
        </div>
      ) : null}

      {d.depth && (
        <div className="glass card">
          <h3>{p.team_name} depth chart</h3>
          <div className="scroll-x">
            <table className="stat-table depth-table">
              <thead><tr>
                <th className="left rowlab"></th>
                {d.depth.positions.map((c) => <th key={c}>{c}</th>)}
              </tr></thead>
              <tbody>
                {d.depth.grid.map((row, i) => (
                  <tr key={i}>
                    <td className="left rowlab">{['1st', '2nd', '3rd'][i] || (i + 1) + 'th'}</td>
                    {row.map((cell, j) => (
                      <td key={j}
                        className={'dslot' + (cell && cell.id_player === p.id_player ? ' me' : '')}
                        onClick={() => cell && cell.id_player !== p.id_player && onOpen && onOpen(cell.id_player)}>
                        {cell ? cell.name : '—'}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
      </div>
    </div>
  )
}
