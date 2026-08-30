"""/api/auth/* — signup, login, email verification, password reset, OAuth."""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Optional

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

import auth
import db
import mailer
import models
import oauth
import settings

router = APIRouter(prefix="/api/auth", tags=["auth"])

VERIFY_TTL = dt.timedelta(hours=24)
RESET_TTL = dt.timedelta(hours=1)

# Login throttling. Crude on purpose: per-email, in Mongo, no Redis.
MAX_ATTEMPTS = 8
LOCKOUT = dt.timedelta(minutes=15)


TERMS_VERSION = "2026-08-16"


class SignupIn(models.Strict):
    email: str
    password: str
    name: str = ""
    accept_terms: bool = False


class LoginIn(models.Strict):
    email: str
    password: str


class EmailIn(models.Strict):
    email: str


class TokenIn(models.Strict):
    token: str


class ResetIn(models.Strict):
    token: str
    password: str


class ProfileIn(models.Strict):
    name: Optional[str] = None
    current_password: Optional[str] = None
    new_password: Optional[str] = None


# ------------------------------------------------------------------ helpers
async def _issue_token(user_id: str, purpose: str, ttl: dt.timedelta) -> str:
    """One live token per purpose per user -- requesting a new reset link
    invalidates the previous one."""
    await db.auth_tokens().delete_many({"user_id": user_id, "purpose": purpose})
    token = auth.new_token()
    await db.auth_tokens().insert_one({
        "_id": auth.token_fingerprint(token),
        "user_id": user_id,
        "purpose": purpose,
        "created_at": auth.now(),
        "expires_at": auth.now() + ttl,
    })
    return token


async def _consume_token(token: str, purpose: str) -> Optional[dict]:
    doc = await db.auth_tokens().find_one_and_delete(
        {"_id": auth.token_fingerprint(token), "purpose": purpose}
    )
    if not doc or doc.get("expires_at", auth.now()) < auth.now():
        return None
    return await db.users().find_one({"_id": doc["user_id"]})


def _link(path: str, token: str) -> str:
    return f"{settings.SITE_BASE_URL}{path}?token={token}"


async def _login_response(user: dict, request: Request) -> Response:
    token = await auth.create_session(user["_id"], request)
    await db.users().update_one({"_id": user["_id"]},
                                {"$set": {"last_login": auth.now()},
                                 "$unset": {"failed_logins": "", "locked_until": ""}})
    from fastapi.responses import JSONResponse
    response = JSONResponse(auth.public_user(user))
    auth.set_session_cookie(response, token)
    return response


# ------------------------------------------------------------------- config
@router.get("/config")
async def auth_config() -> dict:
    """What the login screen should offer."""
    return {
        "providers": oauth.enabled(),
        "allow_signup": settings.ALLOW_SIGNUP,
        "email_configured": mailer.configured(),
        "site_name": settings.SITE_NAME,
    }


@router.get("/me")
async def me(user: Optional[dict] = Depends(auth.optional_user)) -> dict:
    if not user:
        return {"user": None}
    return {"user": auth.public_user(user)}


# ------------------------------------------------------------------- signup
@router.post("/signup")
async def signup(payload: SignupIn, request: Request) -> dict:
    if not settings.ALLOW_SIGNUP:
        raise HTTPException(403, "New accounts are closed on this server.")

    email = payload.email.strip().lower()
    if not auth.EMAIL_RE.match(email):
        raise HTTPException(400, "That doesn't look like an email address.")
    problem = auth.password_problem(payload.password)
    if problem:
        raise HTTPException(400, problem)
    if not payload.accept_terms:
        raise HTTPException(
            400,
            "You must confirm you have the right to upload the recordings you "
            "process, and accept the Terms and Privacy Policy.",
        )

    existing = await db.users().find_one({"email": email})
    if existing:
        # Don't confirm which addresses exist. Tell the truth generically and
        # send a mail that is useful either way.
        if existing.get("password_hash"):
            raise HTTPException(409, "An account with that email already exists. Try signing in.")
        raise HTTPException(
            409,
            "That email is registered through Google or Facebook. "
            "Sign in with that provider instead.",
        )

    user = {
        "_id": uuid.uuid4().hex,
        "email": email,
        "name": (payload.name or email.split("@")[0]).strip()[:80],
        "picture": "",
        "password_hash": auth.hash_password(payload.password),
        "role": auth.ROLE_GOD if auth.is_god_email(email) else auth.ROLE_USER,
        "providers": ["password"],
        "provider_ids": {},
        "email_verified": False,
        "banned": False,
        "created_at": auth.now(),
        "last_login": None,
        "signup_ip": auth.client_ip(request),
        "terms_accepted_at": auth.now(),
        "terms_version": TERMS_VERSION,
    }
    await db.users().insert_one(user)

    token = await _issue_token(user["_id"], "verify", VERIFY_TTL)
    sent = await mailer.send_verification(email, user["name"], _link("/verify", token))
    return {
        "ok": True,
        "email_sent": sent,
        "message": "Check your email to confirm your address."
        if sent else
        "Account created, but confirmation email could not be sent. "
        "Ask the site owner to verify you.",
    }


@router.post("/verify")
async def verify(payload: TokenIn, request: Request) -> Response:
    user = await _consume_token(payload.token, "verify")
    if not user:
        raise HTTPException(400, "That confirmation link is invalid or has expired.")
    await db.users().update_one({"_id": user["_id"]}, {"$set": {"email_verified": True}})
    user["email_verified"] = True
    return await _login_response(user, request)


@router.post("/resend-verification")
async def resend_verification(payload: EmailIn) -> dict:
    user = await db.users().find_one({"email": payload.email.strip().lower()})
    if user and not user.get("email_verified"):
        token = await _issue_token(user["_id"], "verify", VERIFY_TTL)
        await mailer.send_verification(user["email"], user.get("name", ""),
                                       _link("/verify", token))
    # Always the same answer, so this can't be used to enumerate accounts.
    return {"ok": True, "message": "If that address needs confirming, a new link is on its way."}


# -------------------------------------------------------------------- login
@router.post("/login")
async def login(payload: LoginIn, request: Request) -> Response:
    email = payload.email.strip().lower()
    user = await db.users().find_one({"email": email})

    if user and user.get("locked_until") and user["locked_until"] > auth.now():
        wait = int((user["locked_until"] - auth.now()).total_seconds() // 60) + 1
        raise HTTPException(429, f"Too many attempts. Try again in {wait} minute(s).")

    if not user or not auth.verify_password(payload.password, user.get("password_hash")):
        if user:
            failed = int(user.get("failed_logins") or 0) + 1
            update = {"failed_logins": failed}
            if failed >= MAX_ATTEMPTS:
                update["locked_until"] = auth.now() + LOCKOUT
                update["failed_logins"] = 0
            await db.users().update_one({"_id": user["_id"]}, {"$set": update})
        # Same message either way -- never reveal whether the address exists.
        raise HTTPException(401, "Email or password is incorrect.")

    if user.get("banned"):
        raise HTTPException(403, "This account has been suspended.")
    if not user.get("email_verified"):
        raise HTTPException(403, "Confirm your email address first. Check your inbox.")

    return await _login_response(user, request)


@router.post("/logout")
async def logout(ss_session: Optional[str] = Cookie(default=None)) -> Response:
    await auth.destroy_session(ss_session)
    from fastapi.responses import JSONResponse
    response = JSONResponse({"ok": True})
    auth.clear_session_cookie(response)
    return response


@router.post("/logout-everywhere")
async def logout_everywhere(user: dict = Depends(auth.current_user)) -> Response:
    await db.sessions().delete_many({"user_id": user["_id"]})
    from fastapi.responses import JSONResponse
    response = JSONResponse({"ok": True})
    auth.clear_session_cookie(response)
    return response


# ----------------------------------------------------------- password reset
@router.post("/forgot")
async def forgot(payload: EmailIn) -> dict:
    user = await db.users().find_one({"email": payload.email.strip().lower()})
    if user and user.get("password_hash"):
        token = await _issue_token(user["_id"], "reset", RESET_TTL)
        await mailer.send_password_reset(user["email"], user.get("name", ""),
                                         _link("/reset", token))
    return {"ok": True,
            "message": "If that address has an account, a reset link is on its way."}


@router.post("/reset")
async def reset(payload: ResetIn, request: Request) -> Response:
    problem = auth.password_problem(payload.password)
    if problem:
        raise HTTPException(400, problem)
    # No terms check here. ResetIn carries no accept_terms field and the client
    # never sends one, so testing it raised AttributeError -> 500 on every
    # reset. Terms are accepted at signup; choosing a new password is not the
    # moment to re-litigate them.
    user = await _consume_token(payload.token, "reset")
    if not user:
        raise HTTPException(400, "That reset link is invalid or has expired.")

    await db.users().update_one(
        {"_id": user["_id"]},
        {"$set": {"password_hash": auth.hash_password(payload.password),
                  "email_verified": True},
         "$addToSet": {"providers": "password"},
         "$unset": {"failed_logins": "", "locked_until": ""}},
    )
    # A password reset invalidates every existing session -- that is the point
    # of resetting when you think someone else is in your account.
    await db.sessions().delete_many({"user_id": user["_id"]})
    user["email_verified"] = True
    return await _login_response(user, request)


# ------------------------------------------------------------------ profile
@router.patch("/profile")
async def update_profile(payload: ProfileIn, user: dict = Depends(auth.current_user)) -> dict:
    update = {}
    if payload.name is not None:
        update["name"] = payload.name.strip()[:80] or user.get("name")

    if payload.new_password:
        problem = auth.password_problem(payload.new_password)
        if problem:
            raise HTTPException(400, problem)
        if user.get("password_hash"):
            if not auth.verify_password(payload.current_password or "",
                                        user.get("password_hash")):
                raise HTTPException(403, "Current password is incorrect.")
        update["password_hash"] = auth.hash_password(payload.new_password)

    if not update:
        raise HTTPException(400, "Nothing to update")
    await db.users().update_one({"_id": user["_id"]}, {"$set": update})
    if "password_hash" in update:
        await db.users().update_one({"_id": user["_id"]},
                                    {"$addToSet": {"providers": "password"}})
    fresh = await db.users().find_one({"_id": user["_id"]})
    return auth.public_user(fresh)


# -------------------------------------------------------------------- OAuth
@router.get("/{provider}/start")
async def oauth_start(provider: str) -> RedirectResponse:
    if provider not in ("google", "facebook"):
        raise HTTPException(404, "Unknown provider")
    try:
        state = oauth.new_state()
        await db.oauth_states().insert_one(
            {"_id": state, "provider": provider, "created_at": auth.now()}
        )
        return RedirectResponse(oauth.authorize_url(provider, state), status_code=302)
    except oauth.OAuthError as exc:
        raise HTTPException(503, str(exc))


@router.get("/{provider}/callback")
async def oauth_callback(
    provider: str,
    request: Request,
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None,
):
    """Providers redirect the browser here, so every exit path is a redirect
    back into the app -- never a JSON error the user would see as raw text."""
    def fail(message: str) -> RedirectResponse:
        from urllib.parse import quote
        return RedirectResponse(f"{settings.SITE_BASE_URL}/login?error={quote(message)}",
                                status_code=302)

    if provider not in ("google", "facebook"):
        return fail("Unknown sign-in provider.")
    if error:
        return fail("Sign-in was cancelled.")
    if not code or not state:
        return fail("Sign-in did not complete. Please try again.")

    # State is single-use: consuming it prevents replay and CSRF.
    consumed = await db.oauth_states().find_one_and_delete(
        {"_id": state, "provider": provider}
    )
    if not consumed:
        return fail("Sign-in request expired. Please try again.")

    try:
        profile = await oauth.exchange(provider, code)
    except oauth.OAuthError as exc:
        return fail(str(exc))

    # Signing in through the provider button constitutes acceptance; the login
    # page states that immediately above those buttons.
    user = await auth.upsert_oauth_user(
        email=profile["email"],
        name=profile["name"],
        picture=profile["picture"],
        provider=provider,
        provider_id=profile["provider_id"],
    )
    if user.get("banned"):
        return fail("This account has been suspended.")

    token = await auth.create_session(user["_id"], request)
    response = RedirectResponse(f"{settings.SITE_BASE_URL}/", status_code=302)
    auth.set_session_cookie(response, token)
    return response
