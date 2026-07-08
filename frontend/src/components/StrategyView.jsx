import React from 'react'

const $ = (x) => (x == null ? '—' : '$' + Math.round(x))

function TargetRow({ t, onOpen, suggest }) {
  return (
    <tr onClick={() => onOpen(t.id_player)}>
      <td className="left">
        <span className="comp-cell">
          <span className="art sm">{t.headshot && <img src={t.headshot} alt="" loading="lazy" />}</span>
          <span className="comp-name">{t.name}</span>
          <span className="comp-team">{t.pos}{t.age != null ? ' · ' + t.age : ''}</span>
        </span>
      </td>
      <td className="num">{t.production.toFixed(1)}</td>
      <td className="num"><span className="nowv">{$(t.adj_value)}</span></td>
      <td className="num"><span className="expv">{$(t.exp_price)}</span></td>
      {suggest && <td className="num"><span className="value"><span className="dollar">$</span>{t.suggest}</span></td>}
      <td className="num">{t.edge.toFixed(1)}</td>
      <td className="left hide-sm">
        {t.badges.map((b) => (
          <span key={b} className={'chip-mini' + (/Out|OFS|Day-To-Day/.test(b) ? ' gone' : '')}>{b}</span>
        ))}
      </td>
    </tr>
  )
}

export default function StrategyView({ data, onOpen }) {
  if (!data) return <div className="loading">Loading…</div>
  const me = data.me
  if (!me) return <div className="loading">No draft slot found for me.</div>

  const spentOnPlan = data.planned_spend
  const needChips = Object.entries(data.needs || {}).map(([k, v]) => `${k}${v > 1 ? ' ×' + v : ''}`)

  return (
    <div className="fade">
      <div className="metrics">
        <div className="glass metric"><div className="k">Budget left</div><div className="v">{$(me.left)}</div><div className="sub">of $400 · {me.open_slots} slots open</div></div>
        <div className="glass metric"><div className="k">Max single bid</div><div className="v">{$(me.max_bid)}</div><div className="sub">keeping $1 per open slot</div></div>
        <div className="glass metric"><div className="k">Market</div><div className="v">{data.inflation.toFixed(2)}×</div><div className="sub">live price level vs pre-draft</div></div>
        <div className="glass metric"><div className="k">Starting slots open</div><div className="v">{needChips.length ? needChips.join(' · ') : 'all filled'}</div><div className="sub">rest goes to bench</div></div>
      </div>

      <div className="glass card">
        <h3>My roster so far · {$(me.spent)} spent for {$(me.value_won)} of value</h3>
        <div className="scroll-x">
          <table className="stat-table">
            <thead><tr><th className="left">Player</th><th className="left">Slot</th><th>Paid</th><th>Value</th><th>Δ</th></tr></thead>
            <tbody>
              {me.picks.map((p) => (
                <tr key={p.name} onClick={() => p.id_player && onOpen(p.id_player)} style={{ cursor: 'pointer' }}>
                  <td className="left">{p.name}</td>
                  <td className="left"><span className="chip-mini">{p.fills}</span></td>
                  <td className="num"><span className="paid" style={{ fontSize: 14 }}>{$(p.amount)}</span></td>
                  <td className="num">{$(p.value)}</td>
                  <td className={'num ' + (p.delta > 0 ? 'up' : p.delta < 0 ? 'down' : '')}>{p.delta > 0 ? '+' : ''}{p.delta}</td>
                </tr>
              ))}
              {me.picks.length === 0 && <tr><td colSpan="5" className="left" style={{ color: 'var(--muted)' }}>No picks yet.</td></tr>}
            </tbody>
          </table>
        </div>
      </div>

      <div className="glass card">
        <h3>The plan · {me.open_slots} picks with {$(me.left)} — suggested {$(spentOnPlan)}</h3>
        <div className="strategy-note">Ranked by edge = (live value − expected price) + minutes security (depth chart) + age upside + health + filling an open starting slot.</div>
        <div className="scroll-x">
          <table className="stat-table">
            <thead><tr>
              <th className="left">Target</th><th>FP/G</th><th>Now</th><th>Exp</th><th>Bid up to</th><th>Edge</th><th className="left hide-sm">Why</th>
            </tr></thead>
            <tbody>
              {data.plan.map((t) => <TargetRow key={t.id_player} t={t} onOpen={onOpen} suggest />)}
            </tbody>
          </table>
        </div>
      </div>

      {data.more?.length > 0 && (
        <div className="glass card">
          <h3>Next up if the plan gets sniped</h3>
          <div className="scroll-x">
            <table className="stat-table">
              <thead><tr>
                <th className="left">Target</th><th>FP/G</th><th>Now</th><th>Exp</th><th>Edge</th><th className="left hide-sm">Why</th>
              </tr></thead>
              <tbody>
                {data.more.map((t) => <TargetRow key={t.id_player} t={t} onOpen={onOpen} />)}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  )
}
