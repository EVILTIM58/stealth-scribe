"""Authentication: passwords, sessions, roles.

Deliberately dependency-free. Password hashing uses stdlib scrypt (a proper
memory-hard KDF), tokens use `secrets`. No passlib, no bcrypt wheel, no PyJWT --
nothing here can break a Docker build.
"""

from __future__ import annotations

import base64
import datetime as dt
import hashlib
import hmac
import os
import re
import secrets
import uuid
from typing import Optional

from fastapi import Cookie, Depends, HTTPException, Request, Response

import db
import settings

ROLE_USER = "USER"
ROLE_ADMIN = "ADMIN"
ROLE_GOD = "GOD"
ROLE_RANK = {ROLE_USER: 0, ROLE_ADMIN: 1, ROLE_GOD: 2}
# Tier numbers as the operator thinks of them: 1 = USER, 2 = ADMIN, 3 = GOD.
ROLE_LEVEL = {ROLE_USER: 1, ROLE_ADMIN: 2, ROLE_GOD: 3}

# How long a ban lasts. None = permanent.
BAN_DURATIONS = {
    "1d": ("1 day", dt.timedelta(days=1)),
    "3d": ("3 days", dt.timedelta(days=3)),
    "1w": ("1 week", dt.timedelta(weeks=1)),
    "1m": ("1 month", dt.timedelta(days=30)),
    "permanent": ("Permanent", None),
}

SESSION_COOKIE = "ss_session"
SESSION_DAYS = 30

# scrypt parameters. n=2**15 is ~32 MB and ~100ms per hash on a NAS -- costly
# enough to make offline cracking painful, cheap enough for a login endpoint.
_SCRYPT_N = 2 ** 15
_SCRYPT_R = 8
_SCRYPT_P = 1

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[a-zA-Z]{2,}$")


def now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(tzinfo=None)


# ------------------------------------------------------------------ passwords
def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P,
        dklen=32, maxmem=64 * 1024 * 1024,
    )
    return "$".join(
        ["scrypt", str(_SCRYPT_N), str(_SCRYPT_R), str(_SCRYPT_P),
         base64.b64encode(salt).decode(), base64.b64encode(digest).decode()]
    )


def verify_password(password: str, stored: Optional[str]) -> bool:
    if not stored:
        return False
    try:
        scheme, n, r, p, salt_b64, hash_b64 = stored.split("$")
        if scheme != "scrypt":
            return False
        digest = hashlib.scrypt(
            password.encode("utf-8"), salt=base64.b64decode(salt_b64),
            n=int(n), r=int(r), p=int(p), dklen=len(base64.b64decode(hash_b64)),
            maxmem=64 * 1024 * 1024,
        )
        return hmac.compare_digest(digest, base64.b64decode(hash_b64))
    except (ValueError, TypeError):
        return False


def password_problem(password: str) -> Optional[str]:
    """Return a human-readable reason the password is unacceptable, or None.

    Length beats character-class rules -- NIST agrees, and 'must contain a
    symbol' mostly produces Password1! on a sticky note.
    """
    if len(password or "") < 10:
        return "Password must be at least 10 characters."
    if len(password) > 200:
        return "Password must be under 200 characters."
    if password.lower() in {
        "password12", "password123", "1234567890", "qwertyuiop", "letmeinnow",
        "iloveyou12", "welcome123", "admin12345",
    }:
        return "That password is too common. Pick something else."
    return None


# --------------------------------------------------------------------- tokens
def new_token() -> str:
    return secrets.token_urlsafe(32)


def token_fingerprint(token: str) -> str:
    """Sessions are stored as a hash. A leaked DB dump can't be replayed."""
    return hashlib.sha256(f"{settings.TOKEN_PEPPER}:{token}".encode()).hexdigest()


# ------------------------------------------------------------------- sessions
async def create_session(user_id: str, request: Optional[Request] = None) -> str:
    token = new_token()
    await db.sessions().insert_one(
        {
            "_id": token_fingerprint(token),
            "user_id": user_id,
            "created_at": now(),
            "expires_at": now() + dt.timedelta(days=SESSION_DAYS),
            "user_agent": (request.headers.get("user-agent", "")[:200] if request else ""),
            "ip": client_ip(request) if request else "",
        }
    )
    return token


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=SESSION_DAYS * 24 * 3600,
        httponly=True,
        samesite="lax",
        secure=settings.SITE_BASE_URL.startswith("https://"),
        path="/",
    )


def clear_session_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")


async def destroy_session(token: Optional[str]) -> None:
    if token:
        await db.sessions().delete_one({"_id": token_fingerprint(token)})


def client_ip(request: Optional[Request]) -> str:
    """Real client IP from behind Cloudflare. Only meaningful because traffic
    reaches us exclusively through the tunnel."""
    if not request:
        return ""
    cf = request.headers.get("cf-connecting-ip")
    if cf:
        return cf.strip()
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return (request.client.host if request.client else "") or ""


# ---------------------------------------------------------------------- users
def is_god_email(email: str) -> bool:
    return (email or "").strip().lower() == settings.GOD_EMAIL.strip().lower()


def role_for(email: str, stored_role: Optional[str] = None) -> str:
    """GOD is decided by email on every request, not by a stored field. Nobody
    can grant themselves GOD by editing a document."""
    if is_god_email(email):
        return ROLE_GOD
    role = (stored_role or ROLE_USER).upper()
    return role if role in (ROLE_USER, ROLE_ADMIN) else ROLE_USER


def ban_state(doc: dict) -> dict:
    """Is this account currently banned, and until when?

    A ban with an expiry in the past is simply over -- there is no unban job to
    run and nothing to go wrong if one never runs.
    """
    if not doc.get("banned"):
        return {"banned": False}
    until = doc.get("banned_until")
    if until and until <= now():
        return {"banned": False, "expired": True}
    return {
        "banned": True,
        "until": until.isoformat() if until else None,
        "permanent": until is None,
        "reason": doc.get("ban_reason") or "",
        "by": doc.get("banned_by") or "",
        "at": doc["banned_at"].isoformat() if doc.get("banned_at") else None,
    }


def public_user(doc: dict) -> dict:
    state = ban_state(doc)
    return {
        "id": doc["_id"],
        "email": doc.get("email", ""),
        "name": doc.get("name") or (doc.get("email", "").split("@")[0]),
        "picture": doc.get("picture") or "",
        "role": role_for(doc.get("email", ""), doc.get("role")),
        "level": ROLE_LEVEL[role_for(doc.get("email", ""), doc.get("role"))],
        "providers": doc.get("providers") or [],
        "primary_provider": (doc.get("providers") or ["password"])[0],
        "email_verified": bool(doc.get("email_verified")),
        "banned": state["banned"],
        "ban": state,
        "created_at": (doc.get("created_at") or now()).isoformat(),
        "last_login": (doc["last_login"].isoformat() if doc.get("last_login") else None),
        "has_password": bool(doc.get("password_hash")),
    }


async def upsert_oauth_user(
    *, email: str, name: str, picture: str, provider: str, provider_id: str
) -> dict:
    """Find-or-create for a social login.

    Accounts are linked on verified email: signing in with Google using the same
    address as an existing password account attaches the provider rather than
    creating a duplicate. Only ever do this for providers that verify email --
    otherwise it is an account-takeover vector.
    """
    email = email.strip().lower()
    existing = await db.users().find_one({"email": email})
    if existing:
        await db.users().update_one(
            {"_id": existing["_id"]},
            {
                "$set": {
                    "last_login": now(),
                    "email_verified": True,
                    "name": existing.get("name") or name,
                    "picture": existing.get("picture") or picture,
                    f"provider_ids.{provider}": provider_id,
                },
                "$addToSet": {"providers": provider},
            },
        )
        return await db.users().find_one({"_id": existing["_id"]})

    doc = {
        "_id": uuid.uuid4().hex,
        "email": email,
        "name": name or email.split("@")[0],
        "picture": picture or "",
        "password_hash": None,
        "role": ROLE_GOD if is_god_email(email) else ROLE_USER,
        "providers": [provider],
        "provider_ids": {provider: provider_id},
        "email_verified": True,
        "banned": False,
        "created_at": now(),
        "last_login": now(),
        "terms_accepted_at": now(),
        "terms_version": "2026-08-16",
    }
    await db.users().insert_one(doc)
    return doc


# --------------------------------------------------------------- dependencies
async def optional_user(
    ss_session: Optional[str] = Cookie(default=None),
) -> Optional[dict]:
    """Current user, or None. Never raises."""
    if not ss_session:
        return None
    session = await db.sessions().find_one({"_id": token_fingerprint(ss_session)})
    if not session or session.get("expires_at", now()) < now():
        return None
    user = await db.users().find_one({"_id": session["user_id"]})
    if not user:
        return None

    state = ban_state(user)
    if state.get("expired"):
        # The ban ran out. Clear it here rather than relying on a scheduled job
        # that might never run.
        await db.users().update_one(
            {"_id": user["_id"]},
            {"$set": {"banned": False},
             "$unset": {"banned_until": "", "ban_reason": "",
                        "banned_by": "", "banned_at": ""}},
        )
        user["banned"] = False
    elif state["banned"]:
        return None

    user["role"] = role_for(user.get("email", ""), user.get("role"))
    return user


async def current_user(user: Optional[dict] = Depends(optional_user)) -> dict:
    if not user:
        raise HTTPException(401, "Sign in to continue")
    if not user.get("email_verified"):
        raise HTTPException(403, "Please verify your email address first")
    return user


async def require_admin(user: dict = Depends(current_user)) -> dict:
    if ROLE_RANK.get(user["role"], 0) < ROLE_RANK[ROLE_ADMIN]:
        raise HTTPException(403, "Admin access required")
    return user


async def require_god(user: dict = Depends(current_user)) -> dict:
    if user["role"] != ROLE_GOD:
        raise HTTPException(403, "GOD access required")
    return user


def can_see_everything(user: dict) -> bool:
    return ROLE_RANK.get(user.get("role"), 0) >= ROLE_RANK[ROLE_ADMIN]


def owner_filter(user: dict) -> dict:
    """The single source of truth for 'which recordings may this user see'."""
    return {} if can_see_everything(user) else {"owner_id": user["_id"]}
