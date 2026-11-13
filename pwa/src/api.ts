import { getSettings } from './store'
import type { Availability, Item, Job, Look, Outfit, Pin, User } from './types'

export class ApiError extends Error {
  constructor(message: string, public status: number) {
    super(message)
  }
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const { apiBase } = getSettings()
  let res: Response
  try {
    res = await fetch(apiBase.replace(/\/$/, '') + path, init)
  } catch {
    throw new Error('Cannot reach the server. Check the connection in Settings.')
  }
  if (!res.ok) {
    let detail = ''
    try {
      const body = await res.json()
      detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)
    } catch {
      /* not JSON */
    }
    throw new ApiError(detail || `Server error ${res.status}`, res.status)
  }
  return res.json() as Promise<T>
}

const json = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify(body),
})

const uid = () => {
  const id = getSettings().userId
  if (!id) throw new Error('No user selected. Add a user id in Settings.')
  return id
}

function imageForm(files: File[], urls: string[], extra: Record<string, string> = {}) {
  const form = new FormData()
  files.forEach((f) => form.append('files', f))
  urls.forEach((u) => form.append('image_urls', u))
  Object.entries(extra).forEach(([k, v]) => form.append(k, v))
  return form
}

export const api = {
  health: () => req<{ ok: boolean }>('/health'),
  user: () => req<User>(`/users/${uid()}`),
  createUser: (name: string, city: string) => req<User>('/users', json('POST', { name, city })),
  updateUser: (patch: Partial<Pick<User, 'name' | 'city'>>) => req<User>(`/users/${uid()}`, json('PATCH', patch)),

  wardrobe: () => req<Item[]>(`/users/${uid()}/wardrobe`),
  addItems: (files: File[], urls: string[] = []) =>
    req<Item[]>(`/users/${uid()}/wardrobe`, { method: 'POST', body: imageForm(files, urls, { status: 'owned' }) }),
  updateItem: (id: string, patch: Partial<Item>) => req<Item>(`/users/${uid()}/wardrobe/${id}`, json('PATCH', patch)),
  setAvailability: (id: string, availability: Availability) =>
    req<Item>(`/users/${uid()}/wardrobe/${id}`, json('PATCH', { availability })),
  deleteItem: (id: string) => req<unknown>(`/users/${uid()}/wardrobe/${id}`, { method: 'DELETE' }),

  importUrl: (url: string, kind: 'product' | 'instagram') =>
    req<{ job_id: string }>(`/users/${uid()}/imports`, json('POST', { url, kind })),
  job: (id: string) => req<Job>(`/jobs/${id}`),

  looks: () => req<Look[]>(`/users/${uid()}/inspirations`),
  addLooks: (files: File[], urls: string[] = []) =>
    req<Look[]>(`/users/${uid()}/inspirations`, { method: 'POST', body: imageForm(files, urls) }),
  deleteLook: (id: string) => req<unknown>(`/users/${uid()}/inspirations/${id}`, { method: 'DELETE' }),

  swipeDeck: (n: number) => req<Pin[]>(`/users/${uid()}/swipe-deck?n=${n}`),
  swipe: (pinId: string, liked: boolean) =>
    req<unknown>(`/users/${uid()}/swipes`, json('POST', [{ pin_id: pinId, liked, source: 'deck' }])),
  likedPins: () => req<Pin[]>(`/users/${uid()}/swipes?liked=true`),

  /** Agent endpoint: reads calendar, hourly weather, commute and wardrobe through MCP tools. */
  todayOutfit: (note: string) => req<Outfit>(`/users/${uid()}/outfits/today`, json('POST', { note })),
  dailyOutfit: (event: string) => req<Outfit>(`/users/${uid()}/outfits/daily`, json('POST', { event })),
  outfitFeedback: (id: string, feedback: { worn?: boolean; comment?: string }) =>
    req<Outfit>(`/users/${uid()}/outfits/${id}/feedback`, json('POST', feedback)),
}

/**
 * Sends a wardrobe photo to the cutout service and returns the garment alone as a transparent PNG.
 * If the service is down or finds nothing, the original photo is returned so the upload still works.
 */
export async function cutOut(file: File): Promise<File> {
  try {
    const form = new FormData()
    form.append('file', file)
    const res = await fetch('/cutout', { method: 'POST', body: form })
    if (!res.ok) return file
    const blob = await res.blob()
    if (blob.type !== 'image/png') return file
    return new File([blob], file.name.replace(/\.\w+$/, '') + '.png', { type: 'image/png' })
  } catch {
    return file
  }
}

/** Polls a background job (Apify scrapes take one to three minutes) until it finishes. */
export async function waitForJob(jobId: string, timeoutMs = 240_000): Promise<Job> {
  const start = Date.now()
  for (;;) {
    const job = await api.job(jobId)
    if (job.status === 'done') return job
    if (job.status === 'failed') throw new Error(job.error || 'The import failed.')
    if (Date.now() - start > timeoutMs) throw new Error('The import is taking too long. Try again later.')
    await new Promise((r) => setTimeout(r, 3000))
  }
}
