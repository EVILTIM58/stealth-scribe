"""Voice identification: matching a recording's voiceprints against the
people this user has already named.

Pure Python and pure functions on purpose. The backend has no numpy, this is
the highest-risk logic in the app (attaching a name to the wrong person), and
pure functions are the part I can actually test without a running server.

The unit everywhere is COSINE SIMILARITY of L2-normalised vectors:
   1.0  = identical direction
   0.0  = unrelated
  -1.0  = opposite
"""

from __future__ import annotations

import math
import os
from typing import Dict, List, Optional, Sequence, Tuple

# Thresholds for the pyannote engine, deliberately conservative: a wrong name
# silently attached to a stranger's voice is far worse than asking the user to
# confirm one extra time.
#
# For reference, pyannote/embedding cosine similarity typically lands around
# 0.7-0.9 for the same person and below 0.5 for different people. Every voice,
# microphone and room shifts that, so both are env-tunable -- raise
# VOICEID_AUTO if you ever see a wrong auto-assignment, lower it if you find
# yourself confirming the same person constantly.
AUTO_ASSIGN = float(os.environ.get("VOICEID_AUTO", "0.75"))
SUGGEST = float(os.environ.get("VOICEID_SUGGEST", "0.58"))

# The built-in fallback engine is far weaker. It may suggest, never decide.
BUILTIN_SUGGEST = float(os.environ.get("VOICEID_BUILTIN_SUGGEST", "0.88"))
BUILTIN_AUTO = 2.0   # unreachable by design: cosine can never exceed 1.0

MIN_DIMS = 8


def normalise(vec: Sequence[float]) -> List[float]:
    norm = math.sqrt(sum(float(v) * float(v) for v in vec))
    if norm <= 0:
        return [0.0] * len(vec)
    return [float(v) / norm for v in vec]


def similarity(a: Sequence[float], b: Sequence[float]) -> float:
    """Cosine similarity. Returns -1.0 for anything unusable, which can never
    clear a threshold, so bad input fails closed rather than matching."""
    if not a or not b or len(a) != len(b) or len(a) < MIN_DIMS:
        return -1.0
    dot = sum(float(x) * float(y) for x, y in zip(a, b))
    na = math.sqrt(sum(float(x) * float(x) for x in a))
    nb = math.sqrt(sum(float(y) * float(y) for y in b))
    if na <= 0 or nb <= 0:
        return -1.0
    return max(-1.0, min(1.0, dot / (na * nb)))


def thresholds(engine: str) -> Tuple[float, float]:
    """(auto_assign, suggest) for the engine that produced the vectors."""
    if engine == "pyannote":
        return AUTO_ASSIGN, SUGGEST
    return BUILTIN_AUTO, BUILTIN_SUGGEST


def match_one(
    vector: Sequence[float], engine: str, people: List[dict]
) -> Optional[dict]:
    """Best candidate for a single voiceprint, or None.

    `people` are this user's voiceprint documents. Crucially, only those built
    by the SAME engine are considered -- a 26-d cepstral vector and a 512-d
    neural embedding describe different things, and comparing them would
    produce confident nonsense.
    """
    auto_at, suggest_at = thresholds(engine)
    best, best_score = None, -1.0
    runner_up = -1.0

    for person in people:
        if person.get("engine") != engine:
            continue
        score = similarity(vector, person.get("centroid") or [])
        if score > best_score:
            runner_up = best_score
            best, best_score = person, score
        elif score > runner_up:
            runner_up = score

    if best is None or best_score < suggest_at:
        return None

    # If two known people score almost the same, we cannot honestly claim to
    # have told them apart -- demote to a suggestion the human resolves.
    ambiguous = runner_up > 0 and (best_score - runner_up) < 0.05
    return {
        "person_id": best["_id"],
        "name": best.get("name", ""),
        "score": round(best_score, 4),
        "auto": bool(best_score >= auto_at and not ambiguous),
        "ambiguous": ambiguous,
        "runner_up": round(runner_up, 4) if runner_up > 0 else None,
    }


def match_all(
    vectors: Dict[str, Sequence[float]], engine: str, people: List[dict]
) -> Dict[str, dict]:
    """Match every speaker in a recording, ensuring no two speakers in the SAME
    recording are given the same identity.

    Two different people in one conversation cannot both be Tim. Resolve by
    best score first; the loser falls back to a suggestion, or to nothing.
    """
    candidates = []
    for speaker, vec in (vectors or {}).items():
        hit = match_one(vec, engine, people)
        if hit:
            candidates.append((speaker, hit))

    candidates.sort(key=lambda pair: pair[1]["score"], reverse=True)

    taken: Dict[str, str] = {}   # person_id -> speaker that won it
    out: Dict[str, dict] = {}
    for speaker, hit in candidates:
        pid = hit["person_id"]
        if pid in taken:
            # Someone else in this recording is a better fit for that person.
            hit = dict(hit, auto=False, contested_by=taken[pid])
        else:
            taken[pid] = speaker
        out[speaker] = hit
    return out


def updated_centroid(
    centroid: Sequence[float], samples: int, new_vector: Sequence[float]
) -> List[float]:
    """Fold a newly confirmed voiceprint into a person's running average.

    A person's voice varies with microphone, room and mood, so averaging over
    many confirmations is what makes recognition improve with use. Weighted by
    sample count and re-normalised so the centroid stays a unit vector.
    """
    new_vector = list(new_vector or [])
    centroid = list(centroid or [])
    if not new_vector:
        return normalise(centroid)
    if not centroid or len(centroid) != len(new_vector):
        return normalise(new_vector)

    n = max(1, int(samples or 1))
    blended = [(c * n + v) / (n + 1) for c, v in zip(centroid, new_vector)]
    return normalise(blended)


def describe(score: Optional[float], engine: str) -> str:
    """Plain-language confidence for the UI. Never show a bare cosine value to
    a human -- 0.71 means nothing without the threshold beside it."""
    if score is None:
        return "unknown voice"
    auto_at, suggest_at = thresholds(engine)
    if score >= auto_at:
        return "confident match"
    if score >= (auto_at + suggest_at) / 2:
        return "probable match"
    if score >= suggest_at:
        return "possible match"
    return "unknown voice"
