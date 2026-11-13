import type { Item, Occasion, StyleProfile, Weather } from './types'

export const title = (s: string | null | undefined) =>
  (s || '').replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())

export const itemName = (i: Item) => title(i.subtype || i.category || 'Item')
export const itemSub = (i: Item) => [title(i.category), title(i.colors?.[0])].filter(Boolean).join(' · ')
export const isAvailable = (i: Item) => !i.availability || i.availability === 'available'

export function weatherLine(w: Weather | undefined): string | null {
  if (w?.temperature_c != null) {
    const rain = (w.rain_probability ?? 0) * 100
    const sky = rain >= 50 ? 'Rain expected' : rain >= 20 ? 'Rain possible' : 'Dry'
    const feels = w.feels_like_c != null ? `, feels like ${Math.round(w.feels_like_c)}°` : ''
    return `${Math.round(w.temperature_c)}°C${feels} · ${sky}`
  }
  if (!w || w.temperature_2m_max == null) return null
  const rain = w.precipitation_probability_max ?? 0
  const sky = rain >= 50 ? 'Rain expected' : rain >= 20 ? 'Rain possible' : 'Dry'
  const low = w.temperature_2m_min != null ? ` / ${Math.round(w.temperature_2m_min)}°` : ''
  return `${Math.round(w.temperature_2m_max)}°C${low} · ${sky}`
}

export const profileLine = (p: StyleProfile) => [p.name, ...p.style_tags.map(title)].join(' · ')

/**
 * The backend takes the occasion as free text, so the style profile and the availability rule travel inside it.
 * This is what makes switching profile change the next recommendation.
 */
export function eventPrompt(o: Occasion, p: StyleProfile | undefined, avoidItemIds: string[] = []): string {
  const parts = [o.time ? `${o.title} at ${o.time}` : o.title]
  if (p) {
    const bits = [
      p.style_tags.length ? `mood ${p.style_tags.join(', ')}` : '',
      p.preferred_colors.length ? `preferred colours ${p.preferred_colors.join(', ')}` : '',
      p.avoid_colors.length ? `avoid colours ${p.avoid_colors.join(', ')}` : '',
      p.preferred_fit.length ? `fit ${p.preferred_fit.join(' or ')}` : '',
      `formality ${p.formality_range[0]} to ${p.formality_range[1]} of 5`,
    ].filter(Boolean)
    parts.push(`Style profile "${p.name}": ${bits.join('; ')}`)
  }
  parts.push('Use only items whose availability is "available"')
  if (avoidItemIds.length) parts.push(`Give a different combination from this one: ${avoidItemIds.join(', ')}`)
  return parts.join('. ')
}

/** Note for the agent endpoint (500 characters at most). The calendar wins; the typed occasion is the fallback. */
export function todayNote(o: Occasion, p: StyleProfile | undefined): string {
  const occasion = o.time ? `${o.title} at ${o.time}` : o.title
  const parts = [`If the calendar has no event, the occasion is: ${occasion}`]
  if (p) {
    const bits = [
      p.style_tags.length ? `mood ${p.style_tags.join(', ')}` : '',
      p.preferred_colors.length ? `prefer ${p.preferred_colors.join(', ')}` : '',
      p.avoid_colors.length ? `avoid ${p.avoid_colors.join(', ')}` : '',
      `formality ${p.formality_range[0]}-${p.formality_range[1]} of 5`,
    ].filter(Boolean)
    parts.push(`Style "${p.name}": ${bits.join('; ')}`)
  }
  return parts.join('. ').slice(0, 500)
}

export const sentences = (text: string | null) =>
  (text || '')
    .split(/(?<=[.!?])\s+/)
    .map((s) => s.trim())
    .filter(Boolean)

export const errorText = (e: unknown) => (e instanceof Error ? e.message : String(e))
