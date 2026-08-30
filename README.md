<div align="center">

# STEALTH-SCRIBE

**Audio in. Transcribe to English. Save as PDF.**

*Clear. Accurate. Secure.*

</div>

---

Stealth-Scribe turns voice recordings and video into readable, searchable text — with a
summary at the top and every speaker labelled. It runs entirely on hardware you
own: the site lives on the NAS, the heavy AI work happens on your gaming PC's
GPU, and no audio ever leaves your network.

| | |
|---|---|
| **Site** | https://stealth-scribe.com |
| **LAN** | http://10.0.0.146:8458 |
| **Repo** | github.com/EVILTIM58/stealth-scribe |
| **NAS port** | 8458 |
| **Images** | `ghcr.io/eviltim58/stealthscribe-frontend`, `ghcr.io/eviltim58/stealthscribe-backend` |

## What it does

- **Transcribes audio and video** — mp3, wav, m4a, wma, ogg, flac and mp4, mov,
  mkv, avi, wmv. For video the audio track is pulled out automatically and the
  video stays playable in the browser.
- **Three tiers, no subscription** — sign in with Google or Facebook (email and
  password also works) and you have every feature. **USER** (tier 1) gets the
  lot except the admin page. **ADMIN** (tier 2) adds user administration and can
  suspend users for a chosen period. **GOD** (tier 3) is the hardcoded owner and
  is the only one who can promote, demote or delete. An admin can never act on
  another admin. Your recordings are private to your account — nobody but you
  and an admin can see them.
- **Records live** — tap Record and capture straight from your phone or desktop
  microphone, with a level meter and timer; it uploads and queues like any other
  file. Note that browsers only allow microphone access over HTTPS, so this
  needs one of the three fixes in DEPLOYMENT.md Step 11.
- **Separates speakers, and remembers them** — labels turns as Voice 1 / Voice 2,
  and you rename them to real names by clicking the name in the transcript. That
  naming is the training signal: Stealth-Scribe captures a voiceprint for each person
  and recognises them automatically in every later recording. Confident matches
  are applied; weaker ones ask you first. Wrong turn? Reassign it to the right
  speaker in two clicks.
- **Translates to English** — Arabic, Russian, Mandarin, Spanish, Farsi and
  ~95 more, using Whisper's native translation. The original and the English are
  both kept, aligned by timestamp and speaker, so you can read either or both
  side by side. Right-to-left scripts render correctly. Summaries are written
  from the English, and an English search finds an Arabic recording.
- **Summarizes** — overview, key points, action items and questions raised.
- **Timestamps everything** — every turn carries an elapsed timestamp and the
  real wall-clock time it was said, worked out from the recording's date.
- **Searches everything** — full-text search across every transcript you own;
  results link straight to the moment in the recording.
- **Plays along** — click any line to jump the player there; the transcript
  highlights and scrolls itself as it plays.
- **Organises** — folders, tags and free-text notes per recording.
- **Saves audio + PDF + .txt together** — every completed recording keeps all
  three files side by side in the media folder, so a transcript survives with or
  without this app. Download any of them on demand from the Files panel.
  Downloads are **resumable** — a dropped connection on a 2 GB recording picks
  up where it stopped rather than starting over.

## How the pieces fit

```
   Browser  ──►  frontend (nginx)  ──►  backend (FastAPI)  ──►  MongoDB
   :8458                                      │                 (transcripts,
                                              │                  search index)
                                              ▼
                                    /volume1/docker/stealthscribe/media
                                    (your recordings + .txt files)
                                              ▲
                                              │ claims jobs, posts results
                                    Stealth-Scribe worker on your PC
                                    (Whisper + speaker AI, on the GPU)
```

Uploads land on the NAS immediately and sit in a queue. When the worker on your
PC is running it picks them up, transcribes them on the GPU, and posts the text
back. If the PC is off, nothing breaks — jobs simply wait.

## Repository layout

```
backend/     FastAPI service: uploads, library, search, job queue, .txt output
frontend/    React app served by nginx, proxies /api/ to the backend
worker/      The GPU worker that runs on your Windows PC
memory/      Playbooks for whoever works on this next (agent or human)
             (frontend/src/pages holds the public + legal pages Google indexes)
.github/     GitHub Actions workflow that builds both images to GHCR
docker-compose.yml   What you deploy on the NAS
DEPLOYMENT.md        Step-by-step playbook, in the same format as the others
```

> The logo files live in `frontend/public` as base64 text (`*.b64`) and are
> decoded into real images by `scripts/decode-assets.mjs`, which runs
> automatically before `npm run dev` and `npm run build`. That keeps the whole
> repository plain text. To swap the artwork, drop real image files into
> `frontend/public` and delete the matching `.b64`.

## Setting it up

Full instructions are in **[DEPLOYMENT.md](DEPLOYMENT.md)**. The short version:

1. Push this repo to GitHub and wait for the green checkmark in Actions.
2. Make both GHCR packages public.
3. Create the project on the NAS from `docker-compose.yml` — **change
   `WORKER_TOKEN` first**.
4. On your PC, run `worker/setup_worker_windows.bat`, put the same token and
   `http://10.0.0.146:8458` into `stealthscribe-worker.json`, then run
   `run_worker.bat`.
5. Open http://10.0.0.146:8458 and drop in a recording.

## Speaker separation

Two engines, chosen automatically:

- **pyannote 3.1** — properly accurate. Free, but needs a Hugging Face token:
  accept the conditions at
  [pyannote/speaker-diarization-3.1](https://huggingface.co/pyannote/speaker-diarization-3.1),
  create a token at [huggingface.co/settings/tokens](https://huggingface.co/settings/tokens),
  and paste it into `stealthscribe-worker.json`.
- **Built-in** — no token, no download, but approximate. Used automatically when
  no token is set. Fine for two clearly different voices in a clean recording.

## Summaries

The offline summarizer runs on your own hardware and costs nothing: it extracts
the most representative sentences, detects commitments as action items, and
pulls out the questions that were asked. If you'd rather have a written summary
from a language model, set summary mode to `ai` in the app's settings and put an
API key in `stealthscribe-worker.json` — the key stays on your PC.

## Updating

1. Make your changes.
2. Bump `APP_VERSION` in `frontend/src/config/version.js`, add a changelog entry
   there, and update the `<title>` in `frontend/index.html` and `name` in
   `frontend/public/manifest.json`.
3. Push to `main`, wait for the green checkmark in Actions.
4. On the NAS: UGOS Docker → stealthscribe project → **Pull & Redeploy**.

## Port reference

| Site | Port |
|------|------|
| pooperx.com | 8450 |
| warvid.com | 8451 |
| qrcommando.com | 8452 |
| myspacebase.com | 8453 |
| **Stealth-Scribe** | **8458** |
