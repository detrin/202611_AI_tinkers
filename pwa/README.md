# Good Enough PWA

The phone app: Today, My Closet, My Style, Settings. React, TypeScript and Vite. It follows Sun's UI spec and talks to the backend in `../backend` (API reference: `../backend/schemas.md`).

## Run

```bash
cd pwa
npm install
cp .env.example .env      # set BACKEND_URL to where the backend runs
npm run dev               # http://localhost:5173
```

Open Settings in the app and paste a user id (ask Dan for the seeded test user), or create a user there.

The browser only talks to the Vite server; `/api/*` is forwarded to `BACKEND_URL`. That means the backend needs no CORS setup, and one HTTPS tunnel covers both the app and the API.

### Without the real backend

```bash
uv run python pwa/dev/fake_api.py     # from the repo root
```

This runs the real FastAPI app on in-memory fakes with eight seeded items, and prints a user id to paste into Settings. No keys needed. The "stylist" is a stub that picks one available item per category.

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
| Occasion (event and time) | Typed by the user, and labelled so. Switch to the calendar when `POST /users/{uid}/outfits/today` exists |
| Style profiles (Office, Weekend, ...) | Stored on the phone. The backend has no table for them. Their tags, colours, fit and formality are sent inside the `event` text of `POST /outfits/daily`, which is how the selected profile affects the outfit |
| Pinterest board | Saved as a link only, and labelled so |
| "Is it good enough?" (Today → Already dressed?) | Live: `POST /users/{uid}/is-it-good-enough`. Weather from the phone's position, else the saved city. Closet swaps only when switched on |

"Try another" and "in the laundry" also work through the `event` text: it asks for available items only and for a different combination. The backend does not enforce availability itself yet.

## Files

- `src/api.ts`: every backend call.
- `src/store.ts`: what is kept on the phone (settings, occasion, style profiles, last outfit).
- `src/format.ts`: `eventPrompt()` builds the text sent as the occasion.
- `src/pages/`: one file per tab.
- `src/share.tsx` and `public/sw.js`: receiving photos and links shared from other apps.
