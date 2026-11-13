import { ArrowLeft, Briefcase, ChevronRight, Coffee, ExternalLink, Heart, Plane, Plus, Sparkles, Trash2 } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { api, waitForJob } from '../api'
import { errorText, title } from '../format'
import { getProfiles, getSettings, saveProfiles } from '../store'
import type { Look, Pin, StyleProfile } from '../types'
import { Notice, Photo, Sheet } from '../ui'
import Swipe from './Swipe'

const ICONS = { office: Briefcase, weekend: Coffee, date: Heart, travel: Plane, other: Sparkles }
const COLORS: Record<string, string> = {
  navy: '#1f2f56', beige: '#dcc9a8', white: '#ffffff', black: '#1c1c1a', grey: '#8d8d8d', brown: '#6b4a32',
  olive: '#6b7245', green: '#2f6b4a', blue: '#4a7fc0', red: '#c0463c', pink: '#e7a3a8', yellow: '#e6c34a',
}
const FITS = ['slim', 'regular', 'relaxed', 'oversized']

export default function Style({ active, version }: { active: boolean; version: number }) {
  const [profiles, setProfiles] = useState<StyleProfile[]>(getProfiles)
  const [looks, setLooks] = useState<Look[]>([])
  const [error, setError] = useState('')
  const [openId, setOpenId] = useState<string | null>(null)
  const [adding, setAdding] = useState(false)
  const [swiping, setSwiping] = useState(false)
  const [liked, setLiked] = useState<Pin[]>([])

  const load = useCallback(async () => {
    setProfiles(getProfiles())
    if (!getSettings().userId) return
    api.likedPins().then(setLiked).catch(() => setLiked([]))
    try {
      setLooks(await api.looks())
      setError('')
    } catch (e) {
      setError(errorText(e))
    }
  }, [])

  useEffect(() => {
    if (active) load()
  }, [active, version, load])

  const update = (next: StyleProfile[]) => {
    setProfiles(next)
    saveProfiles(next)
  }
  const patch = (p: StyleProfile) => update(profiles.map((x) => (x.profile_id === p.profile_id ? p : x)))
  const open = profiles.find((p) => p.profile_id === openId)
  const refsOf = (p: StyleProfile) => looks.filter((l) => p.reference_ids.includes(l.id))

  if (swiping)
    return (
      <Swipe
        onBack={() => {
          setSwiping(false)
          load()
        }}
      />
    )

  if (open)
    return (
      <Detail
        profile={open}
        looks={refsOf(open)}
        onBack={() => setOpenId(null)}
        onChange={patch}
        onReload={load}
        onDelete={() => {
          update(profiles.filter((p) => p.profile_id !== open.profile_id))
          setOpenId(null)
        }}
      />
    )

  return (
    <div className="page">
      <header className="page-head">
        <h1>My Style</h1>
        <button className="pill-btn" onClick={() => setAdding(true)}>
          <Plus size={18} /> Add Profile
        </button>
      </header>
      <p className="lead">Set your preferred look for each occasion.</p>
      {error && <Notice kind="error">{error}</Notice>}

      <button className="discover" onClick={() => setSwiping(true)}>
        <span className="badge">
          <Sparkles size={22} />
        </span>
        <div>
          <strong>Find your taste</strong>
          <span>Swipe looks you like. It takes a minute.</span>
          {liked.length > 0 && (
            <div className="thumbs">
              {liked.slice(0, 3).map((p) => (
                <Photo key={p.pin_id || p.id} src={p.image_url} alt={p.style_name || 'Liked look'} />
              ))}
              {liked.length > 3 && <div className="photo more-count">+{liked.length - 3}</div>}
            </div>
          )}
        </div>
        <ChevronRight size={20} />
      </button>

      <div className="profiles">
        {profiles.map((p) => {
          const Icon = ICONS[p.icon]
          const refs = refsOf(p)
          return (
            <button key={p.profile_id} className="profile-card" onClick={() => setOpenId(p.profile_id)}>
              <span className={`badge ${p.icon}`}>
                <Icon size={22} />
              </span>
              <div>
                <strong>{p.name}</strong>
                <span>{p.style_tags.map(title).join(' · ') || 'No mood tags yet'}</span>
                {refs.length > 0 ? (
                  <div className="thumbs">
                    {refs.slice(0, 3).map((l) => (
                      <Photo key={l.id} src={l.image_url} alt="Reference" />
                    ))}
                    {refs.length > 3 && <div className="photo more-count">+{refs.length - 3}</div>}
                  </div>
                ) : (
                  <em>No reference images yet</em>
                )}
              </div>
              <ChevronRight size={20} />
            </button>
          )
        })}
      </div>
      <p className="hint">Profiles are saved on this phone. Reference images are stored in your account.</p>

      {adding && (
        <AddProfile
          onClose={() => setAdding(false)}
          onAdd={(p) => {
            update([...profiles, p])
            setAdding(false)
            setOpenId(p.profile_id)
          }}
        />
      )}
    </div>
  )
}

function AddProfile({ onClose, onAdd }: { onClose: () => void; onAdd: (p: StyleProfile) => void }) {
  const [name, setName] = useState('')
  const [tags, setTags] = useState('')
  return (
    <Sheet title="New style profile" onClose={onClose}>
      <form
        className="stack"
        onSubmit={(e) => {
          e.preventDefault()
          if (!name.trim()) return
          onAdd({
            profile_id: `p_${Date.now()}`,
            name: name.trim(),
            icon: 'other',
            style_tags: splitTags(tags),
            preferred_colors: [],
            avoid_colors: [],
            preferred_fit: ['regular'],
            formality_range: [2, 4],
            reference_ids: [],
            reference_sources: [],
          })
        }}
      >
        <label className="field">
          <span>Occasion</span>
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Wedding guest" autoFocus />
        </label>
        <label className="field">
          <span>Mood tags, separated by commas (optional)</span>
          <input value={tags} onChange={(e) => setTags(e.target.value)} placeholder="elegant, light, summery" />
        </label>
        <button className="btn primary" type="submit" disabled={!name.trim()}>
          Create profile
        </button>
      </form>
    </Sheet>
  )
}

const splitTags = (s: string) =>
  s
    .split(',')
    .map((t) => t.trim().toLowerCase())
    .filter(Boolean)

function Detail({
  profile,
  looks,
  onBack,
  onChange,
  onReload,
  onDelete,
}: {
  profile: StyleProfile
  looks: Look[]
  onBack: () => void
  onChange: (p: StyleProfile) => void
  onReload: () => Promise<void>
  onDelete: () => void
}) {
  const [tab, setTab] = useState<'overview' | 'references' | 'details'>('overview')
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const [note, setNote] = useState('')
  const [viewing, setViewing] = useState<Look | null>(null)
  const [source, setSource] = useState('')
  const fileInput = useRef<HTMLInputElement>(null)
  const Icon = ICONS[profile.icon]

  async function addImages(files: FileList | null) {
    if (!files?.length) return
    setError('')
    setBusy(`Saving ${files.length} image${files.length > 1 ? 's' : ''}. About 15 seconds each.`)
    try {
      const added = await api.addLooks([...files])
      onChange({ ...profile, reference_ids: [...added.map((l) => l.id), ...profile.reference_ids] })
      await onReload()
    } catch (e) {
      setError(errorText(e))
    } finally {
      setBusy('')
      if (fileInput.current) fileInput.current.value = ''
    }
  }

  async function removeLook(look: Look) {
    setViewing(null)
    try {
      await api.deleteLook(look.id)
      onChange({ ...profile, reference_ids: profile.reference_ids.filter((id) => id !== look.id) })
      await onReload()
    } catch (e) {
      setError(errorText(e))
    }
  }

  async function addSource() {
    const raw = source.trim()
    if (!raw) return
    setError('')
    setNote('')
    const isPinterest = /pinterest\.|pin\.it/i.test(raw)
    if (isPinterest) {
      // Saved as a link only: the backend cannot read a user's Pinterest board yet.
      onChange({ ...profile, reference_sources: [...profile.reference_sources, { type: 'pinterest', url: raw, sync_status: 'link_only' }] })
      setSource('')
      return
    }
    const url = /^https?:/i.test(raw) ? raw : `https://www.instagram.com/${raw.replace(/^@/, '')}/`
    setBusy('Reading public Instagram posts. This can take a few minutes.')
    try {
      const { job_id } = await api.importUrl(raw, 'instagram')
      const job = await waitForJob(job_id, 360_000)
      const result = job.result as { outfits?: number; style_profile?: { summary?: string; style_tags?: string[] } } | null
      const tags = (result?.style_profile?.style_tags || []).map((t) => t.toLowerCase())
      onChange({
        ...profile,
        style_tags: [...new Set([...profile.style_tags, ...tags])].slice(0, 6),
        reference_sources: [...profile.reference_sources, { type: 'instagram', url, sync_status: 'imported' }],
      })
      setNote(`Read ${result?.outfits ?? 0} outfits. ${result?.style_profile?.summary || ''}`)
      setSource('')
    } catch (e) {
      setError(`Instagram could not be read: ${errorText(e)}. Only public profiles work.`)
    } finally {
      setBusy('')
    }
  }

  const toggle = (key: 'preferred_colors' | 'avoid_colors' | 'preferred_fit', value: string) => {
    const has = profile[key].includes(value)
    onChange({ ...profile, [key]: has ? profile[key].filter((v) => v !== value) : [...profile[key], value] })
  }

  const sources = (
    <div className="sources">
      {profile.reference_sources.length === 0 && <p className="muted">No sources yet.</p>}
      {profile.reference_sources.map((s) => (
        <a key={s.url} href={s.url} target="_blank" rel="noreferrer" className="source">
          <span className={`dot ${s.type}`} />
          <span>
            <strong>{s.type === 'pinterest' ? 'Pinterest Board' : 'Instagram Creator'}</strong>
            <small>
              {s.url.replace(/^https?:\/\/(www\.)?/, '').replace(/\/$/, '')} ·{' '}
              {s.sync_status === 'imported' ? 'Posts read once' : 'Link only, not synced'}
            </small>
          </span>
          <ExternalLink size={18} />
        </a>
      ))}
    </div>
  )

  const swatches = (key: 'preferred_colors' | 'avoid_colors', editable: boolean) => (
    <div className="swatches">
      {(editable ? Object.keys(COLORS) : profile[key]).map((c) => (
        <button
          key={c}
          type="button"
          disabled={!editable}
          title={c}
          aria-label={c}
          aria-pressed={profile[key].includes(c)}
          className={profile[key].includes(c) ? 'on' : ''}
          style={{ background: COLORS[c] || '#ccc' }}
          onClick={() => toggle(key, c)}
        />
      ))}
      {!editable && profile[key].length === 0 && <span className="muted">Not set</span>}
    </div>
  )

  return (
    <div className="page">
      <header className="detail-head">
        <button className="icon-btn" onClick={onBack} aria-label="Back to My Style">
          <ArrowLeft size={22} />
        </button>
        <button
          className="icon-btn"
          aria-label="Delete profile"
          onClick={() => {
            if (confirm(`Delete the ${profile.name} profile?`)) onDelete()
          }}
        >
          <Trash2 size={20} />
        </button>
      </header>
      <div className="detail-hero">
        <span className={`badge big ${profile.icon}`}>
          <Icon size={28} />
        </span>
        <h1>{profile.name}</h1>
        <p>{profile.style_tags.map(title).join(' · ') || 'No mood tags yet'}</p>
      </div>

      <div className="tabs">
        {(['overview', 'references', 'details'] as const).map((t) => (
          <button key={t} className={tab === t ? 'on' : ''} onClick={() => setTab(t)}>
            {title(t)}
          </button>
        ))}
      </div>

      {error && <Notice kind="error">{error}</Notice>}
      {note && <Notice>{note}</Notice>}
      {busy && <p className="busy">{busy}</p>}

      {tab === 'overview' && (
        <>
          <section className="panel">
            <h3>Reference Sources</h3>
            {sources}
            <h3>Reference Images ({looks.length})</h3>
            {looks.length ? (
              <div className="thumbs large">
                {looks.slice(0, 3).map((l) => (
                  <button key={l.id} onClick={() => setViewing(l)}>
                    <Photo src={l.image_url} alt="Reference" />
                  </button>
                ))}
                {looks.length > 3 && (
                  <button className="photo more-count" onClick={() => setTab('references')}>
                    +{looks.length - 3}
                  </button>
                )}
              </div>
            ) : (
              <p className="muted">None yet. Add some under References.</p>
            )}
          </section>
          <section className="panel">
            <h3>Style Preferences</h3>
            <div className="pref"><span>Preferred colors</span>{swatches('preferred_colors', false)}</div>
            <div className="pref"><span>Avoid colors</span>{swatches('avoid_colors', false)}</div>
            <div className="pref"><span>Preferred fit</span><b>{profile.preferred_fit.map(title).join(', ') || 'Not set'}</b></div>
            <div className="pref"><span>Formality range</span><b>{profile.formality_range[0]} – {profile.formality_range[1]} / 5</b></div>
          </section>
        </>
      )}

      {tab === 'references' && (
        <>
          <section className="panel">
            <h3>Reference Images ({looks.length})</h3>
            <div className="ref-grid">
              <button className="photo add-tile" onClick={() => fileInput.current?.click()} aria-label="Add reference image">
                <Plus size={24} />
              </button>
              {looks.map((l) => (
                <button key={l.id} onClick={() => setViewing(l)}>
                  <Photo src={l.image_url} alt="Reference" />
                </button>
              ))}
            </div>
            <p className="hint">References shape the style only. They are never suggested as clothes to wear.</p>
          </section>
          <section className="panel">
            <h3>Reference Sources</h3>
            {sources}
            <form
              className="stack"
              onSubmit={(e) => {
                e.preventDefault()
                addSource()
              }}
            >
              <label className="field">
                <span>Instagram handle or Pinterest board link</span>
                <input value={source} onChange={(e) => setSource(e.target.value)} placeholder="@minimal.gent" />
              </label>
              <button className="btn" type="submit" disabled={!source.trim() || !!busy}>
                Add source
              </button>
            </form>
            <p className="hint">Instagram: public posts are read once and added to your style. Pinterest: saved as a link for now.</p>
          </section>
          <input ref={fileInput} type="file" accept="image/*" multiple hidden onChange={(e) => addImages(e.target.files)} />
        </>
      )}

      {tab === 'details' && (
        <section className="panel stack">
          <label className="field">
            <span>Name</span>
            <input value={profile.name} onChange={(e) => onChange({ ...profile, name: e.target.value })} />
          </label>
          <label className="field">
            <span>Mood tags, separated by commas</span>
            <input
              defaultValue={profile.style_tags.join(', ')}
              onBlur={(e) => onChange({ ...profile, style_tags: splitTags(e.target.value) })}
            />
          </label>
          <div className="field"><span>Preferred colors</span>{swatches('preferred_colors', true)}</div>
          <div className="field"><span>Avoid colors</span>{swatches('avoid_colors', true)}</div>
          <div className="field">
            <span>Preferred fit</span>
            <div className="chips wrap">
              {FITS.map((f) => (
                <button key={f} type="button" className={`chip ${profile.preferred_fit.includes(f) ? 'on' : ''}`} onClick={() => toggle('preferred_fit', f)}>
                  {title(f)}
                </button>
              ))}
            </div>
          </div>
          <label className="field">
            <span>Formality from {profile.formality_range[0]} / 5</span>
            <input
              type="range" min={1} max={5} value={profile.formality_range[0]}
              onChange={(e) => {
                const lo = +e.target.value
                onChange({ ...profile, formality_range: [lo, Math.max(lo, profile.formality_range[1])] })
              }}
            />
          </label>
          <label className="field">
            <span>Formality up to {profile.formality_range[1]} / 5</span>
            <input
              type="range" min={1} max={5} value={profile.formality_range[1]}
              onChange={(e) => {
                const hi = +e.target.value
                onChange({ ...profile, formality_range: [Math.min(hi, profile.formality_range[0]), hi] })
              }}
            />
          </label>
          <p className="hint">Changes are saved as you make them and used for the next outfit.</p>
        </section>
      )}

      {viewing && (
        <Sheet title="Reference" onClose={() => setViewing(null)}>
          <div className="look-view">
            <Photo src={viewing.image_url} alt="Reference" />
          </div>
          {viewing.vibe && <p>{viewing.vibe}</p>}
          <p className="muted">{[...(viewing.style_tags || []), ...(viewing.palette || [])].map(title).join(' · ')}</p>
          <button
            className="btn danger"
            onClick={() => {
              if (confirm('Remove this reference?')) removeLook(viewing)
            }}
          >
            Remove reference
          </button>
        </Sheet>
      )}
    </div>
  )
}
