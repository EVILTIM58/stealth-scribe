"""Environment configuration for the Stealth-Scribe backend."""

from __future__ import annotations

import os

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "stealthscribe")

# ---------------------------------------------------------------- identity
# Canonical public URL. Every OAuth callback, email link, sitemap entry and
# cookie-security decision derives from this one value -- set it correctly or
# social sign-in will fail with a redirect_uri mismatch.
SITE_BASE_URL = os.environ.get("SITE_BASE_URL", "http://localhost:8458").rstrip("/")
SITE_NAME = os.environ.get("SITE_NAME", "Stealth-Scribe")

# The one hardcoded owner account. Matched on every request, never stored as a
# grantable field, so nobody can promote themselves by editing the database.
GOD_EMAIL = os.environ.get("GOD_EMAIL", "eviltim@gmail.com")

# Mixed into session-token hashes. Change it and every session is invalidated.
TOKEN_PEPPER = os.environ.get("TOKEN_PEPPER", "stealthscribe-token-pepper-v1")

# ------------------------------------------------------------------- OAuth
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.environ.get("GOOGLE_CLIENT_SECRET", "")
FACEBOOK_APP_ID = os.environ.get("FACEBOOK_APP_ID", "")
FACEBOOK_APP_SECRET = os.environ.get("FACEBOOK_APP_SECRET", "")

# -------------------------------------------------------------------- mail
RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
MAIL_FROM = os.environ.get("MAIL_FROM", "Stealth-Scribe <noreply@stealth-scribe.com>")
CONTACT_EMAIL = os.environ.get("CONTACT_EMAIL", "contact@stealth-scribe.com")
LEGAL_EMAIL = os.environ.get("LEGAL_EMAIL", "legal@stealth-scribe.com")
DMCA_EMAIL = os.environ.get("DMCA_EMAIL", "dmca@stealth-scribe.com")
JURISDICTION = os.environ.get("JURISDICTION", "the State of Texas, United States")

# ---------------------------------------------------------------- accounts
ALLOW_SIGNUP = os.environ.get("ALLOW_SIGNUP", "1") not in ("0", "false", "False")

# Transcription runs on hardware you own and pay for. This caps how many minutes
# of audio a standard user can queue per rolling 24h. 0 disables the cap.
# Admins and GOD are never limited.
DAILY_MINUTES_QUOTA = int(os.environ.get("DAILY_MINUTES_QUOTA", "180"))
MAX_RECORDINGS_PER_USER = int(os.environ.get("MAX_RECORDINGS_PER_USER", "0"))

# Where audio lives on the NAS (bind-mounted in docker-compose).
MEDIA_DIR = os.environ.get("MEDIA_DIR", "/data/media")
TMP_DIR = os.environ.get("TMP_DIR", "/data/tmp")

# Shared secret the GPU worker uses to claim jobs.
WORKER_TOKEN = os.environ.get("WORKER_TOKEN", "change-me")

# Job is handed back to the queue if a worker goes quiet for this long.
JOB_LEASE_SECONDS = int(os.environ.get("JOB_LEASE_SECONDS", "900"))

# Also drop a plain .txt next to each audio file.
WRITE_TXT_SIDECAR = os.environ.get("WRITE_TXT_SIDECAR", "1") not in ("0", "false", "False")
# Also write a .pdf beside the audio, so audio + text + PDF live together.
WRITE_PDF_SIDECAR = os.environ.get("WRITE_PDF_SIDECAR", "1") not in ("0", "false", "False")

MAX_UPLOAD_BYTES = int(os.environ.get("MAX_UPLOAD_BYTES", str(4 * 1024 * 1024 * 1024)))

APP_VERSION = os.environ.get("APP_VERSION", "1.0.2")

AUDIO_EXTENSIONS = {
    ".mp3", ".wav", ".m4a", ".wma", ".ogg", ".oga", ".flac", ".aac", ".m4b",
    ".opus", ".amr", ".aiff", ".aif", ".3gp", ".mp2", ".ac3", ".caf", ".dss",
    ".dvf", ".msv", ".wv",
}

# Video files are handled exactly the same way -- the audio track is pulled out
# for transcription, and the video itself stays playable in the browser.
VIDEO_EXTENSIONS = {
    ".mp4", ".mov", ".mkv", ".avi", ".wmv", ".webm", ".m4v", ".flv", ".mpg",
    ".mpeg", ".mts", ".m2ts", ".ts", ".vob", ".ogv", ".asf", ".rm", ".3g2",
}

ALLOWED_EXTENSIONS = AUDIO_EXTENSIONS | VIDEO_EXTENSIONS
