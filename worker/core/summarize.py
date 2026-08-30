"""Summarization.

Two modes:
  * offline  -- extractive summary + key points + action items, pure Python,
                no network, no API key. Always available.
  * ai       -- if you paste an Anthropic or OpenAI API key in Settings, the
                transcript is sent to that model for a proper written summary.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Callable, List, Optional

STOPWORDS = set(
    """a about above after again against all am an and any are aren't as at be because been
before being below between both but by can cannot could couldn't did didn't do does doesn't
doing don't down during each few for from further had hadn't has hasn't have haven't having he
he'd he'll he's her here here's hers herself him himself his how how's i i'd i'll i'm i've if
in into is isn't it it's its itself let's me more most mustn't my myself no nor not of off on
once only or other ought our ours ourselves out over own same shan't she she'd she'll she's
should shouldn't so some such than that that's the their theirs them themselves then there
there's these they they'd they'll they're they've this those through to too under until up very
was wasn't we we'd we'll we're we've were weren't what what's when when's where where's which
while who who's whom why why's with won't would wouldn't you you'd you'll you're you've your
yours yourself yourselves yeah yes okay ok um uh like just really got get gonna know think
mean right well going say said thing things kind sort actually basically maybe probably
""".split()
)

ACTION_CUES = [
    r"\bi(?:'ll| will)\b",
    r"\bwe(?:'ll| will)\b",
    r"\bwe need to\b",
    r"\bi need to\b",
    r"\byou need to\b",
    r"\bwe should\b",
    r"\bcan you\b",
    r"\bcould you\b",
    r"\blet's\b",
    r"\baction item\b",
    r"\bfollow up\b",
    r"\bfollow-up\b",
    r"\bmake sure\b",
    r"\bdon't forget\b",
    r"\bremind\b",
    r"\bsend (?:me|you|them|over|the)\b",
    r"\bby (?:monday|tuesday|wednesday|thursday|friday|saturday|sunday|tomorrow|next week|end of)\b",
    r"\bdeadline\b",
    r"\bdue\b",
    r"\bschedule\b",
    r"\bset up\b",
    r"\bgoing to (?:call|email|send|check|look|write|order|book|fix)\b",
]
ACTION_RE = re.compile("|".join(ACTION_CUES), re.IGNORECASE)

QUESTION_RE = re.compile(r"\?\s*$")


@dataclass
class Summary:
    overview: str = ""
    key_points: List[str] = field(default_factory=list)
    action_items: List[str] = field(default_factory=list)
    topics: List[str] = field(default_factory=list)
    questions: List[str] = field(default_factory=list)
    source: str = "offline"


# --------------------------------------------------------------------------
# Offline extractive summary
# --------------------------------------------------------------------------


def summarize_offline(text: str, max_sentences: int = 6) -> Summary:
    sentences = split_sentences(text)
    if not sentences:
        return Summary(overview="(No speech detected in this recording.)")

    words_by_sentence = [_words(s) for s in sentences]
    freq: dict = {}
    for ws in words_by_sentence:
        for w in ws:
            freq[w] = freq.get(w, 0) + 1
    if not freq:
        return Summary(overview=" ".join(sentences[:max_sentences]))

    peak = max(freq.values())
    norm = {w: c / peak for w, c in freq.items()}

    scores = []
    n = len(sentences)
    for i, (sent, ws) in enumerate(zip(sentences, words_by_sentence)):
        if not ws:
            scores.append(0.0)
            continue
        base = sum(norm.get(w, 0.0) for w in ws) / (len(ws) ** 0.65)
        # Openings and closings carry disproportionate signal in conversation.
        position = 1.18 if i < n * 0.12 else (1.10 if i > n * 0.88 else 1.0)
        length_penalty = 0.45 if len(ws) < 5 else 1.0
        scores.append(base * position * length_penalty)

    k = max(1, min(max_sentences, max(3, round(n / 5))))
    top = sorted(range(n), key=lambda i: scores[i], reverse=True)[:k]
    overview = " ".join(sentences[i].strip() for i in sorted(top))

    key_points = [
        sentences[i].strip()
        for i in sorted(sorted(range(n), key=lambda i: scores[i], reverse=True)[: k + 4])
        if len(_words(sentences[i])) >= 5
    ][: max_sentences + 2]

    actions, seen = [], set()
    for s in sentences:
        s_clean = s.strip()
        if len(_words(s_clean)) < 4 or QUESTION_RE.search(s_clean):
            continue
        if ACTION_RE.search(s_clean):
            keyv = re.sub(r"\W+", "", s_clean.lower())[:60]
            if keyv not in seen:
                seen.add(keyv)
                actions.append(s_clean)
    actions = actions[:12]

    questions = [
        s.strip()
        for s in sentences
        if QUESTION_RE.search(s.strip()) and len(s.split()) >= 4
    ][:8]

    topics = [
        w for w, _ in sorted(freq.items(), key=lambda kv: kv[1], reverse=True) if len(w) > 3
    ][:12]

    return Summary(
        overview=overview,
        key_points=key_points,
        action_items=actions,
        topics=topics,
        questions=questions,
        source="offline",
    )


def split_sentences(text: str) -> List[str]:
    text = re.sub(r"\s+", " ", text or "").strip()
    if not text:
        return []
    parts = re.split(r"(?<=[.!?])\s+(?=[A-Z0-9\"'])", text)
    out: List[str] = []
    for p in parts:
        p = p.strip()
        if not p:
            continue
        # Whisper sometimes emits very long unpunctuated runs; chop them.
        if len(p.split()) > 60:
            chunk: List[str] = []
            for w in p.split():
                chunk.append(w)
                if len(chunk) >= 35 and w.endswith(","):
                    out.append(" ".join(chunk))
                    chunk = []
            if chunk:
                out.append(" ".join(chunk))
        else:
            out.append(p)
    return out


def _words(sentence: str) -> List[str]:
    return [
        w for w in re.findall(r"[a-z0-9']+", sentence.lower()) if w not in STOPWORDS and len(w) > 2
    ]


# --------------------------------------------------------------------------
# Optional AI summary
# --------------------------------------------------------------------------

PROMPT = """You are summarizing a transcript of a recorded conversation.

Write your response as plain text with these exact section headers and nothing else:

OVERVIEW
A 3-6 sentence plain-English summary of what this recording is about and what happened.

KEY POINTS
- 4 to 8 bullets, each a concrete point actually made in the conversation.

ACTION ITEMS
- Anything someone committed to do, or that was left open. Include who, if named.
- Write "None identified." if there are none.

Do not invent anything that is not in the transcript.

TRANSCRIPT:
"""


def summarize_ai(
    transcript: str,
    provider: str,
    api_key: str,
    model: Optional[str] = None,
    log: Callable[[str], None] = print,
    max_chars: int = 120_000,
) -> Summary:
    body = transcript[:max_chars]
    if len(transcript) > max_chars:
        body += "\n\n[transcript truncated]"

    log(f"Requesting AI summary ({provider})...")
    if provider == "anthropic":
        raw = _call_anthropic(api_key, model or "claude-sonnet-4-5", PROMPT + body)
    elif provider == "openai":
        raw = _call_openai(api_key, model or "gpt-4o-mini", PROMPT + body)
    else:
        raise ValueError(f"Unknown provider: {provider}")

    return _parse_ai_summary(raw)


def _parse_ai_summary(raw: str) -> Summary:
    sections = {"OVERVIEW": [], "KEY POINTS": [], "ACTION ITEMS": []}
    current = None
    for line in raw.splitlines():
        stripped = line.strip()
        upper = stripped.upper().strip(": ")
        if upper in sections:
            current = upper
            continue
        if current and stripped:
            sections[current].append(stripped)

    def bullets(lines: List[str]) -> List[str]:
        out = []
        for l in lines:
            l = re.sub(r"^[-*•]\s*", "", l).strip()
            if l and l.lower() not in ("none identified.", "none identified", "none."):
                out.append(l)
        return out

    overview = " ".join(sections["OVERVIEW"]).strip() or raw.strip()
    return Summary(
        overview=overview,
        key_points=bullets(sections["KEY POINTS"]),
        action_items=bullets(sections["ACTION ITEMS"]),
        source="ai",
    )


def _post_json(url: str, headers: dict, payload: dict, timeout: int = 180) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:400]
        raise RuntimeError(f"API error {e.code}: {detail}") from None
    except urllib.error.URLError as e:
        raise RuntimeError(f"Could not reach the API: {e.reason}") from None


def _call_anthropic(api_key: str, model: str, prompt: str) -> str:
    out = _post_json(
        "https://api.anthropic.com/v1/messages",
        {
            "content-type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
        },
        {
            "model": model,
            "max_tokens": 2000,
            "messages": [{"role": "user", "content": prompt}],
        },
    )
    return "".join(b.get("text", "") for b in out.get("content", []))


def _call_openai(api_key: str, model: str, prompt: str) -> str:
    out = _post_json(
        "https://api.openai.com/v1/chat/completions",
        {"content-type": "application/json", "authorization": f"Bearer {api_key}"},
        {
            "model": model,
            "max_tokens": 2000,
            "messages": [{"role": "user", "content": prompt}],
        },
    )
    return out["choices"][0]["message"]["content"]
