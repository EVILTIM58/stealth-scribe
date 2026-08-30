"""Transactional email via Resend.

Verification and password-reset mail only. If RESEND_API_KEY is unset, sends are
skipped and the link is logged to the container log instead -- so a fresh deploy
without mail configured is still usable by the operator.
"""

from __future__ import annotations

import asyncio
import json
import urllib.error
import urllib.request
from typing import Optional

import settings

RESEND_URL = "https://api.resend.com/emails"


def configured() -> bool:
    return bool(settings.RESEND_API_KEY)


def _send(to: str, subject: str, html: str, text: str) -> Optional[str]:
    payload = json.dumps({
        "from": settings.MAIL_FROM,
        "to": [to],
        "subject": subject,
        "html": html,
        "text": text,
    }).encode()
    req = urllib.request.Request(
        RESEND_URL,
        data=payload,
        headers={
            "Authorization": f"Bearer {settings.RESEND_API_KEY}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode()).get("id")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        print(f"[mail] FAILED to {to}: {exc.code} {detail}", flush=True)
    except urllib.error.URLError as exc:
        print(f"[mail] FAILED to {to}: {exc.reason}", flush=True)
    return None


async def send(to: str, subject: str, html: str, text: str) -> bool:
    if not configured():
        print(f"[mail] RESEND_API_KEY unset -- would have sent to {to}: {subject}",
              flush=True)
        print(f"[mail] {text}", flush=True)
        return False
    return bool(await asyncio.to_thread(_send, to, subject, html, text))


# ---------------------------------------------------------------- templates
def _shell(title: str, body_html: str, button_label: str, button_url: str) -> str:
    return f"""<!doctype html>
<html><body style="margin:0;padding:0;background:#04060c;
  font-family:'Segoe UI',system-ui,-apple-system,Roboto,Helvetica,Arial,sans-serif;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
         style="background:#04060c;padding:36px 16px;">
    <tr><td align="center">
      <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
             style="max-width:520px;background:#090f1a;border:1px solid #1a2942;">
        <tr><td style="padding:28px 30px 8px;">
          <div style="font-size:15px;font-weight:800;letter-spacing:.18em;
                      text-transform:uppercase;color:#4cc9f0;">Stealth-Scribe</div>
          <div style="font-size:11px;letter-spacing:.14em;text-transform:uppercase;
                      color:#5a6b85;margin-top:4px;">
            Audio in. Transcribe to English. Save as PDF.
          </div>
        </td></tr>
        <tr><td style="padding:14px 30px 4px;">
          <h1 style="margin:0 0 12px;font-size:20px;color:#e9f1ff;">{title}</h1>
          <div style="font-size:15px;line-height:1.6;color:#c6d4e8;">{body_html}</div>
        </td></tr>
        <tr><td style="padding:22px 30px 6px;">
          <a href="{button_url}"
             style="display:inline-block;background:#1f8fff;color:#ffffff;
                    text-decoration:none;padding:12px 26px;font-weight:600;
                    letter-spacing:.06em;text-transform:uppercase;font-size:13px;">
            {button_label}
          </a>
        </td></tr>
        <tr><td style="padding:16px 30px 28px;">
          <div style="font-size:12px;color:#5a6b85;line-height:1.6;">
            If the button doesn't work, paste this into your browser:<br>
            <span style="color:#4cc9f0;word-break:break-all;">{button_url}</span>
          </div>
        </td></tr>
      </table>
      <div style="max-width:520px;margin-top:14px;font-size:11px;color:#5a6b85;">
        Sent by Stealth-Scribe. If you weren't expecting this, you can ignore it safely.
      </div>
    </td></tr>
  </table>
</body></html>"""


async def send_verification(to: str, name: str, link: str) -> bool:
    return await send(
        to,
        "Confirm your Stealth-Scribe address",
        _shell(
            f"Welcome{', ' + name if name else ''}",
            "<p>Confirm this address to activate your Stealth-Scribe account. "
            "The link is good for 24 hours.</p>",
            "Confirm email",
            link,
        ),
        f"Confirm your Stealth-Scribe address (valid 24 hours):\n\n{link}\n",
    )


async def send_password_reset(to: str, name: str, link: str) -> bool:
    return await send(
        to,
        "Reset your Stealth-Scribe password",
        _shell(
            "Password reset",
            "<p>Use the button below to choose a new password. The link expires "
            "in one hour and can only be used once.</p>"
            "<p style='color:#7d90ad;font-size:13px;'>If you didn't ask for this, "
            "nothing has changed and you can ignore this email.</p>",
            "Choose a new password",
            link,
        ),
        f"Reset your Stealth-Scribe password (valid 1 hour):\n\n{link}\n",
    )
