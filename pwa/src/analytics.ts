import type { PostHog } from 'posthog-js'

// Product analytics (PostHog, EU cloud). The project key is a public client key (phc_), safe to ship.
// Override with VITE_POSTHOG_KEY / VITE_POSTHOG_HOST, or turn off with VITE_POSTHOG_DISABLED=1.
// posthog-js is loaded lazily (its own chunk) so it never delays the first paint.
const KEY = (import.meta.env.VITE_POSTHOG_KEY as string | undefined) || 'phc_qTV2Cpqqj7kwyPQsHgJDqe8EfY5r6MrKudTmRvM9u9zi'
const HOST = (import.meta.env.VITE_POSTHOG_HOST as string | undefined) || 'https://eu.i.posthog.com'
const enabled = import.meta.env.VITE_POSTHOG_DISABLED !== '1'

let client: Promise<PostHog | null> = Promise.resolve(null)

export function initAnalytics(userId?: string) {
  if (!enabled) return
  client = import('posthog-js')
    .then(({ default: posthog }) => {
      posthog.init(KEY, {
        api_host: HOST,
        defaults: '2026-08-30', // pageviews on in-app navigation, pageleave, autocapture
        person_profiles: 'identified_only',
      })
      return posthog
    })
    .catch(() => null) // blocked by an ad blocker or offline: the app works without analytics
  identify(userId)
}

/** Tie events to the backend user id (set in Settings). */
export function identify(userId?: string) {
  if (userId) void client.then((ph) => ph?.identify(userId))
}

/** Custom event, e.g. track('outfit_swiped', { liked: true }). */
export function track(event: string, props?: Record<string, unknown>) {
  void client.then((ph) => ph?.capture(event, props))
}
