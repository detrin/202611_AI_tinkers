import { ArrowLeft, Heart, X } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../api'
import { errorText } from '../format'
import type { Pin } from '../types'
import { Notice } from '../ui'

const BATCH = 24
const WANTED = 6

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

/** Swipe looks left or right. Each answer teaches the backend which styles the user likes. */
export default function Swipe({ onBack }: { onBack: () => void }) {
  const [deck, setDeck] = useState<Pin[]>([])
  const [loading, setLoading] = useState(true)
  const [done, setDone] = useState(false)
  const [error, setError] = useState('')
  const [count, setCount] = useState({ liked: 0, total: 0 })
  const [dx, setDx] = useState(0)
  const [leaving, setLeaving] = useState<0 | 1 | -1>(0)
  const [dragging, setDragging] = useState(false)
  const startX = useRef<number | null>(null)
  const fetching = useRef(false)
  const audience = useRef<string | null | undefined>(null)

  const refill = useCallback(async () => {
    if (fetching.current) return
    fetching.current = true
    try {
      if (audience.current === null) {
        audience.current = await api.user().then((u) => u.fit_prefs?.audience, () => undefined)
      }
      const fresh: Pin[] = []
      // Ask for a few batches at most: many pins are filtered out, and each one served is marked as seen.
      for (let round = 0; round < 3 && fresh.length < WANTED; round++) {
        const more = await api.swipeDeck(BATCH)
        if (more.length === 0) {
          setDone(true)
          break
        }
        fresh.push(...more.filter((m) => fitsAudience(m, audience.current ?? undefined)))
      }
      setDeck((d) => [...d, ...fresh.filter((m) => !d.some((x) => x.id === m.id))])
      setError('')
    } catch (e) {
      setError(errorText(e))
    } finally {
      fetching.current = false
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    refill()
  }, [refill])

  const pin = deck[0]

  function answer(liked: boolean) {
    if (!pin || leaving) return
    setLeaving(liked ? 1 : -1)
    api.swipe(pin.id, liked).catch((e) => setError(`Not saved: ${errorText(e)}`))
    setCount((c) => ({ liked: c.liked + (liked ? 1 : 0), total: c.total + 1 }))
    setTimeout(() => {
      setDeck((d) => {
        const rest = d.slice(1)
        if (rest.length <= 2 && !done) refill()
        return rest
      })
      setLeaving(0)
      setDx(0)
    }, 220)
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
                <img src={deck[1].image_url} alt="" />
              </div>
            )}
            {/* Keyed by pin: the next card mounts fresh in the centre instead of sliding back from where the last one left. */}
            <div
              key={pin.id}
              className="swipe-card top"
              style={{
                transform: `translateX(${offset}px) rotate(${lean * 6}deg)`,
                opacity: leaving ? 0 : 1,
                transition: dragging ? 'none' : 'transform 220ms ease-out, opacity 220ms ease-out',
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
              <img src={pin.image_url} alt={pin.title || pin.style_name} draggable={false} />
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
