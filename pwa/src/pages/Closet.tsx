import { Camera, Link as LinkIcon, MoreHorizontal, Plus, Search } from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { api, cutOut, waitForJob } from '../api'
import { errorText, isAvailable, itemName, itemSub } from '../format'
import { getSettings } from '../store'
import type { Item } from '../types'
import { Availability, ItemSheet, Notice, Photo, Sheet } from '../ui'

const FILTERS = [
  { id: 'all', label: 'All' },
  { id: 'top', label: 'Tops' },
  { id: 'bottom', label: 'Bottoms' },
  { id: 'outerwear', label: 'Outerwear' },
  { id: 'shoes', label: 'Shoes' },
  { id: 'other', label: 'Other' },
]
const MAIN = ['top', 'bottom', 'outerwear', 'shoes']

export default function Closet({ active, version }: { active: boolean; version: number }) {
  const [items, setItems] = useState<Item[] | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState('')
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState('all')
  const [adding, setAdding] = useState(false)
  const [open, setOpen] = useState<Item | null>(null)
  const [isNew, setIsNew] = useState(false)
  const fileInput = useRef<HTMLInputElement>(null)

  const load = useCallback(async () => {
    if (!getSettings().userId) return
    try {
      setItems(await api.wardrobe())
      setError('')
    } catch (e) {
      setError(errorText(e))
    }
  }, [])

  useEffect(() => {
    if (active) load()
  }, [active, version, load])

  async function upload(files: FileList | null) {
    if (!files?.length) return
    setAdding(false)
    setError('')
    setBusy(`Cutting out and reading ${files.length} photo${files.length > 1 ? 's' : ''}. About 15 seconds each.`)
    try {
      const cut = await Promise.all([...files].map(cutOut))
      const added = await api.addItems(cut)
      await load()
      if (added[0]) {
        setOpen(added[0])
        setIsNew(true)
      }
    } catch (e) {
      setError(errorText(e))
    } finally {
      setBusy('')
      if (fileInput.current) fileInput.current.value = ''
    }
  }

  async function importUrl(url: string) {
    setAdding(false)
    setError('')
    setBusy('Fetching the product page. This can take a minute or two.')
    try {
      const { job_id } = await api.importUrl(url, 'product')
      const job = await waitForJob(job_id)
      await load()
      const item = (job.result as { item?: Item } | null)?.item
      if (item) {
        setOpen(item)
        setIsNew(true)
      }
    } catch (e) {
      setError(`Could not read that product page: ${errorText(e)}`)
    } finally {
      setBusy('')
    }
  }

  async function change(action: () => Promise<unknown>) {
    setOpen(null)
    setIsNew(false)
    try {
      await action()
      await load()
    } catch (e) {
      setError(errorText(e))
    }
  }

  const q = query.trim().toLowerCase()
  const shown = (items || []).filter((i) => {
    const cat = i.category || ''
    const inFilter = filter === 'all' || (filter === 'other' ? !MAIN.includes(cat) : cat === filter)
    const text = [i.subtype, i.category, ...(i.colors || []), i.material, i.pattern].join(' ').toLowerCase()
    return inFilter && (!q || text.includes(q))
  })

  return (
    <div className="page">
      <header className="page-head">
        <h1>My Closet</h1>
        <button className="add-btn" onClick={() => setAdding(true)} aria-label="Add item">
          <Plus size={22} />
        </button>
      </header>
      <p className="count">{items ? `${items.length} item${items.length === 1 ? '' : 's'}` : ' '}</p>

      <label className="search">
        <Search size={18} />
        <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Search your closet" />
      </label>

      <div className="chips">
        {FILTERS.map((f) => (
          <button key={f.id} className={`chip ${filter === f.id ? 'on' : ''}`} onClick={() => setFilter(f.id)}>
            {f.label}
          </button>
        ))}
      </div>

      {error && <Notice kind="error">{error}</Notice>}
      {busy && <p className="busy">{busy}</p>}

      {!items && !error && (
        <div className="grid">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="card">
              <div className="photo skeleton" />
            </div>
          ))}
        </div>
      )}

      {items && items.length === 0 && (
        <div className="empty">
          <p>Your closet is empty. Add what you own with a photo or a shop link.</p>
          <button className="btn primary" onClick={() => setAdding(true)}>
            Add your first item
          </button>
        </div>
      )}
      {items && items.length > 0 && shown.length === 0 && <p className="muted pad">Nothing matches.</p>}

      <div className="grid">
        {shown.map((item) => (
          <button key={item.id} className={`card ${isAvailable(item) ? '' : 'dim'}`} onClick={() => setOpen(item)}>
            <Photo src={item.image_url} alt={itemName(item)} />
            <MoreHorizontal className="more" size={18} />
            <div className="card-body">
              <strong>{itemName(item)}</strong>
              <span>{itemSub(item)}</span>
              <Availability item={item} />
            </div>
          </button>
        ))}
      </div>

      <input ref={fileInput} type="file" accept="image/*" multiple hidden onChange={(e) => upload(e.target.files)} />

      {adding && <AddSheet onClose={() => setAdding(false)} onPhoto={() => fileInput.current?.click()} onUrl={importUrl} />}

      {open && (
        <ItemSheet
          item={open}
          onClose={() => {
            setOpen(null)
            setIsNew(false)
          }}
          actions={
            <>
              {isNew && <Notice>Added. Check the details; fix anything wrong below.</Notice>}
              <EditItem item={open} onSave={(patch) => change(() => api.updateItem(open.id, patch))} />
              <button
                className="btn"
                onClick={() => change(() => api.setAvailability(open.id, isAvailable(open) ? 'laundry' : 'available'))}
              >
                {isAvailable(open) ? 'Mark as in the laundry' : 'Mark as available'}
              </button>
              <button
                className="btn danger"
                onClick={() => {
                  if (confirm(`Delete ${itemName(open)} from your closet?`)) change(() => api.deleteItem(open.id))
                }}
              >
                Delete item
              </button>
            </>
          }
        />
      )}
    </div>
  )
}

function AddSheet({ onClose, onPhoto, onUrl }: { onClose: () => void; onPhoto: () => void; onUrl: (url: string) => void }) {
  const [url, setUrl] = useState('')
  return (
    <Sheet title="Add an item you own" onClose={onClose}>
      <div className="stack">
        <button className="btn primary" onClick={onPhoto}>
          <Camera size={18} /> Upload photo
        </button>
        <p className="hint">One piece per photo. Worn, on a hanger or laid flat all work: the garment is cut out of the picture.</p>
        <form
          className="stack"
          onSubmit={(e) => {
            e.preventDefault()
            if (url.trim()) onUrl(url.trim())
          }}
        >
          <label className="field">
            <span>Or paste a product link</span>
            <input type="url" inputMode="url" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://shop.com/product" />
          </label>
          <button className="btn" type="submit" disabled={!url.trim()}>
            <LinkIcon size={18} /> Fetch from link
          </button>
        </form>
      </div>
    </Sheet>
  )
}

function EditItem({ item, onSave }: { item: Item; onSave: (patch: Partial<Item>) => void }) {
  const [editing, setEditing] = useState(false)
  const [d, setD] = useState({
    subtype: item.subtype || '',
    category: item.category || 'top',
    color: item.colors?.[0] || '',
    warmth: item.warmth || 3,
    formality: item.formality || 3,
  })
  if (!editing)
    return (
      <button className="btn" onClick={() => setEditing(true)}>
        Edit details
      </button>
    )
  return (
    <form
      className="stack edit"
      onSubmit={(e) => {
        e.preventDefault()
        const colors = d.color.trim() ? [d.color.trim().toLowerCase(), ...(item.colors || []).slice(1)] : item.colors || []
        onSave({ subtype: d.subtype.trim(), category: d.category, colors, warmth: d.warmth, formality: d.formality })
      }}
    >
      <label className="field">
        <span>Name</span>
        <input value={d.subtype} onChange={(e) => setD({ ...d, subtype: e.target.value })} />
      </label>
      <label className="field">
        <span>Category</span>
        <select value={d.category} onChange={(e) => setD({ ...d, category: e.target.value })}>
          {['top', 'bottom', 'outerwear', 'shoes', 'dress', 'accessory'].map((c) => (
            <option key={c}>{c}</option>
          ))}
        </select>
      </label>
      <label className="field">
        <span>Main colour</span>
        <input value={d.color} onChange={(e) => setD({ ...d, color: e.target.value })} />
      </label>
      <label className="field">
        <span>Warmth {d.warmth} / 5</span>
        <input type="range" min={1} max={5} value={d.warmth} onChange={(e) => setD({ ...d, warmth: +e.target.value })} />
      </label>
      <label className="field">
        <span>Formality {d.formality} / 5</span>
        <input type="range" min={1} max={5} value={d.formality} onChange={(e) => setD({ ...d, formality: +e.target.value })} />
      </label>
      <button className="btn primary" type="submit">
        Save details
      </button>
    </form>
  )
}
