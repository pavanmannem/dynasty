import React, { useState } from 'react'

const $ = (x) => (x == null ? '—' : '$' + Math.round(x))
const sd = (x) => (x > 0 ? '+$' + Math.round(x) : x < 0 ? '−$' + Math.abs(Math.round(x)) : '$0')

function MiniList({ title, rows, onOpen, price }) {
  return (
    <div className="room-list">
      <div className="room-list-head">{title}</div>
      {rows.length === 0 ? <div className="comps-empty">Nothing obvious</div> : rows.map((t) => (
        <div className="room-target" key={t.id_player} onClick={() => t.id_player && onOpen(t.id_player)}>
          <span className="art sm">{t.headshot && <img src={t.headshot} alt="" loading="lazy" />}</span>
          <span className="rt-name">{t.name}</span>
          <span className="rt-nums">{price(t)}</span>
        </div>
      ))}
    </div>
  )
}

export default function DraftRoom({ room, onOpen }) {
  const [open, setOpen] = useState(true)
  const [showOwner, setShowOwner] = useState(null)
  if (!room || !room.owners?.length) return null

  const lot = room.lot
  const lotEdge = lot && lot.adj_value != null ? lot.adj_value - lot.bid : null
  const mins = lot?.timer_end ? Math.max(0, Math.round((new Date(lot.timer_end) - Date.now()) / 60000)) : null
  const me = room.owners.find((o) => o.me)

  return (
    <div className="glass room fade">
      <div className="room-head" onClick={() => setOpen((o) => !o)}>
        <span className="room-title">Draft room</span>
        {room.status === 'drafting' && <span className="chip-live">LIVE</span>}
        <span className="room-stat"><b>{room.inflation.toFixed(2)}×</b> market</span>
        <span className="room-stat">{$(room.money_left)} left · {room.slots_left} slots</span>
        {me && <span className="room-stat">my max bid <b>{$(me.max_bid)}</b></span>}
        <span className="room-chev">{open ? '▾' : '▸'}</span>
      </div>

      {open && (
        <div className="room-body">
          {lot && lot.name && (
            <div className="lot">
              <span className="art sm">{lot.headshot && <img src={lot.headshot} alt="" />}</span>
              <span className="lot-name" onClick={() => onOpen(lot.id_player)}>{lot.name}</span>
              <span className="lot-bid">bid {$(lot.bid)}{lot.leader ? ' · ' + lot.leader : ''}</span>
              <span className="lot-val">worth {$(lot.adj_value)} now</span>
              {lotEdge != null && (
                <span className={'lot-verdict ' + (lotEdge > 0 ? 'up' : 'down')}>
                  {lotEdge > 0 ? 'BARGAIN ' : 'OVERPAY '}{sd(lotEdge)}
                </span>
              )}
              {mins != null && <span className="lot-timer">⏱ {mins}m</span>}
              <span className="lot-passed">{lot.passed} passed</span>
            </div>
          )}

          <div className="scroll-x">
            <table className="stat-table room-table">
              <thead><tr>
                <th className="left">Owner</th><th>Spent</th><th>Left</th><th>Max bid</th>
                <th>Open</th><th>Value won</th><th>Surplus</th>
              </tr></thead>
              <tbody>
                {room.owners.map((o) => (
                  <React.Fragment key={o.user_id}>
                    <tr className={o.me ? 'me-row' : ''}
                      onClick={() => setShowOwner(showOwner === o.user_id ? null : o.user_id)}>
                      <td className="left">{o.name}{o.me ? ' ★' : ''}</td>
                      <td className="num">{$(o.spent)}</td>
                      <td className="num">{$(o.left)}</td>
                      <td className="num"><b>{$(o.max_bid)}</b></td>
                      <td className="num">{o.open_slots}</td>
                      <td className="num">{$(o.value_won)}</td>
                      <td className={'num ' + (o.surplus > 0 ? 'up' : o.surplus < 0 ? 'down' : '')}>{sd(o.surplus)}</td>
                    </tr>
                    {showOwner === o.user_id && (
                      <tr className="owner-picks"><td colSpan="7" className="left">
                        {o.picks.length === 0 ? 'No picks yet' : o.picks.map((p) => (
                          <span className="opick" key={p.name} onClick={(e) => { e.stopPropagation(); p.id_player && onOpen(p.id_player) }}>
                            {p.name} <b>{$(p.amount)}</b>
                            {p.delta != null && <span className={p.delta >= 0 ? 'up' : 'down'}> {sd(p.delta)}</span>}
                          </span>
                        ))}
                      </td></tr>
                    )}
                  </React.Fragment>
                ))}
              </tbody>
            </table>
          </div>

          <div className="room-cols">
            <MiniList title="Buy now — value vs likely price" rows={room.targets} onOpen={onOpen}
              price={(t) => <>{$(t.adj_value)} <span className="rt-exp">for ~{$(t.exp_price)}</span></>} />
            <MiniList title="Nominate to drain — room pays over our number" rows={room.nominate} onOpen={onOpen}
              price={(t) => <>{$(t.value)} <span className="rt-exp">mkt {$(t.exp_price)}</span></>} />
            <div className="room-list">
              <div className="room-list-head">Left on the board</div>
              {Object.entries(room.supply).map(([pos, s]) => (
                <div className="supply-row" key={pos}>
                  <span className="sp-pos">{pos}</span>
                  <span className="sp-cnt">{s.star}★ · {s.starter} starters</span>
                  <span className="sp-top">{s.top.join(', ')}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
