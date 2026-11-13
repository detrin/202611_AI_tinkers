import { RefreshCw, Timer } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'

/**
 * In-browser camera for laptops and desktops, where `<input capture>` only opens a file picker.
 * Phones keep the native camera (better: full resolution, focus, flash).
 */
export function hasWebcam(): boolean {
  return typeof window !== 'undefined' && !!navigator.mediaDevices?.getUserMedia && window.matchMedia('(pointer: fine)').matches
}

const TIMER_SECONDS = 3

/** Live preview with a shutter and an optional 3 s timer (to step back for a head-to-toe shot). */
export default function WebCamera({ onShot, onUnavailable }: { onShot: (file: File) => void; onUnavailable: () => void }) {
  const video = useRef<HTMLVideoElement>(null)
  const [facing, setFacing] = useState<'user' | 'environment'>('user')
  const [cameras, setCameras] = useState(0)
  const [ready, setReady] = useState(false)
  const [timer, setTimer] = useState(false)
  const [count, setCount] = useState(0)

  useEffect(() => {
    let stream: MediaStream | null = null
    let cancelled = false
    setReady(false)
    navigator.mediaDevices
      .getUserMedia({ video: { facingMode: facing, width: { ideal: 1920 }, height: { ideal: 1440 } }, audio: false })
      .then(async (s) => {
        if (cancelled) return s.getTracks().forEach((t) => t.stop())
        stream = s
        if (video.current) {
          video.current.srcObject = s
          await video.current.play().catch(() => undefined)
        }
        setReady(true)
        const devices = await navigator.mediaDevices.enumerateDevices()
        setCameras(devices.filter((d) => d.kind === 'videoinput').length)
      })
      .catch(() => !cancelled && onUnavailable()) // permission denied or no camera: fall back to choosing a file
    return () => {
      cancelled = true
      stream?.getTracks().forEach((t) => t.stop())
    }
  }, [facing, onUnavailable])

  useEffect(() => {
    if (count <= 0) return
    const id = setTimeout(() => (count === 1 ? (setCount(0), shoot()) : setCount(count - 1)), 1000)
    return () => clearTimeout(id)
  }, [count]) // eslint-disable-line react-hooks/exhaustive-deps

  function shoot() {
    const v = video.current
    if (!v || !v.videoWidth) return
    const canvas = document.createElement('canvas')
    canvas.width = v.videoWidth
    canvas.height = v.videoHeight
    canvas.getContext('2d')!.drawImage(v, 0, 0) // the saved photo is not mirrored, only the preview is
    canvas.toBlob((blob) => blob && onShot(new File([blob], 'camera.jpg', { type: 'image/jpeg' })), 'image/jpeg', 0.92)
  }

  return (
    <div className="webcam">
      <div className="webcam-frame">
        <video ref={video} playsInline muted className={facing === 'user' ? 'mirrored' : ''} />
        {!ready && <p className="webcam-note">Waiting for the camera…</p>}
        {count > 0 && <span className="webcam-count" key={count}>{count}</span>}
      </div>
      <div className="webcam-bar">
        <button className={`icon-btn ${timer ? 'on' : ''}`} onClick={() => setTimer(!timer)} aria-pressed={timer}
          aria-label={`${TIMER_SECONDS} second timer`}>
          <Timer size={22} strokeWidth={1.5} />
        </button>
        <button className="shutter" disabled={!ready || count > 0} aria-label="Take photo"
          onClick={() => (timer ? setCount(TIMER_SECONDS) : shoot())} />
        {cameras > 1 ? (
          <button className="icon-btn" onClick={() => setFacing(facing === 'user' ? 'environment' : 'user')} aria-label="Switch camera">
            <RefreshCw size={22} strokeWidth={1.5} />
          </button>
        ) : <span className="icon-btn" aria-hidden />}
      </div>
      <p className="hint">{timer ? `Press, then step back: it takes the photo after ${TIMER_SECONDS} seconds.` : 'Step back so the whole outfit is in view.'}</p>
    </div>
  )
}
