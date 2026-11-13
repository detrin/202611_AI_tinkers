import { identify } from './analytics'
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

/** The demo user on the shared backend (GET /users/demo-user). Used until another id is set in Settings. */
const DEMO_USER_ID = '8b63ae0d-35e8-4cc7-8896-f1785c47d54c'
// Bump the key to make every phone forget an older user id and pick up the default again.
const SETTINGS_KEY = 'settings-v2'

export interface Settings {
  apiBase: string
  userId: string
}

export const getSettings = (): Settings =>
  load(SETTINGS_KEY, { apiBase: '/api', userId: (import.meta.env.VITE_USER_ID as string | undefined) || DEMO_USER_ID })
export const saveSettings = (s: Settings) => {
  save(SETTINGS_KEY, s)
  identify(s.userId)
}

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

/** A plan kept in the app. `day` is 0 for today, 1 for tomorrow. */
export interface Plan {
  day: 0 | 1
  time: string
  title: string
  location: string
}

/** Demo plans stored in the app itself. They are not read from a calendar service. */
export const PLANS: Plan[] = [
  { day: 0, time: '19:30', title: 'AI Agents for the Rest of Us: hackathon demos and winners (AI Tinkerers Prague)', location: 'Prague' },
  { day: 0, time: '21:00', title: 'Dinner with the team after the hackathon', location: 'Restaurant, Prague Old Town' },
  { day: 1, time: '10:00', title: 'Brunch with friends', location: 'Café, Vinohrady' },
  { day: 1, time: '14:00', title: 'Client meeting', location: 'Office, Karlín' },
  { day: 1, time: '19:30', title: 'Dinner date', location: 'Fine dining restaurant, Malá Strana' },
]

/** The next plan that started less than 90 minutes ago (19:30 stays until 21:00); tomorrow's first once today is over. */
export function nextPlan(now = new Date()): Plan | undefined {
  const minutes = now.getHours() * 60 + now.getMinutes()
  const mins = (p: Plan) => +p.time.slice(0, 2) * 60 + +p.time.slice(3)
  return PLANS.find((p) => p.day === 0 && mins(p) + 90 > minutes) ?? PLANS.find((p) => p.day === 1)
}

export const getOccasion = (): Occasion => load('occasion', { title: 'Casual day', time: '', profile_id: 'weekend' })
export const saveOccasion = (o: Occasion) => save('occasion', o)

export interface SavedOutfit {
  outfit: Outfit
  selected: boolean
}
export const getLastOutfit = (): SavedOutfit | null => load<SavedOutfit | null>('lastOutfit-v3', null)
export const saveLastOutfit = (o: SavedOutfit | null) => save('lastOutfit-v3', o)

export const today = () => new Date().toLocaleDateString('sv-SE') // YYYY-MM-DD in local time
