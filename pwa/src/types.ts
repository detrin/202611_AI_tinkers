export type Availability = 'available' | 'laundry' | 'lent' | 'stored'

export interface Item {
  id: string
  status: 'owned' | 'wanted'
  category: string | null
  subtype: string | null
  colors: string[] | null
  pattern: string | null
  material: string | null
  fit: string | null
  formality: number | null
  warmth: number | null
  style_tags: string[] | null
  availability: Availability | null
  image_url: string | null
  source_type: string | null
  source_url: string | null
}

export interface Weather {
  city?: string
  temperature_2m_max?: number
  temperature_2m_min?: number
  precipitation_probability_max?: number
  wind_speed_10m_max?: number
  /** Hourly shape returned by the agent endpoint. rain_probability is 0 to 1. */
  temperature_c?: number
  feels_like_c?: number
  rain_probability?: number | null
}

export interface DayEvent {
  title: string
  start_time: string
  location: string | null
  place_category?: string | null
}

export interface Step {
  tool: string
  summary: string
}

export interface Outfit {
  /** Present only when the agent endpoint (/outfits/today) answered. */
  context?: { events?: DayEvent[]; commute?: { mode?: string | null } }
  steps?: Step[]
  from_fallback?: boolean
  id: string
  date: string
  event: string
  city: string
  weather: Weather
  item_ids: string[]
  explanation: string | null
  missing_item_tip: string | null
  items: Item[]
}

export interface Look {
  id: string
  image_url: string | null
  source_url: string | null
  style_tags: string[] | null
  palette: string[] | null
  formality: number | null
  vibe: string | null
}

/** A Pinterest look from the swipe deck. */
export interface Pin {
  id: string
  /** The liked-looks board returns the pin under this name instead of `id`. */
  pin_id?: string
  image_url: string
  pin_url: string | null
  title: string | null
  style_name: string
  reason: string
}

export interface Job {
  id: string
  status: 'queued' | 'running' | 'done' | 'failed'
  result: Record<string, unknown> | null
  error: string | null
}

export interface User {
  id: string
  name: string
  city: string | null
  style_profile?: { summary?: string; style_tags?: string[]; preferred_colors?: string[] } | null
}

export interface ReferenceSource {
  type: 'pinterest' | 'instagram'
  url: string
  /** `link_only`: saved as a link, nothing fetched. `imported`: posts were fetched and analysed by the backend. */
  sync_status: 'link_only' | 'imported'
}

/** Occasion-based style profile. Kept on this device: the backend has no table for it yet. */
export interface StyleProfile {
  profile_id: string
  name: string
  icon: 'office' | 'weekend' | 'date' | 'travel' | 'other'
  style_tags: string[]
  preferred_colors: string[]
  avoid_colors: string[]
  preferred_fit: string[]
  formality_range: [number, number]
  reference_ids: string[]
  reference_sources: ReferenceSource[]
}

export interface Occasion {
  title: string
  time: string
  profile_id: string | null
}
