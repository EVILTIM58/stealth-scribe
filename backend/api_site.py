"""/api/sitemap.xml, /api/robots.txt and the contact form.

nginx rewrites the root paths /sitemap.xml and /robots.txt to these, because
Google and AdSense fetch the root paths and will not look under /api.
"""

from __future__ import annotations

import datetime as dt
import html
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import PlainTextResponse, Response

import auth
import mailer
import models
import settings

router = APIRouter(tags=["site"])

# Public, indexable pages. Recordings are private and never appear here.
PUBLIC_PAGES = [
    ("/", "weekly", "1.0"),
    ("/about", "monthly", "0.7"),
    ("/contact", "monthly", "0.6"),
    ("/privacy", "yearly", "0.4"),
    ("/terms", "yearly", "0.4"),
    ("/guidelines", "yearly", "0.4"),
    ("/dmca", "yearly", "0.4"),
    ("/changelog", "weekly", "0.5"),
    ("/login", "monthly", "0.3"),
    ("/signup", "monthly", "0.5"),
]


class ContactIn(models.Strict):
    name: str = ""
    email: str
    subject: str = ""
    message: str


def site_base_url(request: Request) -> str:
    """Explicit env var wins; otherwise reconstruct from proxy headers."""
    if settings.SITE_BASE_URL and not settings.SITE_BASE_URL.startswith("http://localhost"):
        return settings.SITE_BASE_URL.rstrip("/")
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or ""
    return f"{proto}://{host}".rstrip("/")


@router.get("/api/sitemap.xml")
async def sitemap(request: Request) -> Response:
    base = site_base_url(request)
    today = dt.date.today().isoformat()
    entries = "\n".join(
        f"  <url>\n"
        f"    <loc>{html.escape(base + path)}</loc>\n"
        f"    <lastmod>{today}</lastmod>\n"
        f"    <changefreq>{freq}</changefreq>\n"
        f"    <priority>{priority}</priority>\n"
        f"  </url>"
        for path, freq, priority in PUBLIC_PAGES
    )
    xml = ('<?xml version="1.0" encoding="UTF-8"?>\n'
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
           f"{entries}\n</urlset>\n")
    return Response(content=xml, media_type="application/xml",
                    headers={"Cache-Control": "public, max-age=3600"})


@router.get("/api/robots.txt")
async def robots(request: Request) -> PlainTextResponse:
    base = site_base_url(request)
    body = f"""User-agent: *
Allow: /$
Allow: /about
Allow: /contact
Allow: /privacy
Allow: /terms
Allow: /guidelines
Allow: /dmca
Allow: /changelog
Allow: /login
Allow: /signup

# Everything below is private user data or machine-only.
Disallow: /api/
Disallow: /library
Disallow: /admin
Disallow: /account
Disallow: /verify
Disallow: /reset

Sitemap: {base}/sitemap.xml
"""
    return PlainTextResponse(body, headers={"Cache-Control": "public, max-age=3600"})


@router.get("/api/site/meta")
async def site_meta() -> dict:
    """Single source of truth for the legal pages, so addresses and
    jurisdiction are never hardcoded in two places."""
    return {
        "site_name": settings.SITE_NAME,
        "base_url": settings.SITE_BASE_URL,
        "contact_email": settings.CONTACT_EMAIL,
        "legal_email": settings.LEGAL_EMAIL,
        "dmca_email": settings.DMCA_EMAIL,
        "jurisdiction": settings.JURISDICTION,
        "version": settings.APP_VERSION,
    }


@router.post("/api/contact")
async def contact(
    payload: ContactIn,
    request: Request,
    user: Optional[dict] = Depends(auth.optional_user),
) -> dict:
    email = payload.email.strip().lower()
    if not auth.EMAIL_RE.match(email):
        raise HTTPException(400, "Please give a valid email address so we can reply.")
    message = payload.message.strip()
    if len(message) < 10:
        raise HTTPException(400, "Please write a bit more so we can help.")
    if len(message) > 8000:
        raise HTTPException(400, "That message is too long.")

    who = f"{payload.name.strip() or 'Someone'} <{email}>"
    account = f"signed in as {user['email']} ({user['role']})" if user else "not signed in"
    subject = f"[{settings.SITE_NAME}] {payload.subject.strip() or 'Contact form'}"
    body = (f"From: {who}\n"
            f"Account: {account}\n"
            f"IP: {auth.client_ip(request)}\n"
            f"Received: {auth.now().isoformat()}Z\n\n{message}\n")

    sent = await mailer.send(
        settings.CONTACT_EMAIL,
        subject,
        f"<pre style='font-family:ui-monospace,monospace;white-space:pre-wrap'>"
        f"{html.escape(body)}</pre>",
        body,
    )
    if not sent:
        raise HTTPException(
            503,
            f"Message could not be sent right now. Please email {settings.CONTACT_EMAIL} directly.",
        )
    return {"ok": True, "message": "Thanks — we'll get back to you."}
