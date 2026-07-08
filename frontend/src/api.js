const json = (r) => {
  if (!r.ok) throw new Error('HTTP ' + r.status)
  return r.json()
}

// Config lives in the browser and is passed per request, so the backend stays
// stateless/read-only (deployable as serverless functions).
const q = (config) => (config ? '?config=' + encodeURIComponent(JSON.stringify(config)) : '')

export const getMeta = () => fetch('/api/meta').then(json)
export const getPlayers = (config) => fetch('/api/players' + q(config)).then(json)
export const getPlayer = (id, config) => fetch('/api/players/' + id + q(config)).then(json)
export const getDraft = () => fetch('/api/draft').then(json)
export const getRoom = (config) => fetch('/api/room' + q(config)).then(json)
export const getStrategy = (config) => fetch('/api/strategy' + q(config)).then(json)
