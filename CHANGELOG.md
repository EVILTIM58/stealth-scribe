# Changelog

All notable changes to Stealth-Scribe.

## Versioning policy

| Bump | When |
|------|------|
| **1.0.x** | Fixes, corrections, wording, small adjustments |
| **1.x** | New features, however large |
| **2.0** | Reserved. An **earth-shattering** change only — something that changes what the product fundamentally *is*. Adding features never earns a major bump. |

Every fix and every feature gets an entry here. Keep the newest at the top.

When releasing, update all four together or they drift apart:

- `frontend/src/config/version.js` — `APP_VERSION` and `VERSION_HISTORY`
- `frontend/index.html` — the `<title>`
- `frontend/public/manifest.json` — the `name` field
- `docker-compose.yml` — `APP_VERSION`

---

## [1.0.2] — 2026-08-26

Found by building a clickable prototype of every screen and rendering it at
phone and desktop widths. All three are layout faults that only show up in a
real browser, which is why the code review missed them.

### Fixed
- The Nuke confirmation styled *every* `<strong>` inside the warning panel as a
  block-level red headline, including the inline emphasis in "It happens **the
  moment you press the button**." That sentence rendered in three pieces on
  three lines. The rule is now scoped to the panel's direct child.
- Recording cards pushed the page sideways on a phone. `.rec-list` is a grid
  with an implicit `auto` track, and an `auto` track is sized from its items'
  min-content and is *not* clamped to the container. Pinned to
  `minmax(0, 1fr)`; same fix applied to the admin and people tables.
- Search-match lines never truncated. `.match .txt` had
  `text-overflow: ellipsis`, but a flex item's automatic minimum size is its
  max-content, so instead of ellipsing it stretched the card. Added
  `min-width: 0`.
- The library toolbar (search + Admin + Record + Upload + user chip) was a
  nowrap flex row and overflowed below about 700px. It now gives the search box
  its own row and wraps the controls under it.
- `.app` and `.feature-grid` used bare `1fr` / `minmax(280px, 1fr)` tracks,
  which can exceed a narrow viewport. Now `minmax(0, 1fr)` and
  `minmax(min(280px, 100%), 1fr)`.

### Added
- Two paragraphs in the Nuke warning ran together with no gap. They are now
  spaced.

### Fixed (server-side, found while pushing to GitHub)
- **The backend could not start.** `api_admin.ban_user` annotated its body as
  `models.BanIn`, but no such class existed. `from __future__ import
  annotations` defers the annotation, so it did not fail at definition time —
  FastAPI resolves it when the `@router.post` decorator builds the route, which
  happens at import. Every boot raised `AttributeError` on importing
  `api_admin`. `BanIn` is now declared with the fields the endpoint reads and
  the client sends.
- **Every password reset returned 500.** `reset()` tested
  `payload.accept_terms`, but `ResetIn` declares no such field and the client
  never sends one, so the attribute access raised `AttributeError`. The check
  had been copy-pasted from `signup()`, where it belongs. Terms are accepted at
  signup; choosing a new password is not the moment to re-litigate them.
- `settings.APP_VERSION` still defaulted to `1.0.1`. Harmless in production
  because docker-compose sets it explicitly, but exactly the drift the release
  checklist above exists to prevent.

Both import-time faults are now caught by a static audit: one pass resolves
every `models.*` reference against the declared classes, another resolves every
cross-module `module.attr` reference across all 16 backend modules. Both are
clean.

### Changed
- Repository renamed from `eyespy` to `stealth-scribe`, so it matches the app
  and the `stealthscribe-*` GHCR image names. README, DEPLOYMENT and the
  handoff playbook updated; nothing in the build depends on the repo name.

---

## [1.0.1] — 2026-08-16

### Changed
- Canonical domain set to **stealth-scribe.com**. `SITE_BASE_URL`, the OAuth
  callback URLs, the sitemap, email links and the contact/legal/DMCA addresses
  all derive from it.

### Fixed
- Account deletion instructions said "email us" in the Terms and on the account
  page while the Nuke button already did it instantly. Both now point at the
  dashboard.
- `.admin` was used both as the admin page container and as a role-badge
  modifier, so every ADMIN badge inherited the page's width and padding and
  rendered as a large empty box. Page containers renamed to `.admin-page` and
  `.account-page`.
- The search reticle was invisible: `clip-path` on the input creates a stacking
  context, so the input painted over the absolutely-positioned icon. Fixed with
  an explicit `z-index`.

---

## [1.0.0] — 2026-08-16

First complete release.

### Transcription
- Transcribes audio **and video** — mp3, wav, m4a, wma, ogg, flac, aac, opus, amr,
  and mp4, mov, mkv, avi, wmv, webm. Video has its audio track extracted
  automatically and stays playable next to the transcript.
- Runs on OpenAI Whisper on your own GPU. Nothing is sent to a transcription API.
- Whisper model selectable from tiny to large-v3.
- Timestamps on every turn: elapsed time plus the real wall-clock time it was
  said, derived from the recording's date.
- No ffmpeg binary required — PyAV decodes every container, video included.

### Translation
- Around 99 languages translated into English using Whisper's native translate
  task. English is the only target language.
- The original and the English are both kept, aligned by timestamp and by speaker.
- Read English, the original, or both side by side.
- Right-to-left rendering for Arabic, Hebrew, Farsi, Urdu and Pashto.
- Summaries are written from the English when a translation exists.
- English search finds foreign-language recordings.

### Speakers and voice recognition
- Speaker separation via pyannote 3.1, with a no-token fallback detector.
- Speakers assigned at word level and segments re-cut on speaker change, so a
  reply never starts inside the previous speaker's paragraph.
- Click a speaker name in the transcript to rename them everywhere in it.
- Reassign a single misattributed turn to the correct speaker.
- **Voice ID** — naming a voice stores a voiceprint, and that person is
  recognised automatically in later recordings.
- Confident matches applied automatically; weaker ones ask before labelling.
- One identity is never assigned to two speakers in the same recording, and
  near-ties are demoted to a suggestion rather than guessed.
- People library: see who is known, merge duplicates, forget a voice.

### Summaries
- Overview, key points, action items and questions raised.
- Runs offline on your own hardware at no cost. Optional AI summary via an API
  key held on the worker, never on the server.

### Recording
- Record live from a phone or desktop microphone with a level meter, timer and
  pause/resume, then upload and queue automatically.
- Screen wake lock while recording where the browser supports it.

### Files and downloads
- Every finished recording keeps **audio + PDF + plain text** together on disk.
- Download any of the three on demand.
- Downloads are resumable — a dropped connection continues rather than restarting.
- PDFs embed Unicode fonts and shape Arabic and Hebrew correctly.
- Print view for a clean paper copy.
- Renaming a speaker rewrites the .txt and .pdf so the files never drift from
  what the app shows.

### Uploads
- Chunked resumable uploads in 5 MB parts with exponential backoff over four
  attempts. 4xx failures fail fast instead of retrying pointlessly.
- Upload id validated before it touches the filesystem.
- Size cap enforced after reassembly, not on the client's declared size.
- Hourly sweep of abandoned upload chunks.

### Accounts and roles
- Three tiers, no subscription at any level:
  - **USER (1)** — every feature except the admin page.
  - **ADMIN (2)** — adds user administration and timed suspensions.
  - **GOD (3)** — the hardcoded owner; the only role that can promote, demote or
    delete an account.
- Sign in with Google, Facebook, or email and password.
- GOD is resolved from the email address on every request, never from a stored
  field, so it cannot be granted by editing the database.
- An admin can never promote, demote or suspend another admin.
- Suspensions require a duration — 1 day, 3 days, 1 week, 1 month or permanent —
  expire on their own, and end every active session immediately.
- Admin page shows photo, name, email, tier, ban status and login provider.
- Email confirmation and self-service password reset.
- Per-user daily minutes quota, since transcription runs on hardware you pay for.

### Privacy and data
- Recordings are private to the account that uploaded them; admins can see all
  for moderation.
- Voiceprints are scoped per user, never shared, and never sent to the browser.
- **Nuke** — irreversibly delete every recording you own and everything derived
  from it, behind a typed confirmation. Optionally erases your account too,
  **instantly**: no support ticket, no waiting period, no review, no undo. The
  owner account is the one exception, since deleting it would lock everyone out
  of administering the server.
- Consent is recorded at signup with a timestamp: a required tick-box confirming
  the user has the right to upload what they process.
- Public site with About, Contact, Privacy, Terms, Community Guidelines, DMCA
  and this changelog, plus sitemap.xml and robots.txt.

### Deployment
- React + FastAPI + MongoDB, built to GHCR by GitHub Actions, deployed by
  docker-compose on the NAS at port 8458.
- A GPU worker runs on a separate Windows PC and claims jobs over HTTP, so the
  NAS never does the heavy lifting. Jobs queue safely when the PC is off.
- Atomic job claiming with leases, so a worker that dies mid-job releases it.
- Configuration report printed at boot naming exactly what is and isn't set up.
