"""Google and Facebook sign-in (OAuth 2.0 authorization-code flow).

Uses stdlib urllib in a worker thread rather than adding an HTTP client
dependency. Both providers verify email addresses, which is what makes it safe
to link a social login to an existing account with the same address.
"""

from __future__ import annotations

import asyncio
import json
import secrets
import urllib.error
import urllib.parse
import urllib.request
from typing import Dict, Optional

import settings

GOOGLE_AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO = "https://openidconnect.googleapis.com/v1/userinfo"

FACEBOOK_AUTH = "https://www.facebook.com/v19.0/dialog/oauth"
FACEBOOK_TOKEN = "https://graph.facebook.com/v19.0/oauth/access_token"
FACEBOOK_ME = "https://graph.facebook.com/v19.0/me"


class OAuthError(Exception):
    pass


def enabled() -> Dict[str, bool]:
    return {
        "google": bool(settings.GOOGLE_CLIENT_ID and settings.GOOGLE_CLIENT_SECRET),
        "facebook": bool(settings.FACEBOOK_APP_ID and settings.FACEBOOK_APP_SECRET),
    }


def redirect_uri(provider: str) -> str:
    return f"{settings.SITE_BASE_URL.rstrip('/')}/api/auth/{provider}/callback"


def new_state() -> str:
    return secrets.token_urlsafe(24)


def authorize_url(provider: str, state: str) -> str:
    if provider == "google":
        if not enabled()["google"]:
            raise OAuthError("Google sign-in is not configured on this server.")
        params = {
            "client_id": settings.GOOGLE_CLIENT_ID,
            "redirect_uri": redirect_uri("google"),
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
            "access_type": "online",
            "prompt": "select_account",
        }
        return f"{GOOGLE_AUTH}?{urllib.parse.urlencode(params)}"

    if provider == "facebook":
        if not enabled()["facebook"]:
            raise OAuthError("Facebook sign-in is not configured on this server.")
        params = {
            "client_id": settings.FACEBOOK_APP_ID,
            "redirect_uri": redirect_uri("facebook"),
            "response_type": "code",
            "scope": "email,public_profile",
            "state": state,
        }
        return f"{FACEBOOK_AUTH}?{urllib.parse.urlencode(params)}"

    raise OAuthError(f"Unknown provider '{provider}'")


# ----------------------------------------------------------------- transport
def _request(url: str, *, data: Optional[dict] = None, headers: Optional[dict] = None) -> dict:
    body = urllib.parse.urlencode(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        raise OAuthError(f"Provider returned {exc.code}: {detail}") from None
    except urllib.error.URLError as exc:
        raise OAuthError(f"Could not reach the provider: {exc.reason}") from None
    except json.JSONDecodeError:
        raise OAuthError("Provider returned a malformed response") from None


async def _arequest(url: str, **kwargs) -> dict:
    return await asyncio.to_thread(_request, url, **kwargs)


# ------------------------------------------------------------------ exchange
async def exchange(provider: str, code: str) -> dict:
    """Swap an authorization code for a normalised profile dict."""
    if provider == "google":
        token = await _arequest(
            GOOGLE_TOKEN,
            data={
                "code": code,
                "client_id": settings.GOOGLE_CLIENT_ID,
                "client_secret": settings.GOOGLE_CLIENT_SECRET,
                "redirect_uri": redirect_uri("google"),
                "grant_type": "authorization_code",
            },
        )
        access = token.get("access_token")
        if not access:
            raise OAuthError("Google did not return an access token")
        info = await _arequest(
            GOOGLE_USERINFO, headers={"Authorization": f"Bearer {access}"}
        )
        email = (info.get("email") or "").strip().lower()
        if not email:
            raise OAuthError("Google did not share an email address")
        if not info.get("email_verified", True):
            raise OAuthError("That Google account's email is not verified")
        return {
            "email": email,
            "name": info.get("name") or "",
            "picture": info.get("picture") or "",
            "provider_id": info.get("sub") or email,
        }

    if provider == "facebook":
        token = await _arequest(
            FACEBOOK_TOKEN + "?" + urllib.parse.urlencode({
                "client_id": settings.FACEBOOK_APP_ID,
                "client_secret": settings.FACEBOOK_APP_SECRET,
                "redirect_uri": redirect_uri("facebook"),
                "code": code,
            })
        )
        access = token.get("access_token")
        if not access:
            raise OAuthError("Facebook did not return an access token")
        info = await _arequest(
            FACEBOOK_ME + "?" + urllib.parse.urlencode({
                "fields": "id,name,email,picture.type(large)",
                "access_token": access,
            })
        )
        email = (info.get("email") or "").strip().lower()
        if not email:
            # Facebook accounts registered by phone number have no email, and
            # the user can also decline the permission.
            raise OAuthError(
                "Your Facebook account did not share an email address. "
                "Sign up with email and password instead."
            )
        picture = ""
        try:
            picture = info["picture"]["data"]["url"]
        except (KeyError, TypeError):
            pass
        return {
            "email": email,
            "name": info.get("name") or "",
            "picture": picture,
            "provider_id": info.get("id") or email,
        }

    raise OAuthError(f"Unknown provider '{provider}'")
