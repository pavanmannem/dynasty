// Generative gradient art per player — deterministic from the player id, but
// constrained to the site palette so every card feels like the same family.

function hash(str) {
  let h = 2166136261
  const s = String(str)
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i)
    h = Math.imul(h, 16777619)
  }
  return h >>> 0
}

// Site palette: warm, muted, editorial — anchored on the brand orange.
// Neighbors in this list are curated to blend well; each gradient uses a
// palette color plus the one next to it.
const PALETTE = [
  { h: 24, s: 72, l: 46 },   // burnt orange (brand)
  { h: 10, s: 58, l: 42 },   // terracotta
  { h: 345, s: 42, l: 38 },  // plum
  { h: 228, s: 38, l: 42 },  // slate blue
  { h: 188, s: 46, l: 34 },  // deep teal
  { h: 150, s: 32, l: 36 },  // moss
]

const hsl = (c, dl = 0, alpha = 1) =>
  `hsl(${c.h} ${c.s}% ${Math.max(8, Math.min(88, c.l + dl))}% / ${alpha})`

export function playerGradient(seed) {
  const h = hash(seed)
  const a = PALETTE[h % PALETTE.length]
  const b = PALETTE[(h % PALETTE.length + 1) % PALETTE.length]
  const x1 = 12 + (h % 46)
  const y1 = 10 + ((h >> 4) % 40)
  const x2 = 55 + ((h >> 6) % 40)
  const y2 = 60 + ((h >> 8) % 35)
  const ang = 100 + ((h >> 2) % 140)
  return (
    `radial-gradient(80% 80% at ${x1}% ${y1}%, ${hsl(a, 14, 0.95)}, transparent 62%),` +
    `radial-gradient(75% 75% at ${x2}% ${y2}%, ${hsl(b, 4, 0.9)}, transparent 58%),` +
    `linear-gradient(${ang}deg, ${hsl(a, -6)}, ${hsl(b, -18)})`
  )
}
