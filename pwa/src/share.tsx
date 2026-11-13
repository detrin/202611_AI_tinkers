import { useEffect, useState } from 'react'
import { api, cutOut, waitForJob } from './api'
import { errorText } from './format'
import { getProfiles, saveProfiles } from './store'
import { Notice, Sheet } from './ui'

interface Shared {
  files: File[]
  link: string
}

/** Reads what the service worker stored when another app shared into this one. */
async function readInbox(): Promise<Shared> {
  const inbox = await caches.open('share-inbox')
  const metaRes = await inbox.match('/__share/meta')
  const meta = metaRes ? await metaRes.json() : { files: 0, url: '', text: '' }
  const files: File[] = []
  for (let i = 0; i < meta.files; i++) {
    const res = await inbox.match(`/__share/file-${i}`)
    if (!res) continue
    const blob = await res.blob()
    files.push(new File([blob], `shared-${i}.jpg`, { type: blob.type || 'image/jpeg' }))
  }
  // Apps put the link in `url` or bury it in `text`.
  const link = meta.url || (String(meta.text).match(/https?:\/\/\S+/) || [''])[0]
  return { files, link }
}

const clearInbox = async () => {
  await caches.delete('share-inbox')
}

export default function ShareInbox({ onDone }: { onDone: (goTo?: 'closet' | 'style') => void }) {
  const [shared, setShared] = useState<Shared | null>(null)
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const [profileId, setProfileId] = useState(getProfiles()[0]?.profile_id || '')
  const profiles = getProfiles()

  useEffect(() => {
    readInbox().then(setShared).catch(() => setShared({ files: [], link: '' }))
  }, [])

  const close = (goTo?: 'closet' | 'style') => {
    clearInbox()
    onDone(goTo)
  }

  async function toCloset() {
    if (!shared) return
    setError('')
    try {
      if (shared.files.length) {
        setBusy('Reading the photo. About 15 seconds each.')
        await api.addItems(await Promise.all(shared.files.map(cutOut)))
      } else {
        setBusy('Fetching the product page. This can take a minute or two.')
        const { job_id } = await api.importUrl(shared.link, 'product')
        await waitForJob(job_id)
      }
      close('closet')
    } catch (e) {
      setError(errorText(e))
      setBusy('')
    }
  }

  async function toStyle() {
    if (!shared) return
    setError('')
    setBusy('Saving the look. About 15 seconds each.')
    try {
      const looks = await api.addLooks(shared.files, shared.files.length ? [] : [shared.link])
      saveProfiles(
        profiles.map((p) =>
          p.profile_id === profileId ? { ...p, reference_ids: [...looks.map((l) => l.id), ...p.reference_ids] } : p,
        ),
      )
      close('style')
    } catch (e) {
      setError(
        shared.files.length
          ? errorText(e)
          : `This link could not be saved as an image (${errorText(e)}). Share the picture itself, or a direct image link.`,
      )
      setBusy('')
    }
  }

  const empty = shared && !shared.files.length && !shared.link

  return (
    <Sheet title="Add to Good Enough" onClose={() => close()}>
      {!shared && <p className="muted">Opening what you shared…</p>}
      {empty && <Notice kind="error">Nothing usable was shared. Share a photo or a link.</Notice>}
      {shared && !empty && (
        <>
          <p className="muted">
            {shared.files.length ? `${shared.files.length} photo${shared.files.length > 1 ? 's' : ''}` : shared.link}
          </p>
          {error && <Notice kind="error">{error}</Notice>}
          {busy ? (
            <p className="busy">{busy}</p>
          ) : (
            <div className="stack">
              <button className="btn primary" onClick={toCloset}>
                I own this: add to My Closet
              </button>
              <label className="field">
                <span>Or save as a style reference for</span>
                <select value={profileId} onChange={(e) => setProfileId(e.target.value)}>
                  {profiles.map((p) => (
                    <option key={p.profile_id} value={p.profile_id}>
                      {p.name}
                    </option>
                  ))}
                </select>
              </label>
              <button className="btn" onClick={toStyle}>
                I like this: add to My Style
              </button>
            </div>
          )}
        </>
      )}
    </Sheet>
  )
}
