import React, { useEffect, useState } from 'react'
import { getMeta, getPlayers, getDraft, getRoom, getStrategy } from './api.js'
import RankingTable from './components/RankingTable.jsx'
import PlayerView from './components/PlayerView.jsx'
import DraftRoom from './components/DraftRoom.jsx'
import StrategyView from './components/StrategyView.jsx'

const STORE = 'dynasty_config_v1'

export default function App() {
  const [players, setPlayers] = useState([])
  const [meta, setMeta] = useState(null)
  const [config, setConfig] = useState(null)
  const [selected, setSelected] = useState(null)
  const [loading, setLoading] = useState(true)
  const [draft, setDraft] = useState(null)
  const [room, setRoom] = useState(null)
  const [strat, setStrat] = useState(null)
  const [view, setView] = useState('draft')

  // Initialise: pull meta, seed config from localStorage or the bundled defaults.
  useEffect(() => {
    getMeta().then((m) => {
      setMeta(m)
      let cfg = m.config
      try { const s = localStorage.getItem(STORE); if (s) cfg = { ...cfg, ...JSON.parse(s) } } catch (e) {}
      setConfig(cfg)
    })
  }, [])

  // Poll the live Sleeper draft every 15s.
  useEffect(() => {
    let stop = false
    const poll = () => getDraft().then((d) => { if (!stop) setDraft(d) }).catch(() => {})
    poll()
    const iv = setInterval(poll, 15000)
    return () => { stop = true; clearInterval(iv) }
  }, [])

  // Refetch the board + room on config change (debounced) OR when a new pick lands.
  const lastPickNo = draft?.latest?.pick_no ?? null
  useEffect(() => {
    if (!config) return
    const t = setTimeout(() => {
      getPlayers(config).then((p) => { setPlayers(p); setLoading(false) })
      getRoom(config).then(setRoom).catch(() => {})
      getStrategy(config).then(setStrat).catch(() => {})
    }, 220)
    return () => clearTimeout(t)
  }, [config, lastPickNo])

  // The lot moves faster than picks land — keep the room fresh on its own clock too.
  useEffect(() => {
    if (!config) return
    const iv = setInterval(() => {
      getRoom(config).then(setRoom).catch(() => {})
      getStrategy(config).then(setStrat).catch(() => {})
    }, 15000)
    return () => clearInterval(iv)
  }, [config])

  if (loading || !config) return <div className="app"><div className="loading">Loading…</div></div>

  return (
    <div className="app">
      <div className="topbar">
        <div className="brand">dynasty maxxing</div>
        <div className="tabs">
          {['draft', 'players', 'strategy'].map((t) => (
            <button key={t} className={'tab' + (view === t ? ' active' : '')} onClick={() => setView(t)}>{t}</button>
          ))}
        </div>
      </div>

      {view === 'draft' && <DraftRoom room={room} onOpen={setSelected} />}
      {view === 'players' && <RankingTable players={players} onSelect={setSelected} />}
      {view === 'strategy' && <StrategyView data={strat} onOpen={setSelected} />}
      {selected && <PlayerView key={selected} id={selected} config={config} onBack={() => setSelected(null)} onOpen={setSelected} />}
    </div>
  )
}
