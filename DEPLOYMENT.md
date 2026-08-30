# Stealth-Scribe NAS Deployment Playbook

**App:** Stealth-Scribe — Audio in. Transcribe to English. Save as PDF.
**Domain:** stealth-scribe.com
**NAS Port:** 8458
**GitHub Repo:** github.com/EVILTIM58/stealth-scribe
**Date Created:** August 16, 2026

---

## Overview

This playbook deploys Stealth-Scribe to the UGREEN NAS using the same pattern as
myspacebase.com:

- Docker containers (frontend + backend + MongoDB)
- GitHub Actions CI/CD pipeline building to GHCR
- LAN access on port 8458 (Cloudflare routing optional, see Step 10)

Two things differ from the other sites:

1. There is a **fourth component** — a transcription worker that runs on your
   Windows PC and does the GPU work. The NAS never transcribes anything itself.
2. The backend has a **bind-mounted media folder** so your recordings and their
   .txt transcripts are normal files on the NAS, not buried in a volume.

---

## Prerequisites

- [ ] GitHub repo `EVILTIM58/stealth-scribe` created (done)
- [ ] UGREEN NAS with Docker installed
- [ ] Windows PC with an NVIDIA GPU for the worker
- [ ] Python 3.11 or 3.12 installed on that PC

---

## Step 1: Push the Code to GitHub

From the folder containing this repo:

```bash
git init
git add .
git commit -m "Stealth-Scribe v1.0.0"
git branch -M main
git remote add origin https://github.com/EVILTIM58/stealth-scribe.git
git push -u origin main
```

The workflow at `.github/workflows/build.yml` is already in place and builds on
every push to `main`.

---

## Step 2: Verify the Build

1. Go to https://github.com/EVILTIM58/stealth-scribe/actions
2. Wait for the green checkmark ✅

### If the build fails:

**Workflow permissions error:**
- GitHub repo → Settings → Actions → General → "Read and write permissions" → Save

**Frontend build fails:**
- The frontend uses Vite with no Babel plugin chain, so the ajv / peer-dependency
  problems from the other sites do not apply here. If it still fails, read the
  error in the Actions log — it will name the missing module.

**Backend build fails:**
- The backend has no private index URLs and no `emergentintegrations`. Every
  dependency in `backend/requirements.txt` comes from public PyPI.

---

## Step 3: Make GHCR Packages Public

1. Go to https://github.com/EVILTIM58?tab=packages
2. Click `stealthscribe-frontend` → Package settings → Change visibility → **Public**
3. Click `stealthscribe-backend` → Package settings → Change visibility → **Public**

---

## Step 4: Create the NAS Folders

Create these folders on the NAS:

```
/volume1/docker/stealthscribe/
/volume1/docker/stealthscribe/media/     <- your recordings and .txt transcripts land here
/volume1/docker/stealthscribe/tmp/       <- in-progress uploads, safe to empty any time
```

---

## Step 5: Pick a Worker Token

The worker on your PC proves who it is with a shared secret. Make up something
long — it never needs to be memorable:

```
stealthscribe-3f9c1a77b204e8d5-timgamingpc
```

You will paste this same value in **two** places: the compose file below, and
`stealthscribe-worker.json` on your PC. They must match exactly.

---

## Step 6: Create the NAS Docker Compose

Create `/volume1/docker/stealthscribe/docker-compose.yml`:

```yaml
name: stealthscribe

services:
  mongo:
    image: mongo:7
    container_name: stealthscribe-mongo
    restart: unless-stopped
    volumes:
      - stealthscribe_mongo:/data/db
    networks: [stealthscribe_net]

  backend:
    image: ghcr.io/eviltim58/stealthscribe-backend:latest
    container_name: stealthscribe-backend
    restart: unless-stopped
    environment:
      MONGO_URL: "mongodb://mongo:27017"
      DB_NAME: "stealthscribe"
      MEDIA_DIR: "/data/media"
      TMP_DIR: "/data/tmp"
      WORKER_TOKEN: "stealthscribe-3f9c1a77b204e8d5-timgamingpc"
      WRITE_TXT_SIDECAR: "1"
      APP_VERSION: "1.0.0"
    volumes:
      - /volume1/docker/stealthscribe/media:/data/media
      - /volume1/docker/stealthscribe/tmp:/data/tmp
    depends_on: [mongo]
    networks: [stealthscribe_net]

  frontend:
    image: ghcr.io/eviltim58/stealthscribe-frontend:latest
    container_name: stealthscribe-frontend
    restart: unless-stopped
    ports:
      - "8458:80"
    depends_on: [backend]
    networks: [stealthscribe_net]

networks:
  stealthscribe_net:
    driver: bridge

volumes:
  stealthscribe_mongo:
```

**Change `WORKER_TOKEN` to the value you picked in Step 5.**

---

## Step 7: Deploy on UGOS

1. UGOS Docker → **Project** → **+ Create Project**
2. Name: `stealthscribe`
3. Path: `/volume1/docker/stealthscribe`
4. Paste the docker-compose.yml content
5. ✅ Tick **"Pull the latest image"**
6. **Deploy**

---

## Step 8: Verify the Deployment

```bash
curl http://10.0.0.146:8458/api/system/version
curl http://10.0.0.146:8458/api/health
```

Expected:

```json
{"name":"Stealth-Scribe","version":"1.0.0"}
{"ok":true}
```

Or just visit http://10.0.0.146:8458 in a browser. The sidebar will say
**"No worker connected"** — that is correct until Step 9.

---

## Step 9: Set Up the Worker on Your PC

This is the part that does the actual transcribing.

1. Copy the `worker` folder from this repo to your PC, somewhere permanent —
   e.g. `C:\StealthScribe\worker`.
2. Double-click **`setup_worker_windows.bat`**. It creates a private Python
   environment and installs PyTorch (CUDA build if it sees your GPU),
   faster-whisper and the speaker models. Allow 10–20 minutes; it downloads
   several GB.
3. When it finishes it opens `stealthscribe-worker.json` in Notepad. Set:

```json
{
  "server_url": "http://10.0.0.146:8458",
  "worker_token": "stealthscribe-3f9c1a77b204e8d5-timgamingpc",
  "worker_name": "timgamingpc",
  "hf_token": ""
}
```

4. Double-click **`run_worker.bat`**. You should see:

```
Server : http://10.0.0.146:8458
Worker : timgamingpc
Device : CUDA (NVIDIA GeForce RTX ...)
Waiting for jobs... (leave this window open)
```

5. Refresh http://10.0.0.146:8458 — the sidebar now shows the worker as online.
6. Optional: run **`install_autostart.bat`** so the worker starts with Windows.

### Speaker separation (recommended, free)

Without a Hugging Face token, Stealth-Scribe uses its approximate built-in speaker
detector. To get the accurate one:

1. Go to https://huggingface.co/pyannote/speaker-diarization-3.1 and accept the
   conditions (free account required).
2. Also accept at https://huggingface.co/pyannote/segmentation-3.0
3. Create a read token at https://huggingface.co/settings/tokens
4. Paste it as `hf_token` in `stealthscribe-worker.json` and restart the worker.

---

## Step 10: Cloudflare Routing (optional, later)

Stealth-Scribe is LAN-only as deployed. If you later want it on a domain:

### First: remove existing DNS records
1. https://dash.cloudflare.com/ → your domain → **DNS** → **Records**
2. Delete any A, AAAA, or CNAME records for the hostname you plan to use

### Then: add the tunnel route
1. https://one.dash.cloudflare.com/ → **Networks** → **Connectors**
2. Click your tunnel (warvid-nas)
3. **"+ Add a published application route"**

| Domain | Path | Service |
|--------|------|---------|
| stealth-scribe.com | * | http://10.0.0.146:8458 |

### IMPORTANT if you do this

Cloudflare's free plan caps request bodies at 100 MB. Stealth-Scribe already uploads in
8 MB chunks specifically so this is not a problem — large recordings will still
work through the tunnel. But note that **anyone who reaches the URL can read
your transcripts**: there is no login in v1. Put Cloudflare Access in front of it
(Zero Trust → Access → Applications → self-hosted, restrict to your email)
before exposing it.

---

## Step 11: Live recording from a phone (needs HTTPS)

Stealth-Scribe can record straight from your phone's microphone — open the site, tap
**Record**, and when you stop it uploads and queues like any other file.

**But browsers refuse microphone access on a plain `http://` address.** This is
a hard browser rule (a "secure context" requirement), not a Stealth-Scribe setting,
and nothing in the app can override it. On `http://10.0.0.146:8458` the Record
button will explain this rather than fail silently. Uploading files recorded
with your phone's own voice-recorder app is unaffected — it works over plain
http today.

Pick one of these:

### Option A — Cloudflare tunnel (best)

Do Step 10, which gives you `https://` for free. Recording then works from
anywhere, not just at home. **Add Cloudflare Access first** — Stealth-Scribe has no
login.

### Option B — trust the origin in Chrome (fastest, 2 minutes)

On the phone or desktop, in Chrome:

1. Open `chrome://flags/#unsafely-treat-insecure-origin-as-secure`
2. Add `http://10.0.0.146:8458` to the text box
3. Set the dropdown to **Enabled**, tap **Relaunch**

Only affects that browser. Safari has no equivalent — iPhones need Option A or C.

### Option C — self-signed certificate on nginx

Generate a cert valid for the NAS IP:

```bash
openssl req -x509 -nodes -newkey rsa:2048 -days 3650 \
  -keyout /volume1/docker/stealthscribe/certs/stealthscribe.key \
  -out /volume1/docker/stealthscribe/certs/stealthscribe.crt \
  -subj "/CN=10.0.0.146" \
  -addext "subjectAltName=IP:10.0.0.146"
```

Mount it into the frontend container and add a TLS server block:

```yaml
  frontend:
    ports:
      - "8458:80"
      - "8459:443"
    volumes:
      - /volume1/docker/stealthscribe/certs:/etc/nginx/certs:ro
```

```nginx
server {
    listen 443 ssl;
    ssl_certificate     /etc/nginx/certs/stealthscribe.crt;
    ssl_certificate_key /etc/nginx/certs/stealthscribe.key;
    # ...same body as the port 80 server block...
}
```

Visit `https://10.0.0.146:8459`, accept the one-time warning, and the origin
counts as secure from then on.

### Recording notes

- **Keep the screen on.** A locked phone suspends the recorder. Stealth-Scribe requests
  a screen wake lock where the browser supports it, but iOS Safari does not.
- Android/Chrome records WebM/Opus; iOS Safari records MP4/AAC. Both are
  transcribed identically — the app tells the server the real media type so an
  audio-only `.webm` isn't mistaken for a video.
- Recording continues if you switch tabs on desktop, but not reliably if you
  background the browser on a phone.

---

## Step 12: Domain, HTTPS and SITE_BASE_URL

Multi-user Stealth-Scribe needs a real domain on HTTPS. Google and Facebook will not
accept an IP address as an OAuth callback, cookies can't be marked `Secure`
without it, and microphone recording won't work either.

**Everything derives from one value: `SITE_BASE_URL` in the compose file.**
OAuth callbacks, email links, the sitemap, and whether the session cookie is
marked `Secure` all read it. Set it once, correctly, with no trailing slash:

```yaml
SITE_BASE_URL: "https://stealth-scribe.com"
```

Then in Cloudflare:

1. Add the domain to your account (**Add a site**), update the nameservers at
   your registrar, wait for it to go active.
2. Zero Trust → **Networks → Connectors** → your `warvid-nas` tunnel →
   **+ Add a published application route**:

| Domain | Path | Service |
|--------|------|---------|
| stealth-scribe.com | * | http://10.0.0.146:8458 |
| www.stealth-scribe.com | * | http://10.0.0.146:8458 |

3. Delete any existing A/AAAA/CNAME records for `@` and `www` first, or the
   route will fail with "record already exists".

---

## Step 13: Google sign-in

1. https://console.cloud.google.com/ → create a project (name it Stealth-Scribe).
2. **APIs & Services → OAuth consent screen**:
   - User type: **External**, then **Publish app** (while in Testing, only
     accounts you list can sign in)
   - App name `Stealth-Scribe`, your support email, your logo
   - **Authorized domains**: `stealth-scribe.com`
   - Links: privacy policy `https://stealth-scribe.com/privacy`, terms
     `https://stealth-scribe.com/terms` — Google checks these exist, which is exactly
     why the legal pages are part of this release
   - Scopes: `openid`, `email`, `profile` — nothing more
3. **Credentials → Create credentials → OAuth client ID → Web application**:
   - Authorized JavaScript origins: `https://stealth-scribe.com`
   - **Authorized redirect URI**: `https://stealth-scribe.com/api/auth/google/callback`
     — this must match *character for character*, including scheme and no
     trailing slash
4. Put the client ID and secret into the compose file:

```yaml
GOOGLE_CLIENT_ID: "1234567890-abcdef.apps.googleusercontent.com"
GOOGLE_CLIENT_SECRET: "GOCSPX-..."
```

Leave both blank and the Google button simply doesn't appear.

---

## Step 14: Facebook sign-in

1. https://developers.facebook.com/apps/ → **Create App** → type **Consumer**.
2. Add the **Facebook Login** product → **Settings**:
   - **Valid OAuth Redirect URIs**: `https://stealth-scribe.com/api/auth/facebook/callback`
   - Client OAuth login: **On**. Web OAuth login: **On**.
3. **App settings → Basic**: add Privacy Policy URL `https://stealth-scribe.com/privacy`,
   Terms `https://stealth-scribe.com/terms`, and a category. Facebook requires these
   before the app can leave Development mode.
4. Switch the app to **Live** (top toggle) or only you can sign in.
5. Copy App ID and App Secret into the compose file:

```yaml
FACEBOOK_APP_ID: "123456789012345"
FACEBOOK_APP_SECRET: "abc123..."
```

**Note:** Facebook accounts registered with only a phone number have no email
address to share. Stealth-Scribe tells those users to sign up with email instead —
there's nothing to fix, it's a Facebook limitation.

---

## Step 15: Email with Resend

Confirmation and password-reset mail. Without it, signups can't complete —
the link is printed to the backend container log instead, which works for you
but not for anyone else.

1. https://resend.com → sign up (free tier: 3,000 emails/month).
2. **Domains → Add Domain** → `stealth-scribe.com`. Resend gives you DKIM/SPF records;
   add them in Cloudflare DNS. **Set those records to DNS-only (grey cloud),
   not proxied.** Wait for Verified.
3. **API Keys → Create** with *Sending access*. Copy it — it's shown once.
4. Into the compose file:

```yaml
RESEND_API_KEY: "re_..."
MAIL_FROM: "Stealth-Scribe <noreply@stealth-scribe.com>"
```

Then set up **Cloudflare Email Routing** so the addresses on your legal pages
actually receive mail: Cloudflare zone → **Email → Email Routing → Get started**,
verify your personal Gmail as a destination, let it add the MX records, then
forward `contact@`, `legal@` and `dmca@` to your Gmail. Five minutes, and it's
required for DMCA safe harbour and any future AdSense review.

---

## Step 16: Roles and the owner account

| Role | Can do |
|------|--------|
| **GOD** | Everything. Hardcoded to `eviltim@gmail.com`. |
| **ADMIN** | Everything except changing roles and deleting accounts. Sees all recordings. |
| **USER** | Everything except the admin panel. Sees only their own recordings. |

- **GOD is decided by email address on every single request**, never read from
  a stored field. Nobody can promote themselves by editing the database, and
  the owner account cannot be suspended, demoted or deleted through the UI.
- **Only GOD can promote a USER to ADMIN, and only GOD can demote an ADMIN back
  to USER.** An admin calling that endpoint gets a 403 from the dependency
  itself, not from a UI check.
- An admin cannot suspend or modify another admin. Only GOD can.

**First run:** sign up at `https://stealth-scribe.com/signup` with `eviltim@gmail.com`
(or sign in with that Google account). You are GOD automatically. Any recordings
that existed before multi-user are assigned to you on the next backend restart.

To move the owner account to a different address, change `GOD_EMAIL` in the
compose file and redeploy.

### About open signup

`ALLOW_SIGNUP: "1"` means anyone on the internet can register. Since
transcription runs on **your** GPU, standard users are capped at
`DAILY_MINUTES_QUOTA` minutes of audio per rolling 24 hours (default 180).
Admins and GOD are never capped. Set it to `0` to remove the cap, or set
`ALLOW_SIGNUP: "0"` to close registration entirely if it gets abused.

---

## Step 17: Languages and translation

Stealth-Scribe transcribes ~99 languages and translates any of them **into English**.
This is Whisper's own translation task — the same model, one decoder flag, no
separate translation service and no API key.

### How it behaves

| Setting | What happens |
|---------|--------------|
| `auto` (default) | Anything not detected as English is transcribed **and** translated. English audio is left alone. |
| `always` | Every recording gets a translation pass, even English. |
| `off` | Original language only. |

Both versions are stored and aligned to the same timestamps and the same
speaker labels, so the transcript view offers **English / Original / Both**, and
the `.txt` contains the English first with the original beneath it.

### Things worth knowing

- **Only into English.** Whisper cannot translate English into Arabic, or
  Arabic into French. Every path leads to English. Adding other target
  languages would mean a separate translation model.
- **It roughly doubles processing time**, because it is a second decode of the
  same audio. A 1-hour Arabic recording that transcribes in 3 minutes takes
  about 6 with translation.
- **Use `large-v3` for non-English audio.** The accuracy gap between `medium`
  and `large-v3` is small for English and large for Arabic, Hindi and Chinese.
  If you mostly work with Arabic, set the model to large-v3 and accept the
  slower run. It needs ~10 GB of VRAM.
- **Right-to-left scripts render correctly** — Arabic, Hebrew, Farsi, Urdu and
  Pashto are marked RTL and displayed accordingly. Left-to-right Arabic is
  unreadable, so this matters.
- **Summaries are written from the English** when a translation exists. A
  summary you cannot read is worthless.
- **English search finds foreign recordings.** The translation is indexed
  alongside the original, so searching "inventory" surfaces the Arabic call
  where that word was only ever spoken in Arabic.
- **It is machine translation.** Good enough to know what was said and decide
  whether it matters; not good enough to sign. The .txt says so explicitly, and
  the original is always kept next to it so anything important can be checked.

### Tuning

Nothing to configure for translation itself — it is per-user in Settings.
Voice recognition thresholds live in the compose file (`VOICEID_AUTO`,
`VOICEID_SUGGEST`) if names are being applied too eagerly or not eagerly enough.

---

## Updating the App

1. Make changes in the codebase
2. **Update version number** in:
   - `frontend/src/config/version.js` (APP_VERSION)
   - `frontend/public/manifest.json` (name field)
   - `frontend/index.html` (title tag)
3. **Update changelog** in `frontend/src/config/version.js` (VERSION_HISTORY)
4. Push to GitHub
5. Wait for the green checkmark in GitHub Actions
6. On NAS: UGOS Docker → stealthscribe project → **Pull & Redeploy**

The worker only needs re-copying if you changed something in `worker/`.

---

## Where Your Data Lives

| What | Where |
|------|-------|
| Recordings and video | `/volume1/docker/stealthscribe/media/YYYY/MM/` |
| Plain .txt transcripts | next to each media file, same name |
| Transcripts, summaries, speakers, tags, notes | MongoDB volume `stealthscribe_mongo` |
| In-progress uploads | `/volume1/docker/stealthscribe/tmp/` (safe to empty) |

Back up `/volume1/docker/stealthscribe/media` and you have every recording plus a
readable transcript of each, independent of this app or the database.

---

## Troubleshooting

### Sidebar says "No worker connected"
- Is `run_worker.bat` running on the PC, window still open?
- Does `worker_token` in `stealthscribe-worker.json` exactly match `WORKER_TOKEN` in the
  compose file? A mismatch prints "Server rejected the worker token".
- Can the PC reach the NAS? `curl http://10.0.0.146:8458/api/health` from the PC.

### Uploads stay "Queued" forever
- That means the queue is working and no worker is claiming jobs. See above.
- Jobs are safe — they will process as soon as the worker connects.

### A job says "failed"
- The error is shown on the recording. The worker window has the full traceback.
- Most common: a corrupt file, or a video with no audio track.
- Fix the cause and press **Re-transcribe** on that recording.

### Transcription is very slow
- Check the worker window says `Device : CUDA`. If it says CPU, the CUDA build of
  PyTorch did not install — re-run `setup_worker_windows.bat`.
- Lower the model in the app's settings (medium → small) for a big speedup.

### Speaker labels are wrong or everything is one voice
- Without a Hugging Face token you are on the approximate detector. Add the token
  (Step 9) for a large accuracy jump.
- If you know how many people are talking, set it explicitly in settings — it
  helps a lot.
- Then press **Re-transcribe** on the recording.

### Container won't start on the NAS
- Check container logs in UGOS Docker
- Verify the images pulled successfully and are public (Step 3)
- Check port 8458 is not already in use

### Site loads but the API fails
- Verify the backend container is running and healthy
- `nginx.conf` proxies `/api/` to `http://backend:8001/api/` — the service name
  must stay `backend`
- Verify the MongoDB container is healthy

---

## Files Checklist

- [x] `.github/workflows/build.yml`
- [x] `frontend/Dockerfile`
- [x] `frontend/nginx.conf`
- [x] `backend/Dockerfile`
- [x] `docker-compose.yml`
- [x] `worker/setup_worker_windows.bat`

---

## Post-Deployment

- [ ] Upload one short recording and confirm the .txt appears in
      `/volume1/docker/stealthscribe/media/2026/08/`
- [ ] Rename the speakers on it and confirm the .txt updates
- [ ] Add `/volume1/docker/stealthscribe/media` to your NAS backup job
- [ ] Run `install_autostart.bat` on the PC so the worker is always available
- [ ] Decide whether you want Cloudflare + Access (Step 10) or LAN-only
