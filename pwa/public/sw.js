// Service worker: (1) receives images/links shared from other apps, (2) keeps the app shell available offline.
const SHELL = 'shell-v1'
const INBOX = 'share-inbox'

self.addEventListener('install', () => self.skipWaiting())
self.addEventListener('activate', (e) => e.waitUntil(self.clients.claim()))

async function receiveShare(request) {
  const form = await request.formData()
  const inbox = await caches.open(INBOX)
  for (const key of await inbox.keys()) await inbox.delete(key)
  const files = form.getAll('images').filter((f) => f instanceof File)
  let n = 0
  for (const file of files) {
    await inbox.put(`/__share/file-${n++}`, new Response(file, { headers: { 'Content-Type': file.type || 'image/jpeg' } }))
  }
  const meta = { title: form.get('title') || '', text: form.get('text') || '', url: form.get('url') || '', files: n }
  await inbox.put('/__share/meta', new Response(JSON.stringify(meta), { headers: { 'Content-Type': 'application/json' } }))
  return Response.redirect('/?shared=1', 303)
}

self.addEventListener('fetch', (event) => {
  const { request } = event
  const url = new URL(request.url)
  if (url.origin !== self.location.origin) return
  if (request.method === 'POST' && url.pathname === '/share') {
    event.respondWith(receiveShare(request))
    return
  }
  if (request.method !== 'GET' || url.pathname.startsWith('/api/')) return
  // Network first, so a new build is picked up at once; cache only as the offline fallback.
  event.respondWith(
    fetch(request)
      .then((res) => {
        if (res.ok) {
          const copy = res.clone()
          caches.open(SHELL).then((c) => c.put(request, copy))
        }
        return res
      })
      .catch(async () => (await caches.match(request)) || (await caches.match('/')) || Response.error()),
  )
})
