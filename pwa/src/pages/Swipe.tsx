import { ArrowLeft, Heart, X } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../api'
import { errorText } from '../format'
import type { Pin } from '../types'
import { Notice } from '../ui'

const BATCH = 24
const WANTED = 8

const MEN = /\b(men|mens|men's|man|male|guys?|menswear|masculine|him|his|boyfriend|gentlem[ae]n)\b/i
const WOMEN = /\b(women|womens|women's|woman|female|girls?|ladies|lady|womenswear|feminine|she|her|skirts?|dress(es)?|heels|blouse|mary janes?)\b/i

/**
 * The deck comes from Pinterest searches per style, and the backend only filters whole styles by audience, so a
 * unisex style such as Minimalism still brings looks for the other audience. Keep only pins whose title says they
 * are for this user's audience. Pins with no telling title are dropped: better fewer looks than wrong ones.
 */
function fitsAudience(pin: Pin, audience: string | undefined): boolean {
  const text = `${pin.title || ''}`
  if (audience === 'menswear') return MEN.test(text) && !WOMEN.test(text)
  if (audience === 'womenswear') return WOMEN.test(text) && !MEN.test(text)
  return true
}
const THRESHOLD = 90

const CACHE_KEY = 'swipe-deck-v1'
const readCache = (): Pin[] => {
  try {
    return JSON.parse(localStorage.getItem(CACHE_KEY) || '[]')
  } catch {
    return []
  }
}
const writeCache = (deck: Pin[]) => {
  try {
    localStorage.setItem(CACHE_KEY, JSON.stringify(deck.slice(0, 40)))
  } catch {
    /* storage unavailable: the deck is simply fetched again next time */
  }
}
// The same picture can sit in the library under several pin ids; treat those as one look.
const same = (a: Pin, b: Pin) => a.id === b.id || a.image_url === b.image_url
const merge = (a: Pin[], b: Pin[]) => b.reduce((all, m) => (all.some((x) => same(x, m)) ? all : [...all, m]), a)

/** Pinterest serves a 736px version of every picture; it loads several times faster than the original. */
const small = (url: string) => url.replace('/originals/', '/736x/').replace(/\.(png|webp)$/, '.jpg')

// The deck lives outside the component so it is ready before the screen opens and survives leaving it.
let memory: Pin[] = merge([], readCache())
let warming: Promise<void> | null = null
let audience: string | null | undefined = null
const seen = new Map<string, Pin>()

/** Fetches the next looks for this user's audience. Falls back to looks swiped before when the server has none. */
async function collect(): Promise<Pin[]> {
  if (audience === null) audience = await api.user().then((u) => u.fit_prefs?.audience, () => undefined)
  const fresh: Pin[] = []
  const spare: Pin[] = []
  // Many pins are filtered out, so ask for a few batches at most; each pin served is marked as seen.
  for (let round = 0; round < 3 && fresh.length < WANTED; round++) {
    const more = await api.swipeDeck(BATCH)
    if (more.length === 0) break
    fresh.push(...more.filter((m) => fitsAudience(m, audience ?? undefined)))
    spare.push(...more.filter((m) => !fitsAudience(m, audience ?? undefined)))
  }
  if (fresh.length === 0 && seen.size === 0) {
    const [liked, skipped] = await Promise.all([api.likedPins().catch(() => []), api.skippedPins().catch(() => [])])
    const old = [...liked, ...skipped]
      .filter((m) => m.image_url)
      .map((m) => ({ ...m, id: m.pin_id || m.id, reason: m.reason || 'One more look at this one' }))
    const mine = old.filter((m) => fitsAudience(m, audience ?? undefined))
    fresh.push(...(mine.length >= 3 ? mine : old.length ? old : spare))
  }
  fresh.forEach((m) => seen.set(m.id, m))
  return fresh
}

/** If the small version does not exist, show the original once. */
function fallback(img: HTMLImageElement, original: string) {
  if (img.src !== original) img.src = original
}

/** Call early (app start) so the swipe screen opens with cards already there. */
export function warmDeck(): void {
  if (warming || memory.length >= 7) return
  warming = collect()
    .then((pins) => {
      memory = merge(memory, pins)
      writeCache(memory)
      pins.slice(0, 3).forEach((p) => {
        new Image().src = small(p.image_url)
      })
    })
    .catch(() => undefined)
    .finally(() => {
      warming = null
    })
}

/** Swipe looks left or right. Each answer teaches the backend which styles the user likes. */
export default function Swipe({ onBack }: { onBack: () => void }) {
  const [deck, setDeck] = useState<Pin[]>(memory)
  const [loading, setLoading] = useState(memory.length === 0)
  const [done] = useState(false)
  const [error, setError] = useState('')
  const [count, setCount] = useState({ liked: 0, total: 0 })
  const [dx, setDx] = useState(0)
  const [leaving, setLeaving] = useState<0 | 1 | -1>(0)
  const [dragging, setDragging] = useState(false)
  const startX = useRef<number | null>(null)
  const fetching = useRef(false)

  const refill = useCallback(async () => {
    if (fetching.current) return
    fetching.current = true
    try {
      if (warming) await warming
      else memory = merge(memory, await collect())
      setDeck((d) => {
        const next = merge(d, memory)
        if (next.length > d.length) return next
        // Nothing new: go round again through what was already shown, so the deck never ends.
        return merge(d, [...seen.values()].sort(() => Math.random() - 0.5))
      })
      setError('')
    } catch (e) {
      setError(errorText(e))
    } finally {
      fetching.current = false
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (deck.length < 7) refill()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refill])

  // Keep what is left for the next visit, and fetch the next pictures before they are needed.
  useEffect(() => {
    memory = deck
    writeCache(deck)
    deck.slice(1, 4).forEach((p) => {
      new Image().src = small(p.image_url)
    })
  }, [deck])

  const pin = deck[0]

  function answer(liked: boolean) {
    if (!pin || leaving) return
    setLeaving(liked ? 1 : -1)
    seen.set(pin.id, pin)
    api.swipe(pin.id, liked).catch((e) => setError(`Not saved: ${errorText(e)}`))
    setCount((c) => ({ liked: c.liked + (liked ? 1 : 0), total: c.total + 1 }))
    setTimeout(() => {
      setDeck((d) => {
        const rest = d.slice(1)
        // Fetch more well before the deck runs out; if it still runs out, show earlier looks at once, never wait.
        if (rest.length <= 6) refill()
        if (rest.length > 0) return rest
        return merge([], [...seen.values()].filter((m) => !d[0] || !same(m, d[0])).sort(() => Math.random() - 0.5))
      })
      setLeaving(0)
      setDx(0)
    }, 140)
  }

  const offset = leaving ? leaving * 420 : dx
  const lean = Math.max(-1, Math.min(1, offset / THRESHOLD))

  return (
    <div className="page swipe-page">
      <header className="detail-head">
        <button className="icon-btn" onClick={onBack} aria-label="Back to My Style">
          <ArrowLeft size={22} />
        </button>
        <span className="muted">{count.total > 0 && `${count.liked} liked of ${count.total}`}</span>
      </header>
      <div>
        <h1>What you like</h1>
        <p className="lead">Like or skip. A few swipes are enough to sharpen your style.</p>
      </div>
      {error && <Notice kind="error">{error}</Notice>}

      {loading && <div className="swipe-card skeleton" />}

      {!loading && pin && (
        <>
          <div className="swipe-stack">
            {deck[1] && (
              <div className="swipe-card under" key={`under-${deck[1].id}`}>
                <img src={small(deck[1].image_url)} alt="" onError={(e) => fallback(e.currentTarget, deck[1].image_url)} />
              </div>
            )}
            {/* Keyed by pin: the next card mounts fresh in the centre instead of sliding back from where the last one left. */}
            <div
              key={pin.id}
              className="swipe-card top"
              style={{
                transform: `translateX(${offset}px) rotate(${lean * 6}deg)`,
                opacity: leaving ? 0 : 1,
                transition: dragging ? 'none' : 'transform 140ms ease-out, opacity 140ms ease-out',
              }}
              onPointerDown={(e) => {
                if (leaving) return
                startX.current = e.clientX
                setDragging(true)
                e.currentTarget.setPointerCapture(e.pointerId)
              }}
              onPointerMove={(e) => startX.current !== null && setDx(e.clientX - startX.current)}
              onPointerUp={() => {
                if (startX.current === null) return
                startX.current = null
                setDragging(false)
                if (Math.abs(dx) > THRESHOLD) answer(dx > 0)
                else setDx(0)
              }}
              onPointerCancel={() => {
                startX.current = null
                setDragging(false)
                setDx(0)
              }}
            >
              <img src={small(pin.image_url)} alt={pin.title || pin.style_name} draggable={false} onError={(e) => fallback(e.currentTarget, pin.image_url)} />
              {lean > 0.3 && <span className="stamp like">Like</span>}
              {lean < -0.3 && <span className="stamp skip">Skip</span>}
              <div className="swipe-caption">
                <strong>{pin.style_name}</strong>
                <span>{pin.reason}</span>
              </div>
            </div>
          </div>
          <div className="swipe-actions">
            <button className="round" onClick={() => answer(false)} aria-label="Skip this look">
              <X size={28} />
            </button>
            <button className="round like" onClick={() => answer(true)} aria-label="Like this look">
              <Heart size={28} />
            </button>
          </div>
        </>
      )}

      {!loading && !pin && (
        <div className="empty">
          <p>{done ? 'You have seen every look for now.' : 'No looks loaded.'}</p>
          {!done && (
            <button className="btn" onClick={refill}>
              Try again
            </button>
          )}
          <button className="btn primary" onClick={onBack}>
            Back to My Style
          </button>
        </div>
      )}
    </div>
  )
}
