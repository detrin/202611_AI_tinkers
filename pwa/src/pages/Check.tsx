import { ArrowRight, Camera, Check, CloudSun, ImagePlus, MapPin, Shirt, X } from 'lucide-react'
import { useEffect, useRef, useState, type CSSProperties } from 'react'
import { api } from '../api'
import { errorText, itemName } from '../format'
import type { Item, LookVerdict } from '../types'
import { Notice } from '../ui'

type Phase = 'pick' | 'checking' | 'result'

const MIN_SCAN_MS = 1800

const CHECKING_LINES = ['Looking at the fit', 'Reading the colours', 'Checking the proportions', 'Thinking about the weather', 'Making up my mind']

/**
 * "Is it good enough?": a photo of the look you have on → hell yeah / hell nah, with the reasons.
 * Weather is used only when the phone shares its position (or the saved city as a fallback).
 * The closet is only compared when the user switches it on.
 */
export default function CheckLook({ occasion, onClose }: { occasion?: string; onClose: () => void }) {
  const [phase, setPhase] = useState<Phase>('pick')
  const [photo, setPhoto] = useState<File | null>(null)
  const [preview, setPreview] = useState('')
  const [useWeather, setUseWeather] = useState(true)
  const [useCloset, setUseCloset] = useState(false)
  const [result, setResult] = useState<LookVerdict | null>(null)
  const [error, setError] = useState('')
  const camera = useRef<HTMLInputElement>(null)
  const gallery = useRef<HTMLInputElement>(null)

  useEffect(() => () => { if (preview) URL.revokeObjectURL(preview) }, [preview])
  useEffect(() => {
    const before = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => { document.body.style.overflow = before }
  }, [])

  function choose(files: FileList | null) {
    const file = files?.[0]
    if (!file) return
    setPhoto(file)
    setPreview(URL.createObjectURL(file))
    setResult(null)
    setError('')
    setPhase('pick')
  }

  async function check() {
    if (!photo) return
    setPhase('checking')
    setError('')
    try {
      const [small, position] = await Promise.all([shrink(photo), useWeather ? locate() : Promise.resolve(null)])
      // The scan runs at least a moment even on a fast answer, so the verdict lands instead of flickering in.
      const [verdict] = await Promise.all([
        api.checkLook(small, { position, useSavedCity: useWeather && !position, includeWardrobe: useCloset, occasion }),
        new Promise((r) => setTimeout(r, MIN_SCAN_MS)),
      ])
      setResult(verdict)
      setPhase('result')
      navigator.vibrate?.(verdict.good_enough ? [20, 60, 20, 60, 40] : [90])
    } catch (e) {
      setError(errorText(e))
      setPhase('pick')
    }
  }

  function again() {
    setPhoto(null)
    setPreview('')
    setResult(null)
    setPhase('pick')
    camera.current?.click()
  }

  return (
    <div className="check" role="dialog" aria-label="Is it good enough?">
      <header className="check-head">
        <div>
          <p className="eyebrow">Before you leave</p>
          <h1>Is it good enough?</h1>
        </div>
        <button className="icon-btn" onClick={onClose} aria-label="Close">
          <X size={22} />
        </button>
      </header>

      <input ref={camera} type="file" accept="image/*" capture="user" hidden onChange={(e) => choose(e.target.files)} />
      <input ref={gallery} type="file" accept="image/*" hidden onChange={(e) => choose(e.target.files)} />

      {!preview && (
        <button className="snap" onClick={() => camera.current?.click()}>
          <span className="snap-ring">
            <Camera size={34} strokeWidth={1.5} />
          </span>
          <strong>Take a mirror photo</strong>
          <span>Head to toe works best</span>
        </button>
      )}

      {preview && (
        <Frame
          src={preview}
          scanning={phase === 'checking'}
          verdict={phase === 'result' ? result : null}
          onRetake={phase === 'pick' ? () => camera.current?.click() : undefined}
        />
      )}

      {phase === 'checking' && <Ticker lines={CHECKING_LINES} />}
      {error && <Notice kind="error">{error}</Notice>}

      {phase === 'pick' && (
        <>
          <div className="toggles">
            <Toggle icon={MapPin} label="Weather where I am" hint="Uses your position, or your city" on={useWeather} onChange={setUseWeather} />
            <Toggle icon={Shirt} label="Compare with my closet" hint="Suggests swaps from what you own" on={useCloset} onChange={setUseCloset} />
          </div>
          {preview ? (
            <button className="btn primary big" onClick={check}>
              Is it good enough?
            </button>
          ) : (
            <button className="btn" onClick={() => gallery.current?.click()}>
              <ImagePlus size={18} /> Choose from photos
            </button>
          )}
        </>
      )}

      {phase === 'result' && result && <Reasons verdict={result} onAgain={again} onDone={onClose} />}
    </div>
  )
}

function Frame({ src, scanning, verdict, onRetake }: { src: string; scanning: boolean; verdict: LookVerdict | null; onRetake?: () => void }) {
  const tone = verdict ? (verdict.good_enough ? 'yeah' : 'nah') : ''
  return (
    <div className={`frame ${scanning ? 'scanning' : ''} ${tone}`}>
      <img src={src} alt="Your look" />
      {scanning && (
        <>
          <i className="scanline" />
          <i className="corner tl" />
          <i className="corner tr" />
          <i className="corner bl" />
          <i className="corner br" />
        </>
      )}
      {verdict && (
        <>
          <i className="shock" />
          {verdict.good_enough && <Confetti />}
          <div className="verdict-stamp" aria-live="polite">
            {verdict.good_enough ? 'Hell yeah' : 'Hell nah'}
          </div>
        </>
      )}
      {onRetake && (
        <button className="retake" onClick={onRetake}>
          <Camera size={16} /> Retake
        </button>
      )}
    </div>
  )
}

const PIECES = Array.from({ length: 22 }, (_, i) => {
  const angle = (i / 22) * Math.PI * 2 + (i % 3) * 0.3
  const dist = 120 + ((i * 37) % 90)
  return { dx: Math.cos(angle) * dist, dy: Math.sin(angle) * dist - 40, r: (i * 47) % 360, d: (i % 5) * 25, k: i % 3 }
})

function Confetti() {
  return (
    <div className="confetti" aria-hidden>
      {PIECES.map((p, i) => (
        <i
          key={i}
          className={`c${p.k}`}
          style={{ '--dx': `${p.dx}px`, '--dy': `${p.dy}px`, '--r': `${p.r}deg`, '--d': `${p.d}ms` } as CSSProperties}
        />
      ))}
    </div>
  )
}

function Reasons({ verdict, onAgain, onDone }: { verdict: LookVerdict; onAgain: () => void; onDone: () => void }) {
  const score = useCountUp(verdict.score_1to10 ?? 0, 900, 450)
  const swaps = useSwaps(verdict.swap_item_ids)
  const w = verdict.weather
  const temp = w?.current?.temperature_2m
  let n = 0
  const step = () => ({ '--i': n++ }) as CSSProperties

  return (
    <section className={`reasons ${verdict.good_enough ? 'yeah' : 'nah'}`}>
      <div className="score-row" style={step()}>
        {verdict.score_1to10 != null && (
          <div className="score" style={{ '--p': (verdict.score_1to10 / 10).toFixed(2) } as CSSProperties}>
            <svg viewBox="0 0 64 64" aria-hidden>
              <circle cx="32" cy="32" r="28" />
              <circle cx="32" cy="32" r="28" className="arc" />
            </svg>
            <b>{score}</b>
          </div>
        )}
        <p className="explanation">{verdict.explanation}</p>
      </div>

      {(w || verdict.weather_note) && (
        <p className="weather-chip" style={step()}>
          <CloudSun size={18} />
          <span>
            {temp != null && `${Math.round(temp)}°C${w?.city ? ` in ${w.city}` : ' where you are'}`}
            {temp != null && verdict.weather_note && ' · '}
            {verdict.weather_note}
          </span>
        </p>
      )}

      {verdict.highlights.length > 0 && (
        <ul className="points good">
          {verdict.highlights.map((h) => (
            <li key={h} style={step()}>
              <Check size={18} />
              <span>{h}</span>
            </li>
          ))}
        </ul>
      )}

      {verdict.fixes.length > 0 && (
        <>
          <h3 style={step()}>{verdict.good_enough ? 'To make it even better' : 'What would fix it'}</h3>
          <ul className="points fix">
            {verdict.fixes.map((f) => (
              <li key={f} style={step()}>
                <ArrowRight size={18} />
                <span>{f}</span>
              </li>
            ))}
          </ul>
        </>
      )}

      {swaps.length > 0 && (
        <div className="swaps" style={step()}>
          <h3>Swap in from your closet</h3>
          <div className="swap-row">
            {swaps.map((item) => (
              <figure key={item.id}>
                <div className="photo">{item.image_url ? <img src={item.image_url} alt={itemName(item)} /> : <span>{itemName(item)}</span>}</div>
                <figcaption>{itemName(item)}</figcaption>
              </figure>
            ))}
          </div>
        </div>
      )}

      <div className="actions" style={step()}>
        <button className="btn primary" onClick={onAgain}>
          <Camera size={18} /> Check another
        </button>
        <button className="btn" onClick={onDone}>
          Done
        </button>
      </div>
    </section>
  )
}

function Toggle({ icon: Icon, label, hint, on, onChange }: {
  icon: typeof MapPin; label: string; hint: string; on: boolean; onChange: (v: boolean) => void
}) {
  return (
    <label className="toggle">
      <Icon size={20} />
      <span>
        <strong>{label}</strong>
        <small>{hint}</small>
      </span>
      <input type="checkbox" role="switch" checked={on} onChange={(e) => onChange(e.target.checked)} />
    </label>
  )
}

function Ticker({ lines }: { lines: string[] }) {
  const [i, setI] = useState(0)
  useEffect(() => {
    const t = setInterval(() => setI((x) => (x + 1) % lines.length), 1600)
    return () => clearInterval(t)
  }, [lines.length])
  return (
    <p className="ticker" aria-live="polite">
      <span key={i}>{lines[i]}…</span>
    </p>
  )
}

function useCountUp(target: number, ms: number, delay: number) {
  const [v, setV] = useState(0)
  useEffect(() => {
    if (matchMedia('(prefers-reduced-motion: reduce)').matches) return setV(target)
    let raf = 0
    const start = performance.now() + delay
    const tick = (now: number) => {
      const t = Math.min(1, Math.max(0, (now - start) / ms))
      setV(Math.round(target * (1 - (1 - t) ** 3)))
      if (t < 1) raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [target, ms, delay])
  return v
}

function useSwaps(ids: string[]) {
  const [items, setItems] = useState<Item[]>([])
  const key = ids.join(',')
  useEffect(() => {
    if (!key) return setItems([])
    const wanted = new Set(key.split(','))
    // One retry: the wardrobe list sometimes fails on a stale database connection.
    api.wardrobe()
      .catch(() => api.wardrobe())
      .then((all) => setItems(all.filter((i) => wanted.has(i.id))))
      .catch(() => setItems([]))
  }, [key])
  return items
}

/** Position for the weather, or null if the phone says no or takes too long (then the saved city is used). */
function locate(): Promise<GeolocationCoordinates | null> {
  if (!('geolocation' in navigator)) return Promise.resolve(null)
  return new Promise((resolve) => {
    navigator.geolocation.getCurrentPosition((p) => resolve(p.coords), () => resolve(null), {
      timeout: 6000,
      maximumAge: 15 * 60_000,
    })
  })
}

/** Phone photos are 3 to 8 MB; 1280 px is plenty to judge a look and uploads in a second. */
async function shrink(file: File, max = 1280): Promise<File> {
  try {
    const bitmap = await createImageBitmap(file)
    const scale = Math.min(1, max / Math.max(bitmap.width, bitmap.height))
    const canvas = document.createElement('canvas')
    canvas.width = Math.round(bitmap.width * scale)
    canvas.height = Math.round(bitmap.height * scale)
    canvas.getContext('2d')!.drawImage(bitmap, 0, 0, canvas.width, canvas.height)
    const blob = await new Promise<Blob | null>((r) => canvas.toBlob(r, 'image/jpeg', 0.85))
    return blob ? new File([blob], 'look.jpg', { type: 'image/jpeg' }) : file
  } catch {
    return file
  }
}
