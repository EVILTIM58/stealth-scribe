"""Renders a stored recording into the plain-text transcript file."""

from __future__ import annotations

import datetime as dt
import textwrap
from typing import Dict, List, Optional

WIDTH = 88
RULE = "=" * WIDTH
THIN = "-" * WIDTH


def hms(seconds: float) -> str:
    seconds = max(0, int(round(seconds or 0)))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def _stamp(when: Optional[dt.datetime]) -> str:
    if not when:
        return "unknown"
    return when.strftime("%A, %B %d, %Y at %I:%M %p").replace(" 0", " ")


def _as_dt(value) -> Optional[dt.datetime]:
    if isinstance(value, dt.datetime):
        return value
    if isinstance(value, str):
        try:
            return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def speaker_name(doc: dict, raw: Optional[str]) -> str:
    if not raw:
        return ""
    labels = doc.get("speaker_labels") or {}
    return labels.get(raw) or raw.replace("SPEAKER_", "Voice ").lstrip("0") or raw


def speaking_time(doc: dict) -> List[tuple]:
    totals: Dict[str, float] = {}
    for seg in doc.get("segments") or []:
        name = speaker_name(doc, seg.get("speaker")) or "Speaker"
        totals[name] = totals.get(name, 0.0) + max(
            0.0, float(seg.get("end", 0)) - float(seg.get("start", 0))
        )
    grand = sum(totals.values()) or 1.0
    return sorted(
        ((n, s, 100.0 * s / grand) for n, s in totals.items()), key=lambda r: r[1], reverse=True
    )


def render(doc: dict) -> str:
    segments = doc.get("segments") or []
    summary = doc.get("summary") or {}
    recorded_at = _as_dt(doc.get("recorded_at"))
    created_at = _as_dt(doc.get("created_at"))
    finished_at = _as_dt(doc.get("finished_at")) or dt.datetime.now()
    engine = doc.get("engine") or {}
    show_ts = bool(doc.get("show_timestamps", True))
    talkers = speaking_time(doc)

    L: List[str] = []
    A = L.append

    A(RULE)
    A("STEALTH-SCRIBE  --  SMART TRANSCRIPTION".center(WIDTH))
    A(RULE)
    A("")
    A(f"  Title          : {doc.get('title') or doc.get('original_name', '')}")
    A(f"  Recording      : {doc.get('original_name', '')}")
    A(
        "  Source type    : "
        + ("Video (audio track transcribed)" if doc.get("kind") == "video" else "Audio")
    )
    A(f"  Recorded       : {_stamp(recorded_at)}")
    A(f"  Uploaded       : {_stamp(created_at)}")
    A(f"  Transcribed    : {_stamp(finished_at)}")
    A(f"  Duration       : {hms(doc.get('duration_sec', 0))}")
    A(f"  Speakers       : {len(talkers) if talkers else 1}")
    A(f"  Words          : {int(doc.get('word_count') or 0):,}")
    lang = doc.get("language", "unknown")
    lang_name = doc.get("language_name") or lang
    conf = float(doc.get("language_probability") or 0) * 100
    A(f"  Language       : {lang_name}"
      + (f" [{lang}]" if lang_name != lang else "")
      + (f" ({conf:.0f}% confident)" if conf else ""))
    if doc.get("translation"):
        A(f"  Translation    : {lang_name} -> English (Whisper)")
    if doc.get("folder"):
        A(f"  Folder         : {doc['folder']}")
    if doc.get("tags"):
        A(f"  Tags           : {', '.join(doc['tags'])}")
    A(
        "  Engine         : "
        + f"Whisper {engine.get('model', '?')} on {str(engine.get('device', '?')).upper()}"
        + f" | speakers: {engine.get('diarizer', 'n/a')}"
        + f" | summary: {summary.get('source', 'offline')}"
        + (f" | worker: {engine['worker']}" if engine.get("worker") else "")
    )
    A("")

    if doc.get("notes"):
        A(THIN)
        A("YOUR NOTES")
        A(THIN)
        A("")
        for line in str(doc["notes"]).splitlines():
            A(textwrap.fill(line, WIDTH - 2, initial_indent="  ", subsequent_indent="  ")
              if line.strip() else "")
        A("")

    A(THIN)
    A("SUMMARY")
    A(THIN)
    A("")
    for para in (summary.get("overview") or "(no summary)").split("\n"):
        A(textwrap.fill(para.strip(), WIDTH - 2, initial_indent="  ", subsequent_indent="  "))
    A("")

    for header, items, bullet, indent in (
        ("KEY POINTS", summary.get("key_points"), "  - ", "    "),
        ("ACTION ITEMS", summary.get("action_items"), "  [ ] ", "      "),
        ("OPEN QUESTIONS RAISED", summary.get("questions"), "  ? ", "    "),
    ):
        if items:
            A(header)
            A("")
            for item in items:
                A(textwrap.fill(str(item), WIDTH - len(bullet) - 2,
                                initial_indent=bullet, subsequent_indent=indent))
            A("")

    if summary.get("topics"):
        A("FREQUENT TOPICS")
        A("")
        A(textwrap.fill(", ".join(summary["topics"]), WIDTH - 2,
                        initial_indent="  ", subsequent_indent="  "))
        A("")

    if len(talkers) > 1:
        A("SPEAKING TIME")
        A("")
        for name, secs, pct in talkers:
            A(f"  {name:<14} {hms(secs)}  {pct:5.1f}%  {'#' * int(round(pct / 4))}")
        A("")

    translation = doc.get("translation") or []
    if translation:
        lang_name = doc.get("language_name") or doc.get("language", "the original")
        A(THIN)
        A("FULL TRANSCRIPT  --  ENGLISH TRANSLATION")
        A(THIN)
        A("")
        A(f"  Translated from {lang_name} by Whisper. Machine translation:")
        A("  check anything that matters against the original below.")
        A("")
        A(render_transcript(doc, translation, recorded_at, show_ts))
        A("")
        A(THIN)
        A(f"FULL TRANSCRIPT  --  ORIGINAL ({str(lang_name).upper()})")
        A(THIN)
        A("")
        A(render_transcript(doc, segments, recorded_at, show_ts))
    else:
        A(THIN)
        A("FULL TRANSCRIPT")
        A(THIN)
        A("")
        A(render_transcript(doc, segments, recorded_at, show_ts))
    A("")
    A(THIN)
    A(f"  Generated by Stealth-Scribe on {_stamp(dt.datetime.now())}")
    A(THIN)

    return "\n".join(L) + "\n"


def render_transcript(
    doc: dict, segments: List[dict], recorded_at: Optional[dt.datetime], show_ts: bool
) -> str:
    if not segments:
        return "  (No speech detected.)"

    lines: List[str] = []
    buffer: List[str] = []
    current = object()
    block_start = 0.0

    def flush():
        if not buffer:
            return
        text = " ".join(b.strip() for b in buffer).strip()
        if not text:
            return
        bits = []
        if show_ts:
            bits.append(f"[{hms(block_start)}]")
            if recorded_at:
                # Round the same way hms() does so the two stamps never disagree.
                clock = recorded_at + dt.timedelta(seconds=round(block_start))
                bits.append(f"({clock.strftime('%I:%M:%S %p').lstrip('0')})")
        name = speaker_name(doc, current if isinstance(current, str) else None)
        if name:
            bits.append(f"{name}:")
        header = " ".join(b for b in bits if b).strip()
        if header:
            lines.append(header)
        lines.append(textwrap.fill(text, WIDTH - 4, initial_indent="    ",
                                   subsequent_indent="    "))
        lines.append("")

    for seg in segments:
        spk = seg.get("speaker") or ""
        if spk != current:
            flush()
            buffer = []
            current = spk
            block_start = float(seg.get("start") or 0.0)
        buffer.append(str(seg.get("text") or ""))
    flush()
    return "\n".join(lines).rstrip()


def plain_transcript(doc: dict) -> str:
    """Speaker-prefixed transcript with no decoration (used for AI summaries).
    Prefers the English translation when one exists."""
    out = []
    for seg in (doc.get("translation") or doc.get("segments") or []):
        name = speaker_name(doc, seg.get("speaker"))
        out.append(f"{name}: {seg.get('text','')}" if name else str(seg.get("text", "")))
    return "\n".join(out)
