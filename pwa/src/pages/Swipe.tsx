import { ArrowLeft, Heart, X } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../api'
import { errorText } from '../format'
import type { Pin } from '../types'
import { Notice } from '../ui'

const BATCH = 8
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
  const startX = useRef<number | null>(null)
  const fetching = useRef(false)

  const refill = useCallback(async () => {
    if (fetching.current) return
    fetching.current = true
    try {
      const more = await api.swipeDeck(BATCH)
      if (more.length === 0) setDone(true)
      setDeck((d) => [...d, ...more.filter((m) => !d.some((x) => x.id === m.id))])
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
    }, 180)
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
              <div className="swipe-card under">
                <img src={deck[1].image_url} alt="" />
              </div>
            )}
            <div
              className="swipe-card"
              style={{
                transform: `translateX(${offset}px) rotate(${lean * 6}deg)`,
                transition: startX.current === null ? 'transform 180ms ease-out' : 'none',
              }}
              onPointerDown={(e) => {
                startX.current = e.clientX
                e.currentTarget.setPointerCapture(e.pointerId)
              }}
              onPointerMove={(e) => startX.current !== null && setDx(e.clientX - startX.current)}
              onPointerUp={() => {
                startX.current = null
                if (Math.abs(dx) > THRESHOLD) answer(dx > 0)
                else setDx(0)
              }}
              onPointerCancel={() => {
                startX.current = null
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
