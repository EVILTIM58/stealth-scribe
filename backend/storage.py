"""Files on disk: uploads in progress, and the media library."""

from __future__ import annotations

import os
import re
import shutil
import time
import unicodedata
from datetime import datetime
from typing import Optional

import settings

# An upload_id becomes part of a filesystem path, so it must be a safe token.
# Never interpolate a client-supplied string into a path without this check.
UPLOAD_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{8,64}$")


def valid_upload_id(upload_id: Optional[str]) -> bool:
    return bool(upload_id and UPLOAD_ID_RE.match(upload_id))


def sweep_stale_chunks(max_age_seconds: int = 24 * 3600) -> int:
    """Delete chunk folders from uploads that were abandoned mid-flight.

    The Mongo TTL index expires the *session document*, but that would leave the
    partial files on disk forever and eventually fill the volume.
    """
    removed = 0
    try:
        entries = os.listdir(settings.TMP_DIR)
    except OSError:
        return 0
    now = time.time()
    for name in entries:
        path = os.path.join(settings.TMP_DIR, name)
        if not os.path.isdir(path):
            continue
        try:
            if now - os.path.getmtime(path) > max_age_seconds:
                shutil.rmtree(path, ignore_errors=True)
                removed += 1
        except OSError:
            continue
    return removed


def ensure_dirs() -> None:
    os.makedirs(settings.MEDIA_DIR, exist_ok=True)
    os.makedirs(settings.TMP_DIR, exist_ok=True)


def safe_name(name: str) -> str:
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    name = re.sub(r"[^A-Za-z0-9._ \-]+", "_", name).strip(" .")
    return name[:180] or "recording"


def chunk_dir(upload_id: str) -> str:
    path = os.path.join(settings.TMP_DIR, upload_id)
    os.makedirs(path, exist_ok=True)
    return path


def chunk_path(upload_id: str, index: int) -> str:
    return os.path.join(chunk_dir(upload_id), f"{index:06d}.part")


def assemble(upload_id: str, total_chunks: int, dest_path: str) -> int:
    """Concatenate uploaded chunks into dest_path. Returns bytes written."""
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    written = 0
    with open(dest_path, "wb") as out:
        for i in range(total_chunks):
            part = chunk_path(upload_id, i)
            if not os.path.exists(part):
                raise FileNotFoundError(f"Missing chunk {i} of {total_chunks}")
            with open(part, "rb") as f:
                while True:
                    buf = f.read(1024 * 1024)
                    if not buf:
                        break
                    out.write(buf)
                    written += len(buf)
    shutil.rmtree(chunk_dir(upload_id), ignore_errors=True)
    return written


def discard(upload_id: str) -> None:
    shutil.rmtree(chunk_dir(upload_id), ignore_errors=True)


def media_path(rel: str) -> str:
    return os.path.join(settings.MEDIA_DIR, rel)


def allocate_media_path(original_name: str, recording_id: str) -> str:
    """Return a path relative to MEDIA_DIR, organised by year/month."""
    now = datetime.now()
    folder = os.path.join(f"{now.year:04d}", f"{now.month:02d}")
    os.makedirs(os.path.join(settings.MEDIA_DIR, folder), exist_ok=True)
    base, ext = os.path.splitext(safe_name(original_name))
    ext = ext.lower() or ".mp3"
    candidate = os.path.join(folder, f"{base}{ext}")
    if os.path.exists(os.path.join(settings.MEDIA_DIR, candidate)):
        candidate = os.path.join(folder, f"{base}-{recording_id[:8]}{ext}")
    return candidate.replace("\\", "/")


def sidecar_txt_path(rel_media: str) -> str:
    return os.path.splitext(media_path(rel_media))[0] + ".txt"


def sidecar_pdf_path(rel_media: str) -> str:
    return os.path.splitext(media_path(rel_media))[0] + ".pdf"


def write_pdf_sidecar(rel_media: str, data: bytes) -> Optional[str]:
    if not data:
        return None
    try:
        path = sidecar_pdf_path(rel_media)
        with open(path, "wb") as f:
            f.write(data)
        return path
    except OSError:
        return None


def write_sidecar(rel_media: str, text: str) -> Optional[str]:
    try:
        path = sidecar_txt_path(rel_media)
        with open(path, "w", encoding="utf-8", newline="\r\n") as f:
            f.write(text)
        return path
    except OSError:
        return None


def delete_media(rel_media: str) -> None:
    """Delete the recording and everything derived from it -- audio, .txt, .pdf."""
    for path in (media_path(rel_media), sidecar_txt_path(rel_media),
                 sidecar_pdf_path(rel_media)):
        try:
            os.remove(path)
        except OSError:
            pass


def disk_usage() -> dict:
    try:
        total, used, free = shutil.disk_usage(settings.MEDIA_DIR)
        return {"total": total, "used": used, "free": free}
    except OSError:
        return {"total": 0, "used": 0, "free": 0}
