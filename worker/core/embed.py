"""Voiceprints — a fixed-length vector describing what a voice sounds like.

Two engines, and they are NOT interchangeable:

  * "pyannote"  — a real speaker-recognition neural net (512-d). Accurate enough
                  to recognise the same person across different recordings,
                  microphones and rooms. Needs the Hugging Face token.
  * "builtin"   — averaged cepstral statistics (26-d). No token, no download.
                  Usable for telling two voices apart *inside one recording*,
                  far too weak to identify someone across recordings.

Embeddings from the two engines are meaningless to compare, so every vector is
stamped with the engine that produced it and the server refuses to match across
them. Getting that wrong would silently attach the wrong name to a stranger.
"""

from __future__ import annotations

import math
from typing import Callable, Dict, List, Optional

import numpy as np

from .audio import SAMPLE_RATE
from .diarize import _segment_embedding  # cepstral stats, the fallback engine

# How much of a speaker's audio to feed the model. More is better, with
# diminishing returns; 60s is plenty and keeps memory flat on long recordings.
MAX_SECONDS = 60.0
MIN_SECONDS = 3.0

_PIPELINE_CACHE: dict = {}


def _l2(vec: List[float]) -> List[float]:
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def collect_speaker_audio(
    audio: np.ndarray, segments, speaker: str, max_seconds: float = MAX_SECONDS
) -> Optional[np.ndarray]:
    """Concatenate this speaker's longest turns into one clip.

    Longest-first matters: short interjections ("yeah", "mhm") carry little
    speaker identity and a lot of noise.
    """
    spans = [(s.end - s.start, s.start, s.end) for s in segments if s.speaker == speaker]
    if not spans:
        return None
    spans.sort(reverse=True)

    pieces, total = [], 0.0
    for dur, start, end in spans:
        if total >= max_seconds:
            break
        a = max(0, int(start * SAMPLE_RATE))
        b = min(audio.size, int(end * SAMPLE_RATE))
        if b - a < int(0.4 * SAMPLE_RATE):
            continue
        take = min(b - a, int((max_seconds - total) * SAMPLE_RATE))
        pieces.append(audio[a:a + take])
        total += take / SAMPLE_RATE

    if total < MIN_SECONDS or not pieces:
        return None
    return np.concatenate(pieces)


def _pyannote_embedder(hf_token: str, device_preference: str, log: Callable[[str], None]):
    key = ("pyannote", device_preference)
    if key in _PIPELINE_CACHE:
        return _PIPELINE_CACHE[key]

    import torch
    from pyannote.audio import Inference, Model

    log("  loading voiceprint model (pyannote/embedding)...")
    model = Model.from_pretrained("pyannote/embedding", use_auth_token=hf_token)
    if device_preference != "cpu" and torch.cuda.is_available():
        model.to(torch.device("cuda"))
    # window="whole" -> one vector for the entire clip we hand it.
    inference = Inference(model, window="whole")
    _PIPELINE_CACHE[key] = inference
    return inference


def extract(
    audio: np.ndarray,
    segments,
    speakers: List[str],
    hf_token: str = "",
    device_preference: str = "auto",
    log: Callable[[str], None] = print,
) -> Dict[str, object]:
    """Return {"engine": str, "vectors": {speaker: [floats]}}.

    Never raises -- a failure here must not lose a transcript that already
    succeeded. Worst case it returns no vectors and the recording simply has no
    voiceprints attached.
    """
    vectors: Dict[str, List[float]] = {}
    engine = "none"

    if not speakers:
        return {"engine": engine, "vectors": vectors}

    if hf_token:
        try:
            import torch

            inference = _pyannote_embedder(hf_token, device_preference, log)
            for spk in speakers:
                clip = collect_speaker_audio(audio, segments, spk)
                if clip is None:
                    continue
                waveform = torch.from_numpy(np.asarray(clip, dtype=np.float32)).unsqueeze(0)
                vec = inference({"waveform": waveform, "sample_rate": SAMPLE_RATE})
                vectors[spk] = _l2([float(x) for x in np.asarray(vec).reshape(-1)])
            if vectors:
                engine = "pyannote"
                log(f"  voiceprints: {len(vectors)} captured (pyannote)")
                return {"engine": engine, "vectors": vectors}
        except Exception as exc:
            log(f"  voiceprint model unavailable ({exc}); using the weak fallback")

    # Fallback: mean of the per-segment cepstral statistics we already compute
    # for the built-in diarizer. Good enough to group, not to identify.
    try:
        for spk in speakers:
            stats = []
            for seg in segments:
                if seg.speaker != spk:
                    continue
                vec = _segment_embedding(audio, seg.start, seg.end)
                if vec is not None:
                    stats.append(vec)
            if stats:
                mean = np.mean(np.vstack(stats), axis=0)
                vectors[spk] = _l2([float(x) for x in mean])
        if vectors:
            engine = "builtin"
            log(f"  voiceprints: {len(vectors)} captured (built-in, weak)")
    except Exception as exc:
        log(f"  voiceprint extraction failed entirely ({exc})")

    return {"engine": engine, "vectors": vectors}
