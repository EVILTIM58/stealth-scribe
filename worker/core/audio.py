"""Media loading. Decodes anything faster-whisper's bundled PyAV can read down
to 16 kHz mono float32 -- audio files (mp3, wav, m4a, wma, ogg, flac, aac) and
video files alike (mp4, mov, mkv, avi, wmv...), where the audio track is pulled
out of the container and the video stream is ignored.

No external ffmpeg.exe needed -- PyAV ships its own codecs.
"""

from __future__ import annotations

import os
import wave

import numpy as np

SAMPLE_RATE = 16000


def load_audio(path: str) -> np.ndarray:
    """Return mono float32 samples at 16 kHz, range roughly [-1, 1]."""
    try:
        from faster_whisper.audio import decode_audio

        audio = decode_audio(path, sampling_rate=SAMPLE_RATE)
        return np.asarray(audio, dtype=np.float32)
    except Exception:
        pass

    # Fallback for plain PCM wav files if PyAV is unavailable.
    if path.lower().endswith(".wav"):
        return _load_wav(path)
    raise RuntimeError(
        f"Could not decode {os.path.basename(path)}. The file may be corrupt "
        f"or in an unsupported format."
    )


def _load_wav(path: str) -> np.ndarray:
    with wave.open(path, "rb") as wf:
        n_channels = wf.getnchannels()
        width = wf.getsampwidth()
        rate = wf.getframerate()
        raw = wf.readframes(wf.getnframes())

    if width == 2:
        data = np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0
    elif width == 4:
        data = np.frombuffer(raw, dtype="<i4").astype(np.float32) / 2147483648.0
    elif width == 1:
        data = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    else:
        raise RuntimeError(f"Unsupported WAV sample width: {width} bytes")

    if n_channels > 1:
        data = data.reshape(-1, n_channels).mean(axis=1)

    if rate != SAMPLE_RATE:
        data = _resample(data, rate, SAMPLE_RATE)
    return data.astype(np.float32)


def _resample(data: np.ndarray, src_rate: int, dst_rate: int) -> np.ndarray:
    """Linear resample. Only used by the rarely-hit WAV fallback path."""
    if src_rate == dst_rate or data.size == 0:
        return data
    duration = data.size / float(src_rate)
    n_out = int(round(duration * dst_rate))
    src_idx = np.linspace(0.0, data.size - 1, n_out)
    return np.interp(src_idx, np.arange(data.size), data).astype(np.float32)


def duration_seconds(audio: np.ndarray) -> float:
    return float(audio.size) / SAMPLE_RATE
