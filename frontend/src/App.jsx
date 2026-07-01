import React, { useEffect, useState, useCallback } from 'react'
import { getMeta, getPlayers } from './api.js'
import RankingTable from './components/RankingTable.jsx'
import PlayerView from './components/PlayerView.jsx'

const STORE = 'dynasty_config_v1'

export default function App() {
  const [players, setPlayers] = useState([])
  const [meta, setMeta] = useState(null)
  const [config, setConfig] = useState(null)
  const [selected, setSelected] = useState(null)
  const [loading, setLoading] = useState(true)

  // Initialise: pull meta, seed config from localStorage or the bundled defaults.
  useEffect(() => {
    getMeta().then((m) => {
      setMeta(m)
      let cfg = m.config
      try { const s = localStorage.getItem(STORE); if (s) cfg = { ...cfg, ...JSON.parse(s) } } catch (e) {}
      setConfig(cfg)
    })
  }, [])

  // Refetch players whenever config changes (debounced for slider drags).
  useEffect(() => {
    if (!config) return
    const t = setTimeout(() => {
      getPlayers(config).then((p) => { setPlayers(p); setLoading(false) })
    }, 220)
    return () => clearTimeout(t)
  }, [config])

  const onConfigChange = useCallback((patch) => {
    setConfig((c) => {
      const next = { ...c, ...patch }
      try { localStorage.setItem(STORE, JSON.stringify(next)) } catch (e) {}
      return next
    })
  }, [])

  if (loading || !config) return <div className="app"><div className="loading">Loading…</div></div>

  return (
    <div className="app">
      <div className="topbar">
        <div className="brand"><span className="logo-orb" />dynasty</div>
      </div>

      {selected ? (
        <PlayerView key={selected} id={selected} config={config} onBack={() => setSelected(null)} />
      ) : (
        <RankingTable players={players} config={config} onConfigChange={onConfigChange} onSelect={setSelected} />
      )}
    </div>
  )
}
