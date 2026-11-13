import { Camera, CloudSun, ImagePlus, Share2, Shirt, X } from 'lucide-react'
import { useCallback, useEffect, useRef, useState, type CSSProperties } from 'react'
import { track } from '../analytics'
import { api } from '../api'
import { errorText, itemName } from '../format'
import type { Item, LookPoint, LookVerdict } from '../types'
import { Notice } from '../ui'
import WebCamera, { hasWebcam } from '../webcam'

type Phase = 'pick' | 'checking' | 'result'

const MIN_SCAN_MS = 1800
const LOOK_LINES = ['Looking at the fit', 'Reading the colours', 'Checking the proportions', 'Thinking about the weather', 'Making up my mind']
const CLOSET_LINES = ['Opening your closet', 'Trying pieces on', 'Picking the swap']

/**
 * "Is it good enough?": a photo of the look you have on → hell yeah / hell nah, and what to change.
 * Weather comes from the phone's position (or the saved city when the phone says no).
 * The closet is only read when the user asks for a swap after a hell nah.
 */
export default function CheckLook({ occasion, onClose }: { occasion?: string; onClose: () => void }) {
  const [phase, setPhase] = useState<Phase>('pick')
  const [photo, setPhoto] = useState<File | null>(null)
  const [preview, setPreview] = useState('')
  const [result, setResult] = useState<LookVerdict | null>(null)
  const [withCloset, setWithCloset] = useState(false)
  const [error, setError] = useState('')
  const camera = useRef<HTMLInputElement>(null)
  const gallery = useRef<HTMLInputElement>(null)
  const position = useRef<Promise<GeolocationCoordinates | null> | null>(null)
  const webcam = useRef(hasWebcam()).current // laptops: in-app camera; phones: the native camera app
  const [live, setLive] = useState(false)
  const noWebcam = useCallback(() => {
    setLive(false)
    gallery.current?.click()
  }, [])

  useEffect(() => () => { if (preview) URL.revokeObjectURL(preview) }, [preview])
  useEffect(() => {
    const before = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => { document.body.style.overflow = before }
  }, [])

  async function check(file: File, closet: boolean) {
    setPhase('checking')
    setWithCloset(closet)
    setError('')
    try {
      position.current ??= locate()
      const [small, coords] = await Promise.all([shrink(file), position.current])
      // The scan runs at least a moment even on a fast answer, so the verdict lands instead of flickering in.
      const [verdict] = await Promise.all([
        api.checkLook(small, { position: coords, useSavedCity: !coords, includeWardrobe: closet, occasion }),
        new Promise((r) => setTimeout(r, MIN_SCAN_MS)),
      ])
      setResult(verdict)
      setPhase('result')
      navigator.vibrate?.(verdict.good_enough ? [20, 60, 20, 60, 40] : [90])
      track('look_checked', { verdict: verdict.verdict, with_closet: closet, has_weather: !!verdict.weather })
    } catch (e) {
      setError(errorText(e))
      setPhase(result ? 'result' : 'pick')
    }
  }

  /** A new photo goes straight into the check: no settings to confirm first. */
  function choose(files: FileList | null) {
    if (files?.[0]) pick(files[0])
  }

  /** Laptops: back to the live camera. Phones: the native camera app again. */
  function retake() {
    if (!webcam) return camera.current?.click()
    setPreview('')
    setPhoto(null)
    setResult(null)
    setError('')
    setPhase('pick')
    setLive(true)
  }

  function pick(file: File) {
    setLive(false)
    setPhoto(file)
    setPreview(URL.createObjectURL(file))
    setResult(null)
    check(file, false)
  }

  const tone = phase === 'result' && result ? (result.good_enough ? 'yeah' : 'nah') : ''

  return (
    <div className={`check ${tone}`} role="dialog" aria-label="Is it good enough?">
      {tone && <i className="flood" key={`${tone}-${withCloset}`} />}

      <header className="check-head">
        <p className="eyebrow">Is it good enough?</p>
        <button className="icon-btn" onClick={onClose} aria-label="Close">
          <X size={22} />
        </button>
      </header>

      <input ref={camera} type="file" accept="image/*" capture="environment" hidden onChange={(e) => choose(e.target.files)} />
      <input ref={gallery} type="file" accept="image/*" hidden onChange={(e) => choose(e.target.files)} />

      {!preview ? (
        <>
          {live ? (
            <WebCamera onShot={pick} onUnavailable={noWebcam} />
          ) : (
            <button className="snap" onClick={() => (webcam ? setLive(true) : camera.current?.click())}>
              <span className="snap-ring">
                <Camera size={34} strokeWidth={1.5} />
              </span>
              <strong>{webcam ? 'Take a photo' : 'Take a mirror photo'}</strong>
              <span>Head to toe works best</span>
            </button>
          )}
          <button className="btn" onClick={() => gallery.current?.click()}>
            <ImagePlus size={18} /> Choose from photos
          </button>
          <p className="hint">Weather comes from where you are. Your closet is only used if you ask for a swap.</p>
        </>
      ) : (
        <Card src={preview} scanning={phase === 'checking'} verdict={phase === 'result' ? result : null} />
      )}

      {phase === 'checking' && <Ticker lines={withCloset ? CLOSET_LINES : LOOK_LINES} />}
      {error && <Notice kind="error">{error}</Notice>}
      {phase === 'pick' && preview && (
        <button className="btn primary big" onClick={() => photo && check(photo, false)}>
          Try again
        </button>
      )}

      {phase === 'result' && result && photo && (
        <Verdict
          key={`${result.verdict}-${withCloset}`}
          verdict={result}
          photo={photo}
          onSwap={() => check(photo, true)}
          onRetake={retake}
          onDone={onClose}
        />
      )}
    </div>
  )
}

function Card({ src, scanning, verdict }: { src: string; scanning: boolean; verdict: LookVerdict | null }) {
  return (
    <div className={`look-card ${scanning ? 'scanning' : ''}`}>
      <div className="look-photo">
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
      </div>
      {verdict && (
        <>
          {verdict.good_enough && <Confetti />}
          <span className="sticker" aria-hidden>
            {verdict.good_enough ? 'Yeah' : 'Nah'}
          </span>
        </>
      )}
    </div>
  )
}

function Verdict({ verdict, photo, onSwap, onRetake, onDone }: {
  verdict: LookVerdict; photo: File; onSwap: () => void; onRetake: () => void; onDone: () => void
}) {
  const good = verdict.good_enough
  const points = good ? verdict.highlights : verdict.fixes
  const swaps = useSwaps(verdict.swap_item_ids)
  const temp = verdict.weather?.current?.temperature_2m
  const place = verdict.weather?.city
  const weather = [temp != null ? `${Math.round(temp)}°C${place ? ` in ${place}` : ''}` : '', verdict.weather_note].filter(Boolean).join(' · ')
  const canShare = good && typeof navigator.canShare === 'function'
  let n = 0
  const step = () => ({ '--i': n++ }) as CSSProperties

  return (
    <section className="verdict">
      <div className="verdict-head" style={step()}>
        <h1>{good ? 'Hell yeah' : 'Hell nah'}</h1>
        {verdict.explanation && <p>{verdict.explanation}</p>}
        {weather && (
          <small>
            <CloudSun size={15} /> {weather}
          </small>
        )}
      </div>

      {points.length > 0 && (
        <div className="moves">
          <h2 style={step()}>{good ? 'Why it works' : verdict.used_wardrobe ? 'From your closet' : 'Fix it'}</h2>
          {points.map((p: LookPoint, i) => (
            <div className="move" key={p.title} style={step()}>
              <b>{i + 1}</b>
              <span>
                <strong>{p.title}</strong>
                {p.detail && <small>{p.detail}</small>}
              </span>
            </div>
          ))}
        </div>
      )}

      {swaps.length > 0 && (
        <div className="swap-row" style={step()}>
          {swaps.map((item) => (
            <figure key={item.id}>
              <div className="photo">{item.image_url ? <img src={item.image_url} alt={itemName(item)} /> : <span>{itemName(item)}</span>}</div>
              <figcaption>{itemName(item)}</figcaption>
            </figure>
          ))}
        </div>
      )}

      <div className="actions" style={step()}>
        {good ? (
          <>
            <button className="btn primary" onClick={onDone}>Wear it</button>
            {canShare ? (
              <button className="btn" onClick={() => shareVerdict(photo)}>
                <Share2 size={18} /> Share
              </button>
            ) : (
              <button className="btn" onClick={onRetake}>
                <Camera size={18} /> Check another
              </button>
            )}
          </>
        ) : (
          <>
            {verdict.used_wardrobe ? (
              <button className="btn primary" onClick={onRetake}>
                <Camera size={18} /> Retake
              </button>
            ) : (
              <button className="btn primary" onClick={onSwap}>
                <Shirt size={18} /> Find a swap
              </button>
            )}
            <button className="btn" onClick={verdict.used_wardrobe ? onDone : onRetake}>
              {verdict.used_wardrobe ? 'Done' : 'Retake'}
            </button>
          </>
        )}
      </div>
    </section>
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

/** The photo with the green YEAH sticker on it, through the phone's share sheet. */
async function shareVerdict(photo: File) {
  try {
    const bitmap = await createImageBitmap(photo)
    const scale = Math.min(1, 1280 / Math.max(bitmap.width, bitmap.height))
    const canvas = document.createElement('canvas')
    canvas.width = Math.round(bitmap.width * scale)
    canvas.height = Math.round(bitmap.height * scale)
    const ctx = canvas.getContext('2d')!
    ctx.drawImage(bitmap, 0, 0, canvas.width, canvas.height)
    const size = Math.round(canvas.width * 0.12)
    ctx.font = `800 ${size}px Inter, system-ui, sans-serif`
    const label = 'HELL YEAH'
    const w = ctx.measureText(label).width + size
    const h = size * 1.5
    ctx.translate(canvas.width - w / 2 - size * 0.5, canvas.height - h / 2 - size * 0.6)
    ctx.rotate((8 * Math.PI) / 180)
    ctx.fillStyle = '#ffffff'
    ctx.strokeStyle = '#2f8f5b'
    ctx.lineWidth = size * 0.12
    ctx.beginPath()
    ctx.roundRect(-w / 2, -h / 2, w, h, size * 0.35)
    ctx.fill()
    ctx.stroke()
    ctx.fillStyle = '#2f8f5b'
    ctx.textAlign = 'center'
    ctx.textBaseline = 'middle'
    ctx.fillText(label, 0, size * 0.05)
    const blob = await new Promise<Blob | null>((r) => canvas.toBlob(r, 'image/jpeg', 0.9))
    if (!blob) return
    const file = new File([blob], 'hell-yeah.jpg', { type: 'image/jpeg' })
    const data = { files: [file], text: 'Hell yeah. Good enough to go.' }
    if (navigator.canShare?.(data)) {
      await navigator.share(data)
      track('look_shared')
    }
  } catch {
    /* share sheet dismissed */
  }
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
