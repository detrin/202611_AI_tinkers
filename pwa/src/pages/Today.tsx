import { Camera, CalendarDays, Check, ChevronRight, CloudSun, Heart, RefreshCw, SlidersHorizontal } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { api, ApiError } from '../api'
import { errorText, eventPrompt, itemName, profileLine, sentences, title, todayNote, weatherLine } from '../format'
import { getLastOutfit, getOccasion, getProfiles, getSettings, nextPlan, PLANS, saveLastOutfit, saveOccasion, today } from '../store'
import type { Item, Occasion, Outfit } from '../types'
import { ItemSheet, Notice, Photo, Sheet } from '../ui'
import CheckLook from './Check'

export default function Today({ active, version }: { active: boolean; version: number }) {
  const saved = useRef(getLastOutfit())
  const [outfit, setOutfit] = useState<Outfit | null>(saved.current?.outfit ?? null)
  const [selected, setSelected] = useState(saved.current?.selected ?? false)
  // The next plan is the occasion, until the user sets another one with the sliders.
  const [occasion, setOccasion] = useState<Occasion>(() => {
    const plan = nextPlan()
    const saved = getOccasion()
    if (!plan) return saved
    const office = /meeting|client|office/i.test(plan.title)
    return { title: `${plan.title} (${plan.location})${plan.day ? ', tomorrow' : ''}`, time: plan.time, profile_id: office ? 'office' : saved.profile_id }
  })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [stale, setStale] = useState(false)
  const [controls, setControls] = useState(false)
  const [openItem, setOpenItem] = useState<Item | null>(null)
  const [checking, setChecking] = useState(false)
  const started = useRef(false)
  // Outfits already shown in this session, so swiping one away never brings the same one back.
  const shown = useRef<string[]>(saved.current ? [comboKey(saved.current.outfit.item_ids)] : [])

  const profiles = getProfiles()
  const profile = profiles.find((p) => p.profile_id === occasion.profile_id)

  const generate = useCallback(async (occ: Occasion, avoid: string[] = []) => {
    setLoading(true)
    setError('')
    try {
      const prof = getProfiles().find((p) => p.profile_id === occ.profile_id)
      const seen = shown.current.slice(-4)
      const daily = () =>
        api.dailyOutfit(
          eventPrompt(occ, prof, avoid) +
            (seen.length ? `. Already rejected today, never suggest these exact combinations again: ${seen.map((c) => `[${c}]`).join(' ')}` : ''),
        )
      let next
      try {
        next = await api.todayOutfit(todayNote(occ, prof))
      } catch (e) {
        // 404: endpoint not deployed. 401/503: no token configured. 422: rejected input. Use the simpler picker.
        if (!(e instanceof ApiError) || ![401, 404, 405, 422, 503].includes(e.status)) throw e
        next = await daily()
      }
      // Retry once when the model returns no usable items, or repeats an outfit that was already swiped away.
      if (next.items.length === 0 || shown.current.includes(comboKey(next.item_ids))) next = await daily()
      shown.current.push(comboKey(next.item_ids))
      setOutfit(next)
      setSelected(false)
      setStale(false)
      saveLastOutfit({ outfit: next, selected: false })
    } catch (e) {
      setError(errorText(e))
      setStale(true)
    } finally {
      setLoading(false)
    }
  }, [])

  // First time the tab is shown: reuse today's saved outfit, otherwise ask for one.
  useEffect(() => {
    if (!active || started.current || !getSettings().userId) return
    started.current = true
    if (!outfit || outfit.date !== today()) generate(occasion)
  }, [active, version, outfit, occasion, generate])

  async function wear() {
    if (!outfit) return
    setSelected(true)
    saveLastOutfit({ outfit, selected: true })
    try {
      await api.outfitFeedback(outfit.id, { worn: true })
    } catch (e) {
      setError(`Saved on this phone only: ${errorText(e)}`)
    }
  }

  async function markLaundry(item: Item) {
    setOpenItem(null)
    setLoading(true)
    setError('')
    try {
      await api.setAvailability(item.id, 'laundry')
      setOutfit(null)
      saveLastOutfit(null)
      await generate(occasion, outfit?.item_ids)
    } catch (e) {
      setError(errorText(e))
      setLoading(false)
    }
  }

  function applyControls(next: Occasion) {
    setOccasion(next)
    saveOccasion(next)
    setControls(false)
    generate(next)
  }

  const dateLabel = new Date().toLocaleDateString('en-GB', { weekday: 'long', month: 'short', day: 'numeric' })
  const weather = weatherLine(outfit?.weather)
  const reasons = sentences(outfit?.explanation ?? null)
  const events = outfit?.context?.events ?? []
  const eventTime = new Intl.DateTimeFormat('en-GB', {
    hour: '2-digit', minute: '2-digit', timeZone: outfit?.context?.timezone,
  })
  const commute = outfit?.context?.commute?.mode

  return (
    <div className="page">
      <header className="page-head">
        <div>
          <p className="eyebrow">{dateLabel}</p>
          <h1>Today's Outfit</h1>
        </div>
        <button className="icon-btn" onClick={() => setControls(true)} aria-label="Change occasion and style">
          <SlidersHorizontal size={22} />
        </button>
      </header>

      {getSettings().userId && (
        <button className="check-entry" onClick={() => setChecking(true)}>
          <span className="check-entry-icon">
            <Camera size={22} />
          </span>
          <span>
            <strong>Already dressed?</strong>
            <small>Snap a photo: hell yeah or hell nah</small>
          </span>
          <ChevronRight size={20} />
        </button>
      )}

      <section className="context" aria-label="Today's plans">
        {events.map((event, index) => (
          <p key={`${event.start_time}-${index}`}>
            <CalendarDays size={18} />
            <span>
              {eventTime.format(new Date(event.start_time))} · {event.title}
              {event.location && ` · ${event.location}`}
              {event.place_category && ` · ${event.place_category}`}
              <small>{weatherLine(event.weather ?? undefined) || 'Forecast unavailable'}</small>
            </span>
          </p>
        ))}
        {events.length === 0 && (
          <>
            <p>
              <CalendarDays size={18} />
              <span>
                {occasion.time && `${occasion.time} · `}{occasion.title}
                <small>Dressing for this</small>
              </span>
            </p>
            {PLANS.filter((p) => !occasion.title.startsWith(p.title)).slice(0, 3).map((p) => (
              <p key={`${p.day}-${p.time}`} className="later">
                <CalendarDays size={18} />
                <span>
                  {p.day ? 'Tomorrow ' : ''}{p.time} · {p.title}
                  <small>{p.location}</small>
                </span>
              </p>
            ))}
            <p>
              <CloudSun size={18} />
              <span>{weather ? `${weather}${outfit?.city ? ` · ${outfit.city}` : ''}` : 'Weather loads with the outfit'}</span>
            </p>
          </>
        )}
        <p>
          <Heart size={18} />
          <span>{profile ? profileLine(profile) : 'No style profile applied'}</span>
        </p>
      </section>

      {error && <Notice kind="error">{error}</Notice>}
      {stale && outfit && <Notice>Showing the last outfit that loaded, from {outfit.date}.</Notice>}

      <div className="section-head">
        <h2>Recommended for you</h2>
        <span>From your wardrobe</span>
      </div>

      {loading && (
        <>
          <div className="board skeleton" />
          <p className="busy">Choosing from your closet…</p>
        </>
      )}

      {!loading && outfit && outfit.items.length > 0 && (
        <>
          <OutfitBoard
            items={outfit.items}
            onOpen={setOpenItem}
            onSwipe={(liked) => (liked ? wear() : generate(occasion, outfit.item_ids))}
          />
          {!selected && <p className="hint center">Swipe right to wear it, left for another.</p>}

          <section className="why">
            <h3>Why this outfit?</h3>
            {reasons.map((r) => (
              <p key={r}>
                <Check size={18} />
                <span>{r}</span>
              </p>
            ))}
            {outfit.missing_item_tip && <p className="tip">Would improve it: {outfit.missing_item_tip}</p>}
          </section>

          {outfit.steps && outfit.steps.length > 0 && (
            <details className="steps">
              <summary>How I decided{commute ? ` · going by ${commute}` : ''}</summary>
              {outfit.steps.map((s) => (
                <p key={s.tool}>
                  <b>{title(s.tool.replace(/^get_/, '').replace(/.*\//, 'venue lookup'))}</b>
                  <span>{s.summary}{s.event_start_time && ` · ${eventTime.format(new Date(s.event_start_time))}`}</span>
                </p>
              ))}
              {outfit.from_fallback && <p className="tip">The agent did not answer in time, so the simpler picker chose this.</p>}
            </details>
          )}

          <div className="actions">
            <button className="btn primary" onClick={wear} disabled={selected}>
              {selected ? (
                <>
                  <Check size={18} /> Wearing this
                </>
              ) : (
                'Wear this'
              )}
            </button>
            <button className="btn" onClick={() => generate(occasion, outfit.item_ids)}>
              <RefreshCw size={18} /> Try another
            </button>
          </div>
          <p className="hint">Tap a piece if it is in the laundry and the outfit is replanned without it.</p>
        </>
      )}

      {!loading && outfit && outfit.items.length === 0 && (
        <Notice>No suitable combination was found in your available clothes. Add items in My Closet or try another occasion.</Notice>
      )}

      {!loading && !outfit && !error && (
        <div className="empty">
          <p>{getSettings().userId ? 'No outfit yet.' : 'Add your user in Settings to start.'}</p>
          {getSettings().userId && (
            <button className="btn primary" onClick={() => generate(occasion)}>
              Suggest an outfit
            </button>
          )}
        </div>
      )}
      {!loading && !outfit && error && (
        <button className="btn" onClick={() => generate(occasion)}>
          Try again
        </button>
      )}

      {openItem && (
        <ItemSheet
          item={openItem}
          onClose={() => setOpenItem(null)}
          actions={
            <button className="btn primary" onClick={() => markLaundry(openItem)}>
              In the laundry: replan without it
            </button>
          }
        />
      )}

      {checking && <CheckLook occasion={occasion.time ? `${occasion.title} at ${occasion.time}` : occasion.title} onClose={() => setChecking(false)} />}

      {controls && <Controls occasion={occasion} onApply={applyControls} onClose={() => setControls(false)} />}
    </div>
  )
}

const comboKey = (ids: string[]) => [...ids].sort().join(',')

const SLOT_ORDER = ['outerwear', 'top', 'dress', 'bottom', 'shoes', 'accessory']

/** The outfit as square cards, like My Closet, ordered from outer layer to shoes. The whole set can be swiped. */
function OutfitBoard({ items, onOpen, onSwipe }: { items: Item[]; onOpen: (i: Item) => void; onSwipe: (liked: boolean) => void }) {
  const [dx, setDx] = useState(0)
  const start = useRef<number | null>(null)
  const dragged = useRef(false)
  const [dragging, setDragging] = useState(false)
  const lean = Math.max(-1, Math.min(1, dx / 90))
  const end = () => {
    if (start.current === null) return
    start.current = null
    setDragging(false)
    if (Math.abs(dx) > 90) onSwipe(dx > 0)
    setDx(0)
  }
  const sorted = [...items].sort((a, b) => SLOT_ORDER.indexOf(a.category || '') - SLOT_ORDER.indexOf(b.category || ''))
  return (
    <div className="outfit">
      <div
        className="outfit-cards"
        style={{ transform: `translateX(${dx}px) rotate(${lean * 4}deg)`, transition: dragging ? 'none' : 'transform 180ms ease-out' }}
        onPointerDown={(e) => {
          start.current = e.clientX
          dragged.current = false
          setDragging(true)
        }}
        onPointerMove={(e) => {
          if (start.current === null) return
          const d = e.clientX - start.current
          if (Math.abs(d) > 8) dragged.current = true
          setDx(d)
        }}
        onPointerUp={end}
        onPointerLeave={end}
        onPointerCancel={end}
        onClickCapture={(e) => {
          // A drag must not also open the piece under the finger.
          if (dragged.current) e.stopPropagation()
        }}
      >
        {lean > 0.3 && <span className="stamp like">Wear</span>}
        {lean < -0.3 && <span className="stamp skip">Another</span>}
        {sorted.map((item) => (
          <button key={item.id} className="card" onClick={() => onOpen(item)}>
            <Photo src={item.image_url} alt={itemName(item)} />
            <div className="card-body">
              <strong>{itemName(item)}</strong>
              <span>{[title(item.category), title(item.colors?.[0])].filter(Boolean).join(' · ')}</span>
            </div>
          </button>
        ))}
      </div>
    </div>
  )
}

function Controls({ occasion, onApply, onClose }: { occasion: Occasion; onApply: (o: Occasion) => void; onClose: () => void }) {
  const [draft, setDraft] = useState(occasion)
  const profiles = getProfiles()
  return (
    <Sheet title="What is today?" onClose={onClose}>
      <form
        className="stack"
        onSubmit={(e) => {
          e.preventDefault()
          onApply({ ...draft, title: draft.title.trim() || 'Casual day' })
        }}
      >
        <label className="field">
          <span>Occasion</span>
          <input value={draft.title} onChange={(e) => setDraft({ ...draft, title: e.target.value })} placeholder="Client meeting" />
        </label>
        <label className="field">
          <span>Time (optional)</span>
          <input type="time" value={draft.time} onChange={(e) => setDraft({ ...draft, time: e.target.value })} />
        </label>
        <div className="field">
          <span>Style profile</span>
          <div className="chips wrap">
            {profiles.map((p) => (
              <button
                type="button"
                key={p.profile_id}
                className={`chip ${draft.profile_id === p.profile_id ? 'on' : ''}`}
                onClick={() => setDraft({ ...draft, profile_id: p.profile_id })}
              >
                {p.name}
              </button>
            ))}
            <button
              type="button"
              className={`chip ${draft.profile_id === null ? 'on' : ''}`}
              onClick={() => setDraft({ ...draft, profile_id: null })}
            >
              None
            </button>
          </div>
        </div>
        <p className="hint">This occasion is used when the calendar has no events for today.</p>
        <button className="btn primary" type="submit">
          Apply and suggest
        </button>
      </form>
    </Sheet>
  )
}
