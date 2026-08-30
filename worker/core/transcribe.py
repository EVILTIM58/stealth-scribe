"""Whisper transcription via faster-whisper (CTranslate2).

Runs locally on your GPU if one is available, otherwise CPU.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Callable, List, Optional

import numpy as np

from .audio import SAMPLE_RATE

MODEL_SIZES = ["tiny", "base", "small", "medium", "large-v3"]

# Rough VRAM / speed guidance surfaced in the GUI.
MODEL_NOTES = {
    "tiny": "fastest, roughest accuracy",
    "base": "fast, ok for clear speech",
    "small": "good balance",
    "medium": "recommended -- accurate, needs ~5 GB VRAM",
    "large-v3": "best accuracy, needs ~10 GB VRAM",
}


@dataclass
class Word:
    start: float
    end: float
    text: str
    speaker: Optional[str] = None


@dataclass
class Segment:
    start: float
    end: float
    text: str
    words: List[Word] = field(default_factory=list)
    speaker: Optional[str] = None


@dataclass
class TranscriptResult:
    segments: List[Segment]
    language: str
    language_probability: float
    duration: float
    model_size: str
    device: str
    task: str = "transcribe"


_MODEL_CACHE: dict = {}


def _prepare_windows_cuda() -> None:
    """ctranslate2 needs cuBLAS/cuDNN DLLs; torch ships them. Put them on the
    DLL search path so GPU transcription works without a manual CUDA install."""
    if os.name != "nt":
        return
    try:
        import torch

        for sub in ("lib",):
            libdir = os.path.join(os.path.dirname(torch.__file__), sub)
            if os.path.isdir(libdir):
                os.add_dll_directory(libdir)
    except Exception:
        pass
    try:
        import nvidia  # noqa: F401  (pip-installed CUDA runtime wheels)

        base = os.path.dirname(nvidia.__file__)
        for root, dirs, _files in os.walk(base):
            if os.path.basename(root) == "bin":
                try:
                    os.add_dll_directory(root)
                except Exception:
                    pass
    except Exception:
        pass


def detect_device(preference: str = "auto") -> str:
    """Return 'cuda' or 'cpu'."""
    if preference in ("cuda", "cpu"):
        return preference
    try:
        import torch

        if torch.cuda.is_available():
            return "cuda"
    except Exception:
        pass
    try:
        import ctranslate2

        if ctranslate2.get_cuda_device_count() > 0:
            return "cuda"
    except Exception:
        pass
    return "cpu"


def gpu_name() -> Optional[str]:
    try:
        import torch

        if torch.cuda.is_available():
            return torch.cuda.get_device_name(0)
    except Exception:
        pass
    return None


def load_model(model_size: str, device: str, log: Callable[[str], None] = print):
    """Load (and cache) a Whisper model. Falls back to CPU if CUDA fails."""
    _prepare_windows_cuda()
    compute_type = "float16" if device == "cuda" else "int8"
    key = (model_size, device, compute_type)
    if key in _MODEL_CACHE:
        return _MODEL_CACHE[key], device

    from faster_whisper import WhisperModel

    try:
        log(f"Loading Whisper '{model_size}' on {device.upper()}...")
        model = WhisperModel(model_size, device=device, compute_type=compute_type)
    except Exception as exc:
        if device == "cuda":
            log(f"GPU unavailable ({type(exc).__name__}), falling back to CPU.")
            device, compute_type = "cpu", "int8"
            key = (model_size, device, compute_type)
            if key in _MODEL_CACHE:
                return _MODEL_CACHE[key], device
            model = WhisperModel(model_size, device=device, compute_type=compute_type)
        else:
            raise

    _MODEL_CACHE[key] = model
    return model, device


def transcribe(
    audio: np.ndarray,
    model_size: str = "medium",
    device_preference: str = "auto",
    language: Optional[str] = None,
    task: str = "transcribe",
    log: Callable[[str], None] = print,
    progress: Optional[Callable[[float], None]] = None,
    should_cancel: Optional[Callable[[], bool]] = None,
) -> TranscriptResult:
    """task="transcribe" writes what was said in its own language.
    task="translate" is Whisper's native any-language-to-ENGLISH mode -- the
    same model, one decoder flag, no separate translation system."""
    device = detect_device(device_preference)
    model, device = load_model(model_size, device, log)

    total = float(audio.size) / SAMPLE_RATE
    verb = "Translating" if task == "translate" else "Transcribing"
    log(f"{verb} {_hms(total)} of audio...")

    segments_iter, info = model.transcribe(
        audio,
        language=language,
        task=task,
        beam_size=5,
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 500},
        word_timestamps=True,
        condition_on_previous_text=False,
    )

    segments: List[Segment] = []
    for seg in segments_iter:
        if should_cancel and should_cancel():
            log("Cancelled.")
            break
        words = [
            Word(start=float(w.start), end=float(w.end), text=w.word)
            for w in (seg.words or [])
            if w.start is not None and w.end is not None
        ]
        text = seg.text.strip()
        if not text:
            continue
        segments.append(
            Segment(start=float(seg.start), end=float(seg.end), text=text, words=words)
        )
        if progress and total > 0:
            progress(min(1.0, float(seg.end) / total))

    log(f"{'Translated' if task == 'translate' else 'Transcribed'} "
        f"{len(segments)} segments.")
    return TranscriptResult(
        segments=segments,
        language=getattr(info, "language", language or "unknown"),
        language_probability=float(getattr(info, "language_probability", 0.0) or 0.0),
        duration=total,
        model_size=model_size,
        device=device,
        task=task,
    )


def _hms(seconds: float) -> str:
    seconds = int(round(seconds))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h:d}:{m:02d}:{s:02d}" if h else f"{m:d}:{s:02d}"
