"""Server-side PDF generation.

Every completed recording gets a .pdf written beside its audio and .txt, so the
three files live together on the NAS and can be downloaded on demand.

Two hard parts, both handled defensively:

  * **Unicode.** The built-in PDF fonts are Latin-1 only. A Cyrillic or Arabic
    transcript would come out as mojibake, so a real TrueType font is embedded.
  * **Arabic and Hebrew.** Correct rendering needs glyph *shaping* (letters
    change form by position) and *bidi* reordering. arabic-reshaper and
    python-bidi do that; without them RTL text is emitted unshaped rather than
    silently wrong-looking-but-plausible.

Nothing here may ever fail a job. A PDF is a convenience; the transcript in
Mongo and the .txt are the record. Every failure path returns None and logs.
"""

from __future__ import annotations

import os
from typing import List, Optional, Tuple

import textout

# Debian package `fonts-dejavu-core` (Latin/Cyrillic/Greek) and `fonts-noto-core`
# (Arabic, Hebrew, and much more). Installed in the backend Dockerfile so no
# binary font has to live in the repo.
LATIN_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed.ttf",
    "/usr/share/fonts/TTF/DejaVuSans.ttf",
]
LATIN_BOLD_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf",
]
ARABIC_CANDIDATES = [
    "/usr/share/fonts/truetype/noto/NotoNaskhArabic-Regular.ttf",
    "/usr/share/fonts/truetype/noto/NotoSansArabic-Regular.ttf",
    "/usr/share/fonts/opentype/noto/NotoNaskhArabic-Regular.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",  # last resort
]

INK = (17, 17, 17)
GREY = (110, 110, 110)
RULE = (170, 170, 170)


def _first_existing(paths: List[str]) -> Optional[str]:
    for path in paths:
        if os.path.exists(path):
            return path
    return None


def available() -> Tuple[bool, str]:
    """(can we make PDFs, why not)."""
    try:
        import fpdf  # noqa: F401
    except ImportError:
        return False, "fpdf2 is not installed"
    if not _first_existing(LATIN_CANDIDATES):
        return False, "no embeddable Unicode font found on this system"
    return True, ""


def _shape_rtl(text: str) -> str:
    """Reshape + bidi-reorder Arabic/Hebrew for a PDF renderer that does no
    text layout of its own. Returns the text unchanged if the helpers are
    missing -- unshaped is bad, but silently reversed would be worse."""
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display

        return get_display(arabic_reshaper.reshape(text))
    except Exception:
        return text


def render(doc: dict) -> Optional[bytes]:
    """Build the PDF for a recording. Returns bytes, or None if unavailable."""
    ok, why = available()
    if not ok:
        print(f"[pdf] skipped: {why}", flush=True)
        return None

    try:
        from fpdf import FPDF
    except ImportError:
        return None

    latin = _first_existing(LATIN_CANDIDATES)
    latin_bold = _first_existing(LATIN_BOLD_CANDIDATES) or latin
    arabic = _first_existing(ARABIC_CANDIDATES) or latin

    rtl = bool(doc.get("is_rtl"))
    labels = doc.get("speaker_labels") or {}
    segments = doc.get("segments") or []
    translation = doc.get("translation") or []
    summary = doc.get("summary") or {}

    try:
        pdf = FPDF(orientation="P", unit="mm", format="A4")
        pdf.set_auto_page_break(auto=True, margin=18)
        pdf.add_font("body", "", latin)
        pdf.add_font("body", "B", latin_bold)
        if arabic != latin:
            pdf.add_font("arabic", "", arabic)
        pdf.set_margins(16, 16, 16)
        pdf.add_page()
        width = pdf.w - 32

        def rule():
            pdf.set_draw_color(*RULE)
            pdf.line(16, pdf.get_y(), pdf.w - 16, pdf.get_y())
            pdf.ln(3)

        def heading(text: str):
            pdf.set_font("body", "B", 10)
            pdf.set_text_color(*INK)
            pdf.cell(0, 6, text.upper(), new_x="LMARGIN", new_y="NEXT")
            rule()

        # ---- title block -------------------------------------------------
        pdf.set_font("body", "B", 15)
        pdf.set_text_color(*INK)
        pdf.cell(0, 8, "STEALTH-SCRIBE", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("body", "", 7.5)
        pdf.set_text_color(*GREY)
        pdf.cell(0, 4, "CLEAR. ACCURATE. SECURE.", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(3)
        rule()

        pdf.set_font("body", "B", 14)
        pdf.set_text_color(*INK)
        pdf.multi_cell(width, 7, str(doc.get("title") or doc.get("original_name") or ""))
        pdf.ln(2)

        lang = doc.get("language_name") or doc.get("language") or "unknown"
        rows = [
            ("Recording", str(doc.get("original_name") or "")),
            ("Recorded", textout._stamp(textout._as_dt(doc.get("recorded_at")))),
            ("Duration", textout.hms(doc.get("duration_sec", 0))),
            ("Speakers", str(len(labels) or 1)),
            ("Language", lang + (" -> English" if translation else "")),
            ("Transcribed", textout._stamp(textout._as_dt(doc.get("finished_at")))),
        ]
        if doc.get("folder"):
            rows.append(("Folder", str(doc["folder"])))
        if doc.get("tags"):
            rows.append(("Tags", ", ".join(doc["tags"])))

        pdf.set_font("body", "", 8.5)
        for label, value in rows:
            pdf.set_text_color(*GREY)
            pdf.cell(30, 5, label)
            pdf.set_text_color(*INK)
            pdf.multi_cell(width - 30, 5, value)
        pdf.ln(4)

        # ---- summary -----------------------------------------------------
        heading("Summary")
        pdf.set_font("body", "", 10)
        pdf.set_text_color(*INK)
        pdf.multi_cell(width, 5.4, summary.get("overview") or "(no summary)")
        pdf.ln(2)

        for title, items, bullet in (
            ("Key points", summary.get("key_points"), "• "),
            ("Action items", summary.get("action_items"), "□ "),
            ("Questions raised", summary.get("questions"), "? "),
        ):
            if not items:
                continue
            pdf.set_font("body", "B", 8.5)
            pdf.cell(0, 5, title.upper(), new_x="LMARGIN", new_y="NEXT")
            pdf.set_font("body", "", 9.5)
            for item in items:
                pdf.multi_cell(width, 5, f"{bullet}{item}")
            pdf.ln(1)

        # ---- transcript --------------------------------------------------
        def write_turns(items, is_rtl: bool):
            turns = []
            for seg in items:
                prev = turns[-1] if turns else None
                if prev and prev["speaker"] == seg.get("speaker") and \
                        float(seg.get("start", 0)) - prev["end"] < 30:
                    prev["end"] = float(seg.get("end", 0))
                    prev["text"] += " " + str(seg.get("text", ""))
                else:
                    turns.append({"speaker": seg.get("speaker"),
                                  "start": float(seg.get("start", 0)),
                                  "end": float(seg.get("end", 0)),
                                  "text": str(seg.get("text", ""))})

            for turn in turns:
                who = labels.get(turn["speaker"], turn["speaker"] or "")
                pdf.set_font("body", "B", 7.5)
                pdf.set_text_color(*GREY)
                pdf.cell(0, 4.5, f"{textout.hms(turn['start'])}   {str(who).upper()}",
                         new_x="LMARGIN", new_y="NEXT")
                pdf.set_text_color(*INK)
                text = turn["text"].strip()
                if is_rtl:
                    pdf.set_font("arabic" if arabic != latin else "body", "", 11)
                    pdf.multi_cell(width, 6, _shape_rtl(text), align="R")
                else:
                    pdf.set_font("body", "", 10)
                    pdf.multi_cell(width, 5.4, text)
                pdf.ln(1.5)

        if translation:
            pdf.add_page()
            heading("Transcript - English translation")
            pdf.set_font("body", "", 8)
            pdf.set_text_color(*GREY)
            pdf.multi_cell(width, 4.5,
                           f"Machine translation from {lang}. "
                           "Check anything that matters against the original.")
            pdf.ln(2)
            write_turns(translation, False)

            pdf.add_page()
            heading(f"Transcript - original ({lang})")
            write_turns(segments, rtl)
        else:
            pdf.add_page()
            heading("Transcript")
            write_turns(segments, rtl)

        out = pdf.output()
        return bytes(out) if out else None
    except Exception as exc:  # a broken PDF must never break a transcription
        print(f"[pdf] generation failed: {type(exc).__name__}: {exc}", flush=True)
        return None
