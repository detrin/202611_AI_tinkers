import type { Occasion, Outfit, StyleProfile } from './types'

function load<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key)
    return raw ? (JSON.parse(raw) as T) : fallback
  } catch {
    return fallback
  }
}

function save(key: string, value: unknown) {
  try {
    localStorage.setItem(key, JSON.stringify(value))
  } catch {
    /* storage full or blocked: the app still works for this session */
  }
}

export interface Settings {
  apiBase: string
  userId: string
}

export const getSettings = (): Settings =>
  load('settings', { apiBase: '/api', userId: (import.meta.env.VITE_USER_ID as string | undefined) || '' })
export const saveSettings = (s: Settings) => save('settings', s)

const profile = (
  id: string,
  name: string,
  icon: StyleProfile['icon'],
  tags: string[],
  formality: [number, number],
): StyleProfile => ({
  profile_id: id,
  name,
  icon,
  style_tags: tags,
  preferred_colors: [],
  avoid_colors: [],
  preferred_fit: ['regular'],
  formality_range: formality,
  reference_ids: [],
  reference_sources: [],
})

const DEFAULT_PROFILES: StyleProfile[] = [
  profile('office', 'Office', 'office', ['minimal', 'clean', 'smart casual'], [3, 4]),
  profile('weekend', 'Weekend', 'weekend', ['relaxed', 'casual', 'effortless'], [1, 2]),
  profile('date', 'Date', 'date', ['polished', 'modern', 'refined'], [3, 4]),
  profile('travel', 'Travel', 'travel', ['comfortable', 'functional'], [1, 3]),
]

export const getProfiles = (): StyleProfile[] => load('profiles', DEFAULT_PROFILES)
export const saveProfiles = (p: StyleProfile[]) => save('profiles', p)

export const getOccasion = (): Occasion => load('occasion', { title: 'Casual day', time: '', profile_id: 'weekend' })
export const saveOccasion = (o: Occasion) => save('occasion', o)

export interface SavedOutfit {
  outfit: Outfit
  selected: boolean
}
export const getLastOutfit = (): SavedOutfit | null => load<SavedOutfit | null>('lastOutfit', null)
export const saveLastOutfit = (o: SavedOutfit | null) => save('lastOutfit', o)

export const today = () => new Date().toLocaleDateString('sv-SE') // YYYY-MM-DD in local time
