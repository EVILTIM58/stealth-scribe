"""Stealth-Scribe -- FastAPI backend.

Serves the recording library, accepts uploads, and hands transcription jobs to
GPU workers. All routes live under /api (nginx proxies /api/ to this service).
"""

from __future__ import annotations

import asyncio
import datetime as dt
import os
import re
import uuid
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import (FileResponse, JSONResponse, PlainTextResponse,
                               StreamingResponse)

import api_admin
import api_auth
import api_people
import api_site
import auth
import db
import languages
import models
import pdfout
import settings
import storage
import textout
import voiceid

app = FastAPI(title="Stealth-Scribe", version=settings.APP_VERSION)

# Credentials ride in a cookie, so a wildcard origin is not allowed by the spec
# and would be a CSRF hole anyway. Same-origin in production (nginx proxies
# /api/), plus the Vite dev server.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.SITE_BASE_URL, "http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

MIME_BY_EXT = {
    # audio
    ".mp3": "audio/mpeg", ".wav": "audio/wav", ".m4a": "audio/mp4",
    ".m4b": "audio/mp4", ".ogg": "audio/ogg", ".oga": "audio/ogg",
    ".opus": "audio/ogg", ".flac": "audio/flac", ".aac": "audio/aac",
    ".wma": "audio/x-ms-wma", ".amr": "audio/amr", ".aiff": "audio/aiff",
    ".aif": "audio/aiff", ".3gp": "audio/3gpp", ".mp2": "audio/mpeg",
    ".ac3": "audio/ac3", ".caf": "audio/x-caf", ".wv": "audio/wavpack",
    # video -- transcribed identically, the audio track is extracted
    ".mp4": "video/mp4", ".m4v": "video/mp4", ".mov": "video/quicktime",
    ".mkv": "video/x-matroska", ".webm": "video/webm", ".avi": "video/x-msvideo",
    ".wmv": "video/x-ms-wmv", ".flv": "video/x-flv", ".mpg": "video/mpeg",
    ".mpeg": "video/mpeg", ".ts": "video/mp2t", ".mts": "video/mp2t",
    ".m2ts": "video/mp2t", ".vob": "video/mpeg", ".ogv": "video/ogg",
    ".asf": "video/x-ms-asf", ".3g2": "video/3gpp2",
}


def _kind_for(ext: str) -> str:
    return "video" if ext.lower() in settings.VIDEO_EXTENSIONS else "audio"


def _resolve_media_type(ext: str, declared_mime: str = "") -> tuple:
    """Return (mime, kind).

    A browser-recorded voice memo is audio inside a .webm or .mp4 container, so
    the extension alone would wrongly call it video. When the client declares a
    mime type, trust it; otherwise fall back to the extension table.
    """
    ext = (ext or "").lower()
    declared = (declared_mime or "").split(";")[0].strip().lower()
    if declared.startswith("audio/"):
        return declared, "audio"
    if declared.startswith("video/"):
        return declared, "video"
    return MIME_BY_EXT.get(ext, "application/octet-stream"), _kind_for(ext)


# ---------------------------------------------------------------- lifecycle
@app.on_event("startup")
async def _startup() -> None:
    _log_configuration()
    storage.ensure_dirs()
    await db.ensure_indexes()
    await db.get_settings()
    await _requeue_stale()
    await _backfill()
    storage.sweep_stale_chunks()
    asyncio.create_task(_janitor())


def _log_configuration() -> None:
    """Print exactly what is and isn't configured, at boot.

    Sign-in buttons are hidden when a provider has no credentials, which is
    correct for users but invisible to the operator -- it just looks like the
    feature wasn't built. This makes the state obvious in `docker logs`, and
    prints the callback URLs so they can be pasted into the provider consoles
    (a redirect_uri that differs by one character is the single most common
    OAuth failure).
    """
    import oauth

    L = lambda msg: print(f"[config] {msg}", flush=True)  # noqa: E731
    base = settings.SITE_BASE_URL
    providers = oauth.enabled()

    L(f"Stealth-Scribe {settings.APP_VERSION}")
    L(f"SITE_BASE_URL   : {base}")
    L(f"Owner (GOD)     : {settings.GOD_EMAIL}")
    L(f"Signups         : {'OPEN' if settings.ALLOW_SIGNUP else 'CLOSED'}"
      + (f", {settings.DAILY_MINUTES_QUOTA} min/day per user"
         if settings.DAILY_MINUTES_QUOTA > 0 else ", no quota"))

    for name, on, env in (
        ("Google sign-in  ", providers["google"], "GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET"),
        ("Facebook sign-in", providers["facebook"], "FACEBOOK_APP_ID / FACEBOOK_APP_SECRET"),
    ):
        if on:
            L(f"{name}: ENABLED")
            L(f"{' ' * 16}  callback -> {oauth.redirect_uri(name.split()[0].lower())}")
            L(f"{' ' * 16}  (must match the provider console character for character)")
        else:
            L(f"{name}: off -- set {env} to show the button")

    if settings.RESEND_API_KEY:
        L(f"Email (Resend)  : ENABLED, from {settings.MAIL_FROM}")
    else:
        L("Email (Resend)  : off -- confirmation links will be PRINTED HERE, "
          "not emailed. Nobody but you can complete a signup.")

    # Warnings worth shouting about.
    if not base.startswith("https://"):
        L("WARNING: SITE_BASE_URL is not https. Google and Facebook will refuse "
          "the callback, session cookies won't be marked Secure, and browsers "
          "will block microphone recording.")
    if "localhost" in base and (providers["google"] or providers["facebook"]):
        L("WARNING: SITE_BASE_URL still points at localhost while OAuth is "
          "configured -- sign-in will redirect users to the wrong host.")
    if settings.TOKEN_PEPPER == "stealthscribe-token-pepper-v1":
        L("WARNING: TOKEN_PEPPER is still the default. Change it.")
    if settings.WORKER_TOKEN == "change-me":
        L("WARNING: WORKER_TOKEN is still the default. Change it, and match it "
          "in the worker's stealthscribe-worker.json.")
    for a, b, label in (
        (settings.GOOGLE_CLIENT_ID, settings.GOOGLE_CLIENT_SECRET, "Google"),
        (settings.FACEBOOK_APP_ID, settings.FACEBOOK_APP_SECRET, "Facebook"),
    ):
        if bool(a) != bool(b):
            L(f"WARNING: {label} is half-configured -- one of the ID/secret pair "
              f"is missing, so the button stays hidden.")


async def _janitor() -> None:
    """Hourly: bin abandoned upload chunks and rescue jobs from dead workers."""
    while True:
        await asyncio.sleep(3600)
        try:
            removed = storage.sweep_stale_chunks()
            if removed:
                print(f"[janitor] removed {removed} abandoned upload folder(s)", flush=True)
            await _requeue_stale()
        except Exception as exc:  # never let the janitor kill itself
            print(f"[janitor] error: {exc}", flush=True)


async def _backfill() -> None:
    """Idempotent migrations, safe to re-run on every boot."""
    coll = db.recordings()
    await coll.update_many({"tags": {"$exists": False}}, {"$set": {"tags": []}})
    await coll.update_many({"notes": {"$exists": False}}, {"$set": {"notes": ""}})
    await coll.update_many({"folder": {"$exists": False}}, {"$set": {"folder": ""}})
    await coll.update_many(
        {"speaker_labels": {"$exists": False}}, {"$set": {"speaker_labels": {}}}
    )
    # Records created before video support have no "kind" -- derive it.
    async for row in coll.find({"kind": {"$exists": False}}, {"media_path": 1}):
        ext = os.path.splitext(row.get("media_path") or "")[1]
        await coll.update_one({"_id": row["_id"]}, {"$set": {"kind": _kind_for(ext)}})

    # Recordings that predate multi-user have no owner. Hand them to the owner
    # account once it exists, so they don't sit visible only to admins.
    god = await db.users().find_one({"email": settings.GOD_EMAIL.strip().lower()})
    if god:
        await coll.update_many(
            {"$or": [{"owner_id": {"$exists": False}}, {"owner_id": None}]},
            {"$set": {"owner_id": god["_id"], "owner_email": god["email"]}},
        )
        # The hardcoded owner is GOD on every login regardless, but keep the
        # stored field honest so the admin list reads correctly.
        if god.get("role") != auth.ROLE_GOD:
            await db.users().update_one({"_id": god["_id"]},
                                        {"$set": {"role": auth.ROLE_GOD}})


async def _requeue_stale() -> None:
    cutoff = _now() - dt.timedelta(seconds=settings.JOB_LEASE_SECONDS)
    await db.recordings().update_many(
        {"status": "processing", "lease_at": {"$lt": cutoff}},
        {"$set": {"status": "queued", "stage": "requeued after worker timeout",
                  "progress": 0.0}},
    )


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


# ------------------------------------------------------------------ helpers
def _jsonable(doc: dict, include_segments: bool = True) -> dict:
    out: Dict[str, Any] = {}
    for k, v in doc.items():
        if k == "segments" and not include_segments:
            continue
        # Raw voiceprints are biometric data and hundreds of floats each.
        # The UI never needs them; only the match summary.
        if k == "speaker_embeddings":
            continue
        if isinstance(v, dt.datetime):
            out[k] = v.isoformat()
        else:
            out[k] = v
    out["id"] = out.pop("_id", None)
    if not include_segments:
        out.pop("text", None)
    return out


def _parse_dt(value: Optional[str]) -> Optional[dt.datetime]:
    if not value:
        return None
    try:
        return dt.datetime.fromisoformat(str(value).replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def _guess_recorded_at(filename: str) -> Optional[dt.datetime]:
    """Voice recorders usually stamp the filename. Fall back to now."""
    patterns = [
        (r"(20\d{2})[-_]?(\d{2})[-_]?(\d{2})[-_ Tt]+(\d{2})[-_:]?(\d{2})[-_:]?(\d{2})", 6),
        (r"(20\d{2})[-_]?(\d{2})[-_]?(\d{2})[-_ Tt]+(\d{2})[-_:]?(\d{2})", 5),
        (r"(20\d{2})[-_]?(\d{2})[-_]?(\d{2})", 3),
    ]
    for pat, count in patterns:
        m = re.search(pat, filename)
        if m:
            try:
                parts = [int(g) for g in m.groups()[:count]]
                while len(parts) < 6:
                    parts.append(0)
                return dt.datetime(*parts)
            except ValueError:
                continue
    return None


def _default_labels(speakers: List[str]) -> Dict[str, str]:
    return {raw: f"Voice {i + 1}" for i, raw in enumerate(speakers)}


def _check_worker(token: Optional[str]) -> None:
    if not token or token != settings.WORKER_TOKEN:
        raise HTTPException(status_code=401, detail="Bad worker token")


# ------------------------------------------------------------------- system
@app.get("/api/system/version")
async def version() -> dict:
    return {"name": "Stealth-Scribe", "version": settings.APP_VERSION}


@app.get("/api/system/languages")
async def language_list() -> dict:
    """Common languages for the settings dropdown. Whisper handles ~99; these
    are the ones worth naming, and the ones flagged rtl need right-to-left
    rendering or the transcript is unreadable."""
    return {"languages": languages.as_list()}

@app.get("/api/health")
async def health() -> dict:
    try:
        await db.get_db().command("ping")
        return {"ok": True}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"database unavailable: {exc}")


@app.get("/api/stats")
async def stats(user: dict = Depends(auth.current_user)) -> dict:
    coll = db.recordings()
    scope = auth.owner_filter(user)
    by_status: Dict[str, int] = {}
    async for row in coll.aggregate(
        [{"$match": scope}, {"$group": {"_id": "$status", "n": {"$sum": 1}}}]
    ):
        by_status[row["_id"] or "unknown"] = row["n"]

    agg = await coll.aggregate(
        [{"$match": scope},
         {"$group": {"_id": None, "dur": {"$sum": "$duration_sec"},
                     "words": {"$sum": "$word_count"}, "bytes": {"$sum": "$size_bytes"}}}]
    ).to_list(1)
    totals = agg[0] if agg else {}

    cutoff = _now() - dt.timedelta(seconds=90)
    online = await db.workers().find({"last_seen": {"$gte": cutoff}}).to_list(20)

    return {
        "by_status": by_status,
        "total": sum(by_status.values()),
        "duration_sec": float(totals.get("dur") or 0),
        "word_count": int(totals.get("words") or 0),
        "bytes": int(totals.get("bytes") or 0),
        "disk": storage.disk_usage() if auth.can_see_everything(user) else {},
        "quota": await _quota_status(user),
        "workers": [
            {"name": w["_id"], "device": w.get("device"),
             "last_seen": w["last_seen"].isoformat(),
             "current": w.get("current") if auth.can_see_everything(user) else None}
            for w in online
        ],
    }


# Transcription preferences are per-user: one person choosing large-v3 must not
# change what everyone else's uploads run with.
async def _user_prefs(user: dict) -> dict:
    merged = dict(db.DEFAULT_SETTINGS)
    merged.pop("_id", None)
    merged.update({k: v for k, v in (user.get("prefs") or {}).items() if v is not None})
    return merged


@app.get("/api/settings")
async def read_settings(user: dict = Depends(auth.current_user)) -> dict:
    return await _user_prefs(user)


@app.patch("/api/settings")
async def patch_settings(
    patch: models.SettingsPatch, user: dict = Depends(auth.current_user)
) -> dict:
    update = {f"prefs.{k}": v for k, v in patch.model_dump().items() if v is not None}
    if update:
        await db.users().update_one({"_id": user["_id"]}, {"$set": update})
    fresh = await db.users().find_one({"_id": user["_id"]})
    return await _user_prefs(fresh or user)


@app.get("/api/folders")
async def folders(user: dict = Depends(auth.current_user)) -> dict:
    coll = db.recordings()
    scope = auth.owner_filter(user)
    folder_rows = await coll.aggregate(
        [{"$match": scope}, {"$group": {"_id": "$folder", "n": {"$sum": 1}}},
         {"$sort": {"_id": 1}}]
    ).to_list(500)
    tag_rows = await coll.aggregate(
        [{"$match": scope}, {"$unwind": "$tags"},
         {"$group": {"_id": "$tags", "n": {"$sum": 1}}}, {"$sort": {"n": -1}}]
    ).to_list(500)
    return {
        "folders": [{"name": r["_id"] or "", "count": r["n"]} for r in folder_rows],
        "tags": [{"name": r["_id"], "count": r["n"]} for r in tag_rows],
    }


# -------------------------------------------------------------------- quota
async def _quota_status(user: dict) -> dict:
    """Signup is open, and transcription burns time on hardware you own. This
    caps a standard user's rolling 24h minutes. Admins and GOD are exempt."""
    limit = settings.DAILY_MINUTES_QUOTA
    if limit <= 0 or auth.can_see_everything(user):
        return {"limited": False, "used_minutes": 0, "limit_minutes": 0}

    since = _now() - dt.timedelta(hours=24)
    agg = await db.recordings().aggregate([
        {"$match": {"owner_id": user["_id"], "created_at": {"$gte": since}}},
        {"$group": {"_id": None, "dur": {"$sum": "$duration_sec"},
                    "bytes": {"$sum": "$size_bytes"}}},
    ]).to_list(1)
    row = agg[0] if agg else {}
    # Duration is only known after transcription, so bill unprocessed uploads at
    # a rough 1 MB/minute. Otherwise the quota is trivially bypassed by uploading
    # everything at once before anything finishes.
    used = float(row.get("dur") or 0) / 60.0
    if not used:
        used = float(row.get("bytes") or 0) / (1024 * 1024)
    return {
        "limited": True,
        "used_minutes": round(used, 1),
        "limit_minutes": limit,
        "remaining_minutes": round(max(0.0, limit - used), 1),
    }


async def _enforce_quota(user: dict) -> None:
    status = await _quota_status(user)
    if status["limited"] and status["used_minutes"] >= status["limit_minutes"]:
        raise HTTPException(
            429,
            f"You've reached the daily limit of {status['limit_minutes']} minutes of "
            f"audio. It resets on a rolling 24-hour basis.",
        )
    if settings.MAX_RECORDINGS_PER_USER > 0 and not auth.can_see_everything(user):
        count = await db.recordings().count_documents({"owner_id": user["_id"]})
        if count >= settings.MAX_RECORDINGS_PER_USER:
            raise HTTPException(
                429, f"You've reached the limit of {settings.MAX_RECORDINGS_PER_USER} recordings."
            )


# ------------------------------------------------------------------ uploads
@app.post("/api/uploads/init")
async def upload_init(
    payload: models.UploadInit, user: dict = Depends(auth.current_user)
) -> dict:
    ext = os.path.splitext(payload.filename)[1].lower()
    if ext not in settings.ALLOWED_EXTENSIONS:
        raise HTTPException(400, f"Unsupported file type '{ext}'.")
    if payload.size and payload.size > settings.MAX_UPLOAD_BYTES:
        raise HTTPException(413, "File is larger than the configured limit.")
    await _enforce_quota(user)

    upload_id = uuid.uuid4().hex
    await db.uploads().insert_one(
        {
            "_id": upload_id,
            "owner_id": user["_id"],
            "filename": payload.filename,
            "mime": payload.mime or "",
            "size": int(payload.size or 0),
            "total_chunks": max(1, int(payload.total_chunks or 1)),
            "received": [],
            "created_at": _now(),
        }
    )
    storage.chunk_dir(upload_id)
    return {"upload_id": upload_id, "chunk_size": 8 * 1024 * 1024}


@app.put("/api/uploads/{upload_id}/chunk")
async def upload_chunk(
    upload_id: str,
    request: Request,
    index: int = Query(0, ge=0),
    user: dict = Depends(auth.current_user),
) -> dict:
    # upload_id lands in a filesystem path -- validate before it touches disk.
    if not storage.valid_upload_id(upload_id):
        raise HTTPException(400, "Invalid upload_id")
    # Scope by owner as well as id: knowing someone else's upload_id must not
    # let you write into their session.
    doc = await db.uploads().find_one({"_id": upload_id, "owner_id": user["_id"]})
    if not doc:
        raise HTTPException(404, "Upload session not found or expired.")
    if index >= int(doc.get("total_chunks") or 1):
        raise HTTPException(400, "Chunk index out of range")

    path = storage.chunk_path(upload_id, index)
    total = 0
    with open(path, "wb") as f:
        async for chunk in request.stream():
            f.write(chunk)
            total += len(chunk)

    await db.uploads().update_one({"_id": upload_id}, {"$addToSet": {"received": index}})
    return {"ok": True, "index": index, "bytes": total}


@app.post("/api/uploads/{upload_id}/complete")
async def upload_complete(
    upload_id: str, payload: models.UploadComplete, user: dict = Depends(auth.current_user)
) -> dict:
    if not storage.valid_upload_id(upload_id):
        raise HTTPException(400, "Invalid upload_id")
    doc = await db.uploads().find_one({"_id": upload_id, "owner_id": user["_id"]})
    if not doc:
        raise HTTPException(404, "Upload session not found or expired.")

    total_chunks = int(doc.get("total_chunks") or 1)
    missing = sorted(set(range(total_chunks)) - set(doc.get("received") or []))
    if missing:
        raise HTTPException(400, f"Upload incomplete, missing chunks: {missing[:10]}")

    rec_id = uuid.uuid4().hex
    original_name = doc["filename"]
    rel = storage.allocate_media_path(original_name, rec_id)
    try:
        size = storage.assemble(upload_id, total_chunks, storage.media_path(rel))
    except FileNotFoundError as exc:
        raise HTTPException(400, str(exc))

    # Enforce the size cap on the REASSEMBLED file. Checking the client-declared
    # size at init only is meaningless -- 500 chunks of 8 MB still fills the disk.
    if size > settings.MAX_UPLOAD_BYTES:
        storage.delete_media(rel)
        await db.uploads().delete_one({"_id": upload_id})
        raise HTTPException(
            413,
            f"File is {size / 1e9:.1f} GB, over the "
            f"{settings.MAX_UPLOAD_BYTES / 1e9:.1f} GB limit.",
        )

    await db.uploads().delete_one({"_id": upload_id})

    mime, kind = _resolve_media_type(os.path.splitext(rel)[1], doc.get("mime", ""))

    defaults = await _user_prefs(user)
    recorded_at = (
        _parse_dt(payload.recorded_at)
        or _guess_recorded_at(original_name)
        or _now()
    )

    record = {
        "_id": rec_id,
        "owner_id": user["_id"],
        "owner_email": user.get("email", ""),
        "title": (payload.title or os.path.splitext(original_name)[0]).strip(),
        "original_name": original_name,
        "media_path": rel,
        "size_bytes": size,
        "mime": mime,
        "kind": kind,
        "folder": (payload.folder or "").strip(),
        "tags": [t.strip() for t in (payload.tags or []) if t.strip()],
        "notes": payload.notes or "",
        "recorded_at": recorded_at,
        "created_at": _now(),
        "updated_at": _now(),
        "status": "queued",
        "progress": 0.0,
        "stage": "waiting for a worker",
        "error": "",
        "duration_sec": 0.0,
        "word_count": 0,
        "language": "",
        "language_probability": 0.0,
        "segments": [],
        "speaker_labels": {},
        "summary": {},
        "text": "",
        "engine": {},
        "show_timestamps": bool(defaults.get("show_timestamps", True)),
        "options": {
            "model_size": defaults.get("model_size", "medium"),
            "language": defaults.get("language", "auto"),
            "speaker_mode": defaults.get("speaker_mode", "auto"),
            "num_speakers": int(defaults.get("num_speakers") or 0),
            "summary_mode": defaults.get("summary_mode", "offline"),
            "translate": defaults.get("translate", "auto"),
        },
    }
    await db.recordings().insert_one(record)
    return _jsonable(record, include_segments=False)


# --------------------------------------------------------------- recordings
def _scoped(rec_id: str, user: dict) -> Dict[str, Any]:
    """Every single-recording lookup goes through this. A standard user simply
    cannot address a recording they don't own -- they get 404, not 403, so the
    existence of other people's recordings isn't leaked either."""
    return {"_id": rec_id, **auth.owner_filter(user)}


@app.get("/api/recordings")
async def list_recordings(
    q: str = Query("", description="full-text search"),
    folder: Optional[str] = None,
    tag: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = Query(60, le=300),
    skip: int = 0,
    user: dict = Depends(auth.current_user),
) -> dict:
    query: Dict[str, Any] = dict(auth.owner_filter(user))
    if folder is not None:
        query["folder"] = folder
    if tag:
        query["tags"] = tag
    if status:
        query["status"] = status

    projection = {"segments": 0, "text": 0}
    sort: List[tuple] = [("created_at", -1)]

    if q.strip():
        query["$text"] = {"$search": q.strip()}
        projection["score"] = {"$meta": "textScore"}
        sort = [("score", {"$meta": "textScore"})]

    cursor = db.recordings().find(query, projection).sort(sort).skip(skip).limit(limit)
    docs = await cursor.to_list(limit)
    total = await db.recordings().count_documents(query)

    items = [_jsonable(d, include_segments=False) for d in docs]

    # For search, attach the matching lines so the UI can jump to them.
    if q.strip() and items:
        words = [w for w in re.findall(r"[\w']+", q.lower()) if len(w) > 1]
        ids = [i["id"] for i in items]
        full = await db.recordings().find(
            {"_id": {"$in": ids}, **auth.owner_filter(user)},
            {"segments": 1, "translation": 1, "speaker_labels": 1},
        ).to_list(len(ids))
        by_id = {f["_id"]: f for f in full}
        for item in items:
            src = by_id.get(item["id"], {})
            hits = []
            # Search the English first when it exists: an English query on an
            # Arabic recording must return a line the searcher can read.
            haystack = (src.get("translation") or []) + (src.get("segments") or [])
            for seg in haystack:
                low = str(seg.get("text", "")).lower()
                if any(w in low for w in words):
                    hits.append(
                        {
                            "start": seg.get("start", 0),
                            "text": seg.get("text", ""),
                            "speaker": (src.get("speaker_labels") or {}).get(
                                seg.get("speaker"), seg.get("speaker")
                            ),
                        }
                    )
                if len(hits) >= 5:
                    break
            item["matches"] = hits

    return {"items": items, "total": total, "skip": skip, "limit": limit}


@app.get("/api/recordings/{rec_id}")
async def get_recording(rec_id: str, user: dict = Depends(auth.current_user)) -> dict:
    doc = await db.recordings().find_one(_scoped(rec_id, user), {"text": 0})
    if not doc:
        raise HTTPException(404, "Recording not found")
    return _jsonable(doc)


@app.patch("/api/recordings/{rec_id}")
async def patch_recording(
    rec_id: str, patch: models.RecordingPatch, user: dict = Depends(auth.current_user)
) -> dict:
    update: Dict[str, Any] = {}
    data = patch.model_dump(exclude_none=True)
    if "title" in data:
        update["title"] = data["title"].strip()
    if "folder" in data:
        update["folder"] = data["folder"].strip()
    if "tags" in data:
        update["tags"] = sorted({t.strip() for t in data["tags"] if t.strip()})
    if "notes" in data:
        update["notes"] = data["notes"]
    if "recorded_at" in data:
        parsed = _parse_dt(data["recorded_at"])
        if parsed:
            update["recorded_at"] = parsed
    if not update:
        raise HTTPException(400, "Nothing to update")
    update["updated_at"] = _now()

    doc = await db.recordings().find_one_and_update(
        _scoped(rec_id, user), {"$set": update},
        return_document=True, projection={"text": 0},
    )
    if not doc:
        raise HTTPException(404, "Recording not found")
    await _refresh_sidecar(rec_id)
    return _jsonable(doc)


@app.post("/api/recordings/{rec_id}/speakers")
async def rename_speakers(
    rec_id: str, payload: models.SpeakerRename, user: dict = Depends(auth.current_user)
) -> dict:
    """Rename a speaker -- and treat that as training data.

    Putting a name to a voice is the only labelled example we will ever get, so
    it also enrols or reinforces that person's voiceprint. Recognition improves
    purely as a side effect of using the app.
    """
    doc = await db.recordings().find_one(
        _scoped(rec_id, user),
        {"speaker_labels": 1, "speaker_embeddings": 1, "embedding_engine": 1,
         "speaker_matches": 1},
    )
    if not doc:
        raise HTTPException(404, "Recording not found")

    labels = dict(doc.get("speaker_labels") or {})
    embeddings = doc.get("speaker_embeddings") or {}
    engine = doc.get("embedding_engine") or "none"
    matches = dict(doc.get("speaker_matches") or {})
    learned = []

    for raw, name in payload.labels.items():
        clean = (name or "").strip()[:60]
        if not clean:
            continue
        labels[raw] = clean
        person = await api_people.enroll(
            user["_id"], clean, embeddings.get(raw), engine, rec_id
        )
        if person:
            learned.append(person["name"])
        # A human has spoken; the machine's guess for this speaker is settled.
        matches.pop(raw, None)

    await db.recordings().update_one(
        {"_id": rec_id},
        {"$set": {"speaker_labels": labels, "speaker_matches": matches,
                  "updated_at": _now()}},
    )
    await _refresh_sidecar(rec_id)
    return {"speaker_labels": labels, "learned": learned,
            "speaker_matches": matches}


@app.post("/api/recordings/{rec_id}/speakers/confirm")
async def confirm_speaker(
    rec_id: str, payload: models.ConfirmIn, user: dict = Depends(auth.current_user)
) -> dict:
    """Accept or reject a suggested recognition ("Is this Tim?")."""
    doc = await db.recordings().find_one(
        _scoped(rec_id, user),
        {"speaker_labels": 1, "speaker_matches": 1, "speaker_embeddings": 1,
         "embedding_engine": 1},
    )
    if not doc:
        raise HTTPException(404, "Recording not found")

    matches = dict(doc.get("speaker_matches") or {})
    hit = matches.pop(payload.speaker, None)
    if not hit:
        raise HTTPException(404, "No suggestion for that speaker")

    labels = dict(doc.get("speaker_labels") or {})
    if payload.accept:
        labels[payload.speaker] = hit["name"]
        await api_people.enroll(
            user["_id"], hit["name"],
            (doc.get("speaker_embeddings") or {}).get(payload.speaker),
            doc.get("embedding_engine") or "none", rec_id,
        )
    else:
        # Remember the rejection so the same wrong guess isn't offered again.
        rejected = set(doc.get("rejected_matches") or [])
        rejected.add(f"{payload.speaker}:{hit['person_id']}")
        await db.recordings().update_one(
            {"_id": rec_id}, {"$set": {"rejected_matches": sorted(rejected)}}
        )

    await db.recordings().update_one(
        {"_id": rec_id},
        {"$set": {"speaker_labels": labels, "speaker_matches": matches,
                  "updated_at": _now()}},
    )
    await _refresh_sidecar(rec_id)
    return {"speaker_labels": labels, "speaker_matches": matches}


@app.post("/api/recordings/{rec_id}/reassign")
async def reassign_turn(
    rec_id: str, payload: models.ReassignIn, user: dict = Depends(auth.current_user)
) -> dict:
    """Fix diarization errors by hand.

    Speaker separation gets turns wrong -- crosstalk, a cough, someone leaning
    away from the mic. Without this the only remedy is re-transcribing and
    hoping, so let the human simply correct it.
    """
    doc = await db.recordings().find_one(_scoped(rec_id, user), {"segments": 1})
    if not doc:
        raise HTTPException(404, "Recording not found")

    segments = doc.get("segments") or []
    target = payload.to_speaker
    moved = 0

    if payload.segment_index is not None:
        i = payload.segment_index
        if i < 0 or i >= len(segments):
            raise HTTPException(400, "That turn doesn't exist in this recording")
        segments[i]["speaker"] = target
        moved = 1
    elif payload.from_speaker:
        for seg in segments:
            if seg.get("speaker") == payload.from_speaker:
                seg["speaker"] = target
                moved += 1
    else:
        raise HTTPException(400, "Give either segment_index or from_speaker")

    await db.recordings().update_one(
        {"_id": rec_id}, {"$set": {"segments": segments, "updated_at": _now()}}
    )
    await _refresh_sidecar(rec_id)
    return {"ok": True, "moved": moved}


@app.post("/api/recordings/{rec_id}/requeue")
async def requeue(
    rec_id: str,
    options: models.RequeueOptions = models.RequeueOptions(),
    user: dict = Depends(auth.current_user),
) -> dict:
    doc = await db.recordings().find_one(_scoped(rec_id, user), {"options": 1})
    if not doc:
        raise HTTPException(404, "Recording not found")
    await _enforce_quota(user)
    merged = dict(doc.get("options") or {})
    for key, value in options.model_dump(exclude_none=True).items():
        if value != "":
            merged[key] = value
    await db.recordings().update_one(
        {"_id": rec_id},
        {"$set": {"status": "queued", "progress": 0.0, "error": "",
                  "stage": "waiting for a worker", "options": merged,
                  "updated_at": _now()}},
    )
    return {"ok": True, "options": merged}


@app.delete("/api/recordings/{rec_id}")
async def delete_recording(
    rec_id: str, keep_file: bool = False, user: dict = Depends(auth.current_user)
) -> dict:
    doc = await db.recordings().find_one(_scoped(rec_id, user), {"media_path": 1})
    if not doc:
        raise HTTPException(404, "Recording not found")
    if not keep_file:
        storage.delete_media(doc["media_path"])
    await db.recordings().delete_one({"_id": rec_id})
    return {"ok": True}


@app.get("/api/recordings/{rec_id}/transcript.txt")
async def transcript_txt(rec_id: str, user: dict = Depends(auth.current_user)) -> Response:
    doc = await db.recordings().find_one(_scoped(rec_id, user))
    if not doc:
        raise HTTPException(404, "Recording not found")
    text = textout.render(doc)
    name = storage.safe_name(doc.get("title") or doc.get("original_name") or rec_id)
    return PlainTextResponse(
        text,
        headers={"Content-Disposition": f'attachment; filename="{name}.txt"'},
        media_type="text/plain; charset=utf-8",
    )


def _serve_file(path: str, mime: str, request: Request,
                download_as: Optional[str] = None):
    """Serve a file with byte-range support.

    Range support is what makes a large download RESUMABLE: a dropped
    connection on a 2 GB recording resumes from where it stopped instead of
    starting again. It is the download-side counterpart to the chunked upload,
    and the reason downloads are offered as separate files rather than one zip
    -- a zip would have to be rebuilt from scratch on every retry.
    """
    if not os.path.exists(path):
        raise HTTPException(404, "That file is not on disk")

    file_size = os.path.getsize(path)
    disposition = (
        {"Content-Disposition": f'attachment; filename="{download_as}"'}
        if download_as else {}
    )
    range_header = request.headers.get("range") or request.headers.get("Range")

    if not range_header:
        return FileResponse(
            path, media_type=mime,
            headers={"Accept-Ranges": "bytes",
                     "Cache-Control": "private, max-age=3600", **disposition},
        )

    m = re.match(r"bytes=(\d*)-(\d*)", range_header)
    if not m:
        raise HTTPException(416, "Malformed Range header")
    start = int(m.group(1)) if m.group(1) else 0
    end = int(m.group(2)) if m.group(2) else file_size - 1
    start = max(0, min(start, file_size - 1))
    end = max(start, min(end, file_size - 1))
    length = end - start + 1

    def iterator():
        with open(path, "rb") as f:
            f.seek(start)
            remaining = length
            while remaining > 0:
                chunk = f.read(min(256 * 1024, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk

    return StreamingResponse(
        iterator(),
        status_code=206,
        media_type=mime,
        headers={
            "Content-Range": f"bytes {start}-{end}/{file_size}",
            "Accept-Ranges": "bytes",
            "Content-Length": str(length),
            "Cache-Control": "private, max-age=3600",
            **disposition,
        },
    )


# --------------------------------------------------------------- downloads
@app.get("/api/recordings/{rec_id}/audio")
async def stream_audio(
    rec_id: str, request: Request, user: dict = Depends(auth.current_user)
):
    """In-browser playback. Range-enabled so seeking works."""
    doc = await db.recordings().find_one(
        _scoped(rec_id, user), {"media_path": 1, "mime": 1, "original_name": 1}
    )
    if not doc:
        raise HTTPException(404, "Recording not found")
    return _serve_file(storage.media_path(doc["media_path"]),
                       doc.get("mime") or "application/octet-stream", request)


@app.get("/api/recordings/{rec_id}/download/{what}")
async def download(
    rec_id: str, what: str, request: Request, user: dict = Depends(auth.current_user)
):
    """Download the audio, the PDF or the text -- resumable, on demand.

    All three sit together next to each other on the NAS; this just hands them
    out with the right filename and Content-Type.
    """
    if what not in ("audio", "pdf", "txt"):
        raise HTTPException(404, "Unknown download")

    doc = await db.recordings().find_one(_scoped(rec_id, user))
    if not doc:
        raise HTTPException(404, "Recording not found")

    base = storage.safe_name(doc.get("title") or doc.get("original_name") or rec_id)
    base = os.path.splitext(base)[0]
    rel = doc["media_path"]

    if what == "audio":
        ext = os.path.splitext(rel)[1] or ".bin"
        return _serve_file(storage.media_path(rel),
                           doc.get("mime") or "application/octet-stream",
                           request, download_as=f"{base}{ext}")

    if what == "pdf":
        path = storage.sidecar_pdf_path(rel)
        if not os.path.exists(path):
            # Never 404 on a PDF we can simply make now -- it may predate the
            # feature, or PDF writing may have been off when it was transcribed.
            data = await asyncio.to_thread(pdfout.render, doc)
            if not data:
                ok, why = pdfout.available()
                raise HTTPException(503, f"PDF is unavailable on this server: {why}")
            storage.write_pdf_sidecar(rel, data)
        return _serve_file(path, "application/pdf", request,
                           download_as=f"{base}.pdf")

    text = textout.render(doc)
    return PlainTextResponse(
        text, media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{base}.txt"'},
    )


@app.get("/api/recordings/{rec_id}/files")
async def list_files(rec_id: str, user: dict = Depends(auth.current_user)) -> dict:
    """What exists on disk for this recording, and how big."""
    doc = await db.recordings().find_one(
        _scoped(rec_id, user), {"media_path": 1, "original_name": 1, "kind": 1}
    )
    if not doc:
        raise HTTPException(404, "Recording not found")

    rel = doc["media_path"]
    def info(path, label, kind):
        exists = os.path.exists(path)
        return {"kind": kind, "label": label, "available": exists,
                "bytes": os.path.getsize(path) if exists else 0}

    return {"files": [
        info(storage.media_path(rel),
             "Original " + ("video" if doc.get("kind") == "video" else "audio"), "audio"),
        info(storage.sidecar_pdf_path(rel), "Transcript PDF", "pdf"),
        info(storage.sidecar_txt_path(rel), "Transcript text", "txt"),
    ]}


async def _refresh_sidecar(rec_id: str) -> None:
    """Rewrite the .txt and .pdf that sit beside the audio.

    Called after anything that changes the transcript -- a speaker rename, a
    reassigned turn, an edited title -- so the files on disk never drift from
    what the app shows.
    """
    doc = await db.recordings().find_one({"_id": rec_id})
    if not doc or doc.get("status") != "done":
        return
    if settings.WRITE_TXT_SIDECAR:
        storage.write_sidecar(doc["media_path"], textout.render(doc))
    if settings.WRITE_PDF_SIDECAR:
        # PDF rendering is CPU-bound; keep it off the event loop.
        data = await asyncio.to_thread(pdfout.render, doc)
        storage.write_pdf_sidecar(doc["media_path"], data)


# --------------------------------------------------------------------- nuke
@app.post("/api/account/nuke")
async def nuke_my_recordings(
    payload: models.NukeIn, user: dict = Depends(auth.current_user)
) -> dict:
    """Delete every recording this user owns, and everything derived from it.

    DANGEROUS BY DESIGN, so read the scoping carefully:

    This must NEVER use auth.owner_filter(). For an admin or the owner that
    helper returns {} -- "see everything" -- which is correct for reading and
    catastrophic here: one click would wipe every user's recordings off the
    server. Bulk deletion is always scoped to the caller's own id, explicitly.
    """
    if payload.confirm != "NUKE":
        raise HTTPException(400, 'Type NUKE to confirm. Nothing was deleted.')

    mine = {"owner_id": user["_id"]}          # explicit. never owner_filter().

    deleted = 0
    freed = 0
    async for rec in db.recordings().find(mine, {"media_path": 1, "size_bytes": 1}):
        freed += int(rec.get("size_bytes") or 0)
        # Removes the media file plus its .txt and .pdf siblings.
        storage.delete_media(rec["media_path"])
        deleted += 1

    result = await db.recordings().delete_many(mine)

    voices = 0
    if payload.forget_voices:
        vp = await db.voiceprints().delete_many({"owner_id": user["_id"]})
        voices = vp.deleted_count

    # Any half-finished uploads of theirs go too.
    uploads = await db.uploads().find(mine, {"_id": 1}).to_list(500)
    for up in uploads:
        storage.discard(up["_id"])
    await db.uploads().delete_many(mine)

    # Optionally erase the account itself. No support ticket, no waiting period,
    # no soft-delete flag that an operator could reverse -- the row is gone.
    account_deleted = False
    if payload.delete_account:
        if auth.is_god_email(user.get("email", "")):
            # The owner deleting their own account would lock everyone out of
            # administering the server. Their recordings still go.
            raise HTTPException(
                400,
                "The owner account cannot delete itself. Your recordings were "
                "deleted; change GOD_EMAIL first if you really mean to leave.",
            )
        await db.sessions().delete_many({"user_id": user["_id"]})
        await db.auth_tokens().delete_many({"user_id": user["_id"]})
        await db.users().delete_one({"_id": user["_id"]})
        account_deleted = True

    print(f"[nuke] {user.get('email')} deleted {deleted} recording(s), "
          f"{voices} voiceprint(s), freed {freed} bytes"
          + (", ACCOUNT DELETED" if account_deleted else ""), flush=True)

    response = JSONResponse({
        "ok": True,
        "recordings_deleted": max(deleted, result.deleted_count),
        "voices_forgotten": voices,
        "uploads_discarded": len(uploads),
        "bytes_freed": freed,
        "account_deleted": account_deleted,
    })
    if account_deleted:
        auth.clear_session_cookie(response)
    return response


# ---------------------------------------------------------------- worker API
@app.post("/api/worker/claim")
async def worker_claim(
    payload: models.WorkerClaim, x_worker_token: Optional[str] = Header(default=None)
):
    _check_worker(x_worker_token)
    await db.workers().update_one(
        {"_id": payload.worker},
        {"$set": {"device": payload.device, "last_seen": _now(), "models": payload.models}},
        upsert=True,
    )
    await _requeue_stale()

    doc = await db.recordings().find_one_and_update(
        {"status": "queued"},
        {"$set": {"status": "processing", "lease_at": _now(), "progress": 0.0,
                  "stage": "starting", "worker": payload.worker, "updated_at": _now()}},
        sort=[("created_at", 1)],
        projection={"segments": 0, "text": 0},
        return_document=True,
    )
    if not doc:
        await db.workers().update_one({"_id": payload.worker}, {"$set": {"current": None}})
        return Response(status_code=204)

    await db.workers().update_one(
        {"_id": payload.worker},
        {"$set": {"current": {"id": doc["_id"], "title": doc.get("title")}}},
    )
    return {
        "id": doc["_id"],
        "title": doc.get("title"),
        "original_name": doc.get("original_name"),
        "size_bytes": doc.get("size_bytes"),
        "audio_url": f"/api/worker/jobs/{doc['_id']}/audio",
        "options": doc.get("options") or {},
    }


@app.post("/api/worker/heartbeat")
async def worker_heartbeat(
    payload: models.WorkerClaim, x_worker_token: Optional[str] = Header(default=None)
) -> dict:
    _check_worker(x_worker_token)
    await db.workers().update_one(
        {"_id": payload.worker},
        {"$set": {"device": payload.device, "last_seen": _now()}},
        upsert=True,
    )
    return {"ok": True}


@app.get("/api/worker/jobs/{rec_id}/audio")
async def worker_audio(rec_id: str, x_worker_token: Optional[str] = Header(default=None)):
    _check_worker(x_worker_token)
    doc = await db.recordings().find_one({"_id": rec_id}, {"media_path": 1, "mime": 1,
                                                           "original_name": 1})
    if not doc:
        raise HTTPException(404, "Recording not found")
    path = storage.media_path(doc["media_path"])
    if not os.path.exists(path):
        raise HTTPException(404, "Audio file is missing from disk")
    return FileResponse(path, media_type=doc.get("mime") or "application/octet-stream",
                        filename=doc.get("original_name"))


@app.post("/api/worker/jobs/{rec_id}/progress")
async def worker_progress(
    rec_id: str, payload: models.WorkerProgress,
    x_worker_token: Optional[str] = Header(default=None)
) -> dict:
    _check_worker(x_worker_token)
    await db.recordings().update_one(
        {"_id": rec_id},
        {"$set": {"progress": max(0.0, min(1.0, payload.progress)),
                  "stage": payload.stage[:120], "lease_at": _now(),
                  "updated_at": _now()}},
    )
    return {"ok": True}


@app.post("/api/worker/jobs/{rec_id}/error")
async def worker_error(
    rec_id: str, payload: models.WorkerError,
    x_worker_token: Optional[str] = Header(default=None)
) -> dict:
    _check_worker(x_worker_token)
    await db.recordings().update_one(
        {"_id": rec_id},
        {"$set": {"status": "failed", "error": payload.message[:2000],
                  "stage": "failed", "updated_at": _now()}},
    )
    return {"ok": True}


@app.post("/api/worker/jobs/{rec_id}/result")
async def worker_result(
    rec_id: str, payload: models.WorkerResult,
    x_worker_token: Optional[str] = Header(default=None)
) -> dict:
    _check_worker(x_worker_token)
    doc = await db.recordings().find_one({"_id": rec_id}, {"speaker_labels": 1})
    if not doc:
        raise HTTPException(404, "Recording not found")

    segments = [s.model_dump() for s in payload.segments]
    order: List[str] = []
    for seg in segments:
        spk = seg.get("speaker")
        if spk and spk not in order:
            order.append(spk)
    labels = _default_labels(order)
    labels.update({k: v for k, v in (doc.get("speaker_labels") or {}).items() if k in labels})

    # ---- voice recognition -------------------------------------------------
    # Compare each speaker's voiceprint against the people this user has named
    # before. Confident matches are applied; weaker ones become a suggestion
    # the user can accept or reject in the UI.
    owner_id = doc.get("owner_id")
    matches: Dict[str, Any] = {}
    if owner_id and payload.speaker_embeddings:
        known = await db.voiceprints().find({"owner_id": owner_id}).to_list(1000)
        if known:
            found = voiceid.match_all(
                payload.speaker_embeddings, payload.embedding_engine, known
            )
            for raw, hit in found.items():
                if raw not in labels:
                    continue
                if hit["auto"]:
                    labels[raw] = hit["name"]
                    hit = dict(hit, applied=True)
                matches[raw] = hit

    translation = [s.model_dump() for s in payload.translation]
    full_text = " ".join(s["text"].strip() for s in segments).strip()
    english_text = " ".join(s["text"].strip() for s in translation).strip()
    update = {
        "status": "done",
        "progress": 1.0,
        "stage": "complete",
        "error": "",
        "segments": segments,
        "speaker_labels": labels,
        "speaker_embeddings": payload.speaker_embeddings,
        "embedding_engine": payload.embedding_engine,
        "speaker_matches": matches,
        "summary": payload.summary.model_dump(),
        "text": full_text,
        "text_en": english_text,
        "translation": translation,
        "translated_from": payload.translated_from,
        "is_rtl": languages.is_rtl(payload.language),
        "language_name": languages.name_of(payload.language),
        # Word count follows whichever text the reader will actually read.
        "word_count": len((english_text or full_text).split()),
        "duration_sec": float(payload.duration or 0),
        "language": payload.language,
        "language_probability": float(payload.language_probability or 0),
        "engine": payload.engine,
        "finished_at": _now(),
        "updated_at": _now(),
    }
    await db.recordings().update_one({"_id": rec_id}, {"$set": update})

    # Writes the .txt and .pdf next to the audio.
    await _refresh_sidecar(rec_id)

    worker_name = (await db.recordings().find_one({"_id": rec_id}, {"worker": 1}) or {}).get(
        "worker"
    )
    if worker_name:
        await db.workers().update_one({"_id": worker_name}, {"$set": {"current": None}})
    return {"ok": True}


# ============================================================================
# ROUTERS LAST.
#
# FastAPI snapshots a router at include_router() time: any @router route
# declared after the include call is silently ignored and 404s. Keeping these
# calls at the absolute end of the file makes that impossible.
# ============================================================================
app.include_router(api_auth.router)
app.include_router(api_admin.router)
app.include_router(api_people.router)
app.include_router(api_site.router)
