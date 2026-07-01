// Generative abstract gradient art — a unique, deterministic "cover" per player,
// echoing the album-art / moodboard aesthetic of the inspiration.

function hash(str) {
  let h = 2166136261
  const s = String(str)
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i)
    h = Math.imul(h, 16777619)
  }
  return h >>> 0
}

export function playerGradient(seed) {
  const h = hash(seed)
  const hue = h % 360
  const hue2 = (hue + 35 + ((h >> 3) % 70)) % 360
  const hue3 = (hue + 165 + ((h >> 5) % 70)) % 360
  const x1 = 12 + (h % 46)
  const y1 = 10 + ((h >> 4) % 40)
  const x2 = 55 + ((h >> 6) % 40)
  const y2 = 60 + ((h >> 8) % 35)
  const ang = (h >> 2) % 360
  return (
    `radial-gradient(80% 80% at ${x1}% ${y1}%, hsl(${hue} 88% 64% / 0.95), transparent 62%),` +
    `radial-gradient(75% 75% at ${x2}% ${y2}%, hsl(${hue3} 82% 56% / 0.9), transparent 58%),` +
    `linear-gradient(${ang}deg, hsl(${hue2} 74% 46%), hsl(${hue} 68% 26%))`
  )
}

// A soft accent color derived from the same seed (for glows / rings).
export function playerAccent(seed) {
  return `hsl(${hash(seed) % 360} 85% 66%)`
}
