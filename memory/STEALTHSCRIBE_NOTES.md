# Stealth-Scribe — notes for the next agent

Read `AGENT_HANDOFF_PLAYBOOK.md` in this folder first. Everything below is what
is *different* about Stealth-Scribe, plus which playbook lessons are already applied so
you don't redo them.

## What is different from WarVid

| | WarVid | Stealth-Scribe |
|---|---|---|
| Hosting | Emergent → NAS | NAS only, no Emergent |
| Frontend build | CRA | **Vite** (no babel/ajv/`--legacy-peer-deps` class of failure) |
| Auth | Emergent Google, GOD/ADMIN/USER | **None.** LAN-only. See "Before exposing it" |
| Heavy compute | none | **GPU worker on a separate PC**, claims jobs over HTTP |
| Public? | yes, SEO + AdSense | no. No sitemap, no robots.txt, no legal pages, no PWA SW |
| Port | 8451 | **8458** |

## Playbook lessons already applied

- **§1 chunked uploads** — 5 MB parts, `init`/`chunk`/`complete`, exponential
  backoff over 4 attempts, `upload_id` regex-validated before it touches a path,
  **size cap enforced after reassembly**, hourly sweep of abandoned chunk dirs,
  `client_max_body_size 100M`.
- **§2 GHCR pipeline** — build in Actions, pull on the NAS, compose is pull-only.
- **§3 tunnel readiness** — uvicorn runs with `--proxy-headers
  --forwarded-allow-ips "*"` so it reads correct client info if a tunnel is
  added later. No tunnel is configured yet, by choice.
- **§7 Pydantic `extra='forbid'`** — every request body is a model, none are
  bare dicts. Schema-invalid payloads return 422; tests should expect 422.
- **§14 idempotent startup migrations** — `_backfill()` in `server.py`. Add to
  it rather than writing one-off scripts.
- **§19 SPA fallback lying about missing files** — nginx returns a real 404 for
  `.md`/`.txt`/`.xml` instead of the React shell.

## Deliberately not done

- **§10 PWA service worker.** The manifest is there for "add to home screen",
  but there is no SW. Stealth-Scribe's content is a live job queue — a stale-HTML
  cache would show wrong transcription progress, and §10's own warning about
  SWs not updating mid-session is the reason to skip it.
- **§12 SEO surface, §13 legal pages.** Private tool, no public traffic.
- **§15 `include_router` trap.** Not applicable — routes are declared directly
  on `app`, there is no router to include. If you refactor to a router, move the
  `include_router` call to the very end of the file.

## Before exposing it to the internet

There is **no login**. Anyone who reaches the URL reads every transcript.
Put Cloudflare Access in front of it (Zero Trust → Access → Applications →
self-hosted, restrict to your email) before adding a tunnel route. If you'd
rather build real auth, §4 and §5 of the playbook are the pattern.

## Order of operations if you extend it

1. Get the Actions build green and the NAS deploy working before any feature work
2. Worker connected and one real recording transcribed end to end
3. Then features — the data model in `backend/server.py` is the source of truth
4. Bump `frontend/src/config/version.js`, `index.html` title, `manifest.json`
   name together. There is no `sync-version.js` hook yet; add one if this grows.

## The one thing that will bite you

The worker is a *separate machine*. If jobs sit in `queued` forever, the app is
working correctly — the worker isn't running, or its `worker_token` doesn't
match `WORKER_TOKEN` in the compose file. Check the worker's console window
before you debug the backend.
