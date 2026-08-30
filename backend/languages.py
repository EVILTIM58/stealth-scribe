"""Language metadata.

Whisper recognises ~99 languages. These are the ones worth naming in the UI,
plus the two facts the app actually needs: a human-readable name, and whether
the script runs right-to-left (Arabic, Hebrew, Farsi, Urdu) so the transcript
renders correctly instead of as visual gibberish.
"""

from __future__ import annotations

from typing import Dict

# code -> (English name, right-to-left)
LANGUAGES: Dict[str, tuple] = {
    "en": ("English", False),
    "es": ("Spanish", False),
    "fr": ("French", False),
    "de": ("German", False),
    "it": ("Italian", False),
    "pt": ("Portuguese", False),
    "nl": ("Dutch", False),
    "pl": ("Polish", False),
    "ru": ("Russian", False),
    "uk": ("Ukrainian", False),
    "ar": ("Arabic", True),
    "he": ("Hebrew", True),
    "fa": ("Persian (Farsi)", True),
    "ur": ("Urdu", True),
    "tr": ("Turkish", False),
    "zh": ("Chinese", False),
    "ja": ("Japanese", False),
    "ko": ("Korean", False),
    "hi": ("Hindi", False),
    "bn": ("Bengali", False),
    "vi": ("Vietnamese", False),
    "th": ("Thai", False),
    "id": ("Indonesian", False),
    "tl": ("Tagalog", False),
    "sw": ("Swahili", False),
    "el": ("Greek", False),
    "ro": ("Romanian", False),
    "cs": ("Czech", False),
    "hu": ("Hungarian", False),
    "sv": ("Swedish", False),
    "no": ("Norwegian", False),
    "da": ("Danish", False),
    "fi": ("Finnish", False),
    "ta": ("Tamil", False),
    "ms": ("Malay", False),
    "so": ("Somali", False),
    "ps": ("Pashto", True),
    "ku": ("Kurdish", True),
    "am": ("Amharic", False),
}

RTL_CODES = {code for code, (_, rtl) in LANGUAGES.items() if rtl}


def name_of(code: str) -> str:
    code = (code or "").split("-")[0].lower()
    entry = LANGUAGES.get(code)
    return entry[0] if entry else (code.upper() if code else "unknown")


def is_rtl(code: str) -> bool:
    return (code or "").split("-")[0].lower() in RTL_CODES


def as_list() -> list:
    return [{"code": c, "name": n, "rtl": r} for c, (n, r) in LANGUAGES.items()]
