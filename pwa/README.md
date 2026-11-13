# Good Enough PWA

The phone app: Today, My Closet, My Style, Settings. React, TypeScript and Vite. It follows Sun's UI spec and talks to the backend in `../backend` (API reference: `../backend/schemas.md`).

## Run

```bash
cd pwa
npm install
npm run dev               # http://localhost:5173
```

Open Settings in the app and paste a user id (ask Dan for the seeded test user), or create a user there.

The browser only talks to the Vite server; `/api/*` is forwarded to `BACKEND_URL`. That means the backend needs no CORS setup, and one HTTPS tunnel covers both the app and the API.

To use the Today calendar flow, run Vite with the same `TODAY_API_TOKEN` as the backend. Set `VITE_USER_ID` to the demo user ID or select that user in Settings. For a shared demo, use a dedicated calendar with demo events. Keep the calendar URL and token in server-side configuration.

### Without the real backend

```bash
TODAY_API_TOKEN=local-today-demo uv run python pwa/dev/fake_api.py   # from the repo root
```

This runs FastAPI with an in-memory wardrobe, a sample calendar, simulated forecasts, and a demo stylist. Start Vite with the same local token and set `VITE_USER_ID` to the printed user ID. Today shows the 09:30 team meeting and the 18:30 event at Café Savoy. Mark Chino Pants as in the laundry to see Jeans in the next outfit.

## On a phone (needed for install and for sharing into the app)

Install and the share sheet need HTTPS and Android Chrome. iPhones cannot share into a PWA.

```bash
npm run build && npm run preview      # http://localhost:4173, also forwards /api
cloudflared tunnel --url http://localhost:4173
```

Open the tunnel address on the phone, then Chrome menu → "Add to Home screen" / "Install app". After that "Good Enough" appears in the share sheet for photos and links.

## What is live and what is not

| Feature | State |
|---|---|
| Outfit, weather, wardrobe, availability, reference images, product-link import, Instagram import | Live, through the backend |
| Occasion (event and time) | Today shows each calendar event with its local time, forecast and venue category when available. The typed occasion is used on days without calendar events. |
| Style profiles (Office, Weekend, ...) | Stored on the phone. The app includes the selected profile in its outfit request. |
| Pinterest board | Saved as a link only, and labelled so |
| "Is it good enough?" (Today → Already dressed?) | Live: `POST /users/{uid}/is-it-good-enough`. Weather from the phone's position, else the saved city. Closet swaps only when switched on |

Marking an item as in the laundry updates its wardrobe availability before requesting another outfit. The Today endpoint excludes that item from the next recommendation.

## Files

- `src/api.ts`: every backend call.
- `src/store.ts`: what is kept on the phone (settings, occasion, style profiles, last outfit).
- `src/format.ts`: `eventPrompt()` builds the text sent as the occasion.
- `src/pages/`: one file per tab.
- `src/share.tsx` and `public/sw.js`: receiving photos and links shared from other apps.
