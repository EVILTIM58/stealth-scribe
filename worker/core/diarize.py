"""Speaker diarization -- figuring out who spoke when.

Primary engine: pyannote.audio 3.1 (accurate, needs a free Hugging Face token).
Fallback engine: a lightweight built-in clusterer that needs no token or extra
downloads. The fallback is approximate -- it is there so the app still labels
speakers out of the box, but pyannote is what you want for real conversations.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple

import numpy as np

from .audio import SAMPLE_RATE
from .transcribe import Segment


@dataclass
class SpeakerTurn:
    start: float
    end: float
    speaker: str


# --------------------------------------------------------------------------
# pyannote
# --------------------------------------------------------------------------


def diarize_pyannote(
    audio: np.ndarray,
    hf_token: str,
    num_speakers: Optional[int] = None,
    device_preference: str = "auto",
    log: Callable[[str], None] = print,
) -> List[SpeakerTurn]:
    import torch
    from pyannote.audio import Pipeline

    log("Loading speaker model (pyannote 3.1)...")
    pipeline = Pipeline.from_pretrained(
        "pyannote/speaker-diarization-3.1", use_auth_token=hf_token
    )
    if pipeline is None:
        raise RuntimeError(
            "pyannote returned no pipeline. This usually means the token is "
            "invalid, or you have not accepted the model's user conditions at "
            "huggingface.co/pyannote/speaker-diarization-3.1"
        )

    use_cuda = device_preference != "cpu" and torch.cuda.is_available()
    if use_cuda:
        pipeline.to(torch.device("cuda"))

    waveform = torch.from_numpy(np.asarray(audio, dtype=np.float32)).unsqueeze(0)
    kwargs = {}
    if num_speakers:
        kwargs["num_speakers"] = int(num_speakers)

    log("Detecting speakers...")
    annotation = pipeline({"waveform": waveform, "sample_rate": SAMPLE_RATE}, **kwargs)

    turns = [
        SpeakerTurn(start=float(seg.start), end=float(seg.end), speaker=str(label))
        for seg, _track, label in annotation.itertracks(yield_label=True)
    ]
    turns.sort(key=lambda t: t.start)
    return turns


# --------------------------------------------------------------------------
# Built-in fallback clusterer (numpy only)
# --------------------------------------------------------------------------


def diarize_builtin(
    audio: np.ndarray,
    segments: List[Segment],
    num_speakers: Optional[int] = None,
    log: Callable[[str], None] = print,
) -> List[SpeakerTurn]:
    """Cluster transcript segments by voice timbre using log-mel statistics.

    Approximate: works reasonably for two clearly different voices in a clean
    recording, struggles with similar voices, crosstalk or noise.
    """
    if not segments:
        return []

    log("Detecting speakers (built-in, approximate)...")
    feats, usable = [], []
    for i, seg in enumerate(segments):
        vec = _segment_embedding(audio, seg.start, seg.end)
        if vec is not None:
            feats.append(vec)
            usable.append(i)

    if len(feats) < 2:
        return [SpeakerTurn(s.start, s.end, "SPEAKER_00") for s in segments]

    X = np.vstack(feats)
    X = (X - X.mean(axis=0)) / (X.std(axis=0) + 1e-8)
    X /= np.linalg.norm(X, axis=1, keepdims=True) + 1e-8

    labels, k = _agglomerative(X, num_speakers)
    log(f"Built-in detector found {k} probable speaker(s).")

    label_by_index = {seg_i: int(lab) for seg_i, lab in zip(usable, labels)}
    turns: List[SpeakerTurn] = []
    last = 0
    for i, seg in enumerate(segments):
        lab = label_by_index.get(i, last)
        last = lab
        turns.append(SpeakerTurn(seg.start, seg.end, f"SPEAKER_{lab:02d}"))
    return turns


def _segment_embedding(audio: np.ndarray, start: float, end: float) -> Optional[np.ndarray]:
    a, b = int(start * SAMPLE_RATE), int(end * SAMPLE_RATE)
    a = max(0, a)
    b = min(audio.size, b)
    if b - a < SAMPLE_RATE // 2:  # need at least 0.5 s
        return None
    clip = audio[a:b]

    frame, hop = 400, 160  # 25 ms / 10 ms at 16 kHz
    n_frames = 1 + (clip.size - frame) // hop
    if n_frames < 5:
        return None
    idx = np.arange(frame)[None, :] + hop * np.arange(n_frames)[:, None]
    frames = clip[idx] * np.hanning(frame)[None, :]

    spec = np.abs(np.fft.rfft(frames, n=512, axis=1)) ** 2
    mel = spec @ _mel_filterbank(n_mels=26, n_fft=512, sr=SAMPLE_RATE).T
    logmel = np.log(mel + 1e-10)

    # Cepstral-ish compression, then per-segment statistics.
    dct = _dct_matrix(13, logmel.shape[1])
    cep = logmel @ dct.T
    return np.concatenate([cep.mean(axis=0), cep.std(axis=0)])


_FB_CACHE: dict = {}


def _mel_filterbank(n_mels: int, n_fft: int, sr: int) -> np.ndarray:
    key = (n_mels, n_fft, sr)
    if key in _FB_CACHE:
        return _FB_CACHE[key]

    def hz_to_mel(f):
        return 2595.0 * np.log10(1.0 + f / 700.0)

    def mel_to_hz(m):
        return 700.0 * (10 ** (m / 2595.0) - 1.0)

    low, high = hz_to_mel(60.0), hz_to_mel(sr / 2.0)
    pts = mel_to_hz(np.linspace(low, high, n_mels + 2))
    bins = np.floor((n_fft + 1) * pts / sr).astype(int)
    fb = np.zeros((n_mels, n_fft // 2 + 1), dtype=np.float32)
    for i in range(n_mels):
        l, c, r = bins[i], bins[i + 1], bins[i + 2]
        if c == l:
            c = l + 1
        if r == c:
            r = c + 1
        r = min(r, fb.shape[1] - 1)
        c = min(c, r)
        for j in range(l, c):
            fb[i, j] = (j - l) / max(1, (c - l))
        for j in range(c, r):
            fb[i, j] = (r - j) / max(1, (r - c))
    _FB_CACHE[key] = fb
    return fb


_DCT_CACHE: dict = {}


def _dct_matrix(n_out: int, n_in: int) -> np.ndarray:
    key = (n_out, n_in)
    if key in _DCT_CACHE:
        return _DCT_CACHE[key]
    n = np.arange(n_in)
    k = np.arange(n_out)[:, None]
    m = np.cos(np.pi * k * (2 * n + 1) / (2 * n_in)) * np.sqrt(2.0 / n_in)
    _DCT_CACHE[key] = m
    return m


def _agglomerative(X: np.ndarray, num_speakers: Optional[int]) -> Tuple[np.ndarray, int]:
    """Average-linkage clustering on cosine distance."""
    n = X.shape[0]
    sim = X @ X.T
    dist = 1.0 - sim
    np.fill_diagonal(dist, 0.0)

    clusters = {i: [i] for i in range(n)}
    merge_distances: List[float] = []
    history: List[dict] = [{i: [i] for i in range(n)}]

    while len(clusters) > 1:
        keys = list(clusters)
        best, best_d = None, np.inf
        for i in range(len(keys)):
            for j in range(i + 1, len(keys)):
                a, b = clusters[keys[i]], clusters[keys[j]]
                d = dist[np.ix_(a, b)].mean()
                if d < best_d:
                    best_d, best = d, (keys[i], keys[j])
        ka, kb = best
        clusters[ka] = clusters[ka] + clusters[kb]
        del clusters[kb]
        merge_distances.append(best_d)
        history.append({k: list(v) for k, v in clusters.items()})

    if num_speakers:
        k = max(1, min(int(num_speakers), n))
    else:
        # Largest jump in merge distance = natural number of speakers, capped
        # at 6 and biased toward few speakers.
        k = 1
        if len(merge_distances) >= 2:
            d = np.array(merge_distances)
            jumps = np.diff(d)
            if jumps.size:
                # index of biggest jump -> clusters remaining after that merge
                cut = int(np.argmax(jumps))
                k = max(1, min(6, n - cut - 1))
                if d[-1] < 0.35:  # everything is close together: one voice
                    k = 1
    snapshot = history[n - k]
    labels = np.zeros(n, dtype=int)
    for new_label, members in enumerate(snapshot.values()):
        for m in members:
            labels[m] = new_label
    return labels, k


# --------------------------------------------------------------------------
# Applying speaker turns to the transcript
# --------------------------------------------------------------------------


def assign_speakers(segments: List[Segment], turns: List[SpeakerTurn]) -> List[Segment]:
    """Attach a speaker to every word, then re-cut segments where the speaker
    changes mid-sentence. Returns new segments in chronological order."""
    if not turns:
        return segments

    for seg in segments:
        if seg.words:
            for w in seg.words:
                w.speaker = _best_speaker(w.start, w.end, turns)
            seg.speaker = _majority([w.speaker for w in seg.words])
        else:
            seg.speaker = _best_speaker(seg.start, seg.end, turns)

    out: List[Segment] = []
    for seg in segments:
        if not seg.words:
            out.append(seg)
            continue
        current: List = []
        current_spk = seg.words[0].speaker
        for w in seg.words:
            if w.speaker != current_spk and current:
                out.append(_segment_from_words(current, current_spk))
                current, current_spk = [], w.speaker
            current.append(w)
        if current:
            out.append(_segment_from_words(current, current_spk))

    out.sort(key=lambda s: s.start)
    return _drop_stray_turns(out)


def _segment_from_words(words: List, speaker: Optional[str]) -> Segment:
    text = "".join(w.text for w in words).strip()
    return Segment(
        start=words[0].start, end=words[-1].end, text=text, words=list(words), speaker=speaker
    )


def _drop_stray_turns(segments: List[Segment]) -> List[Segment]:
    """A single short word attributed to another speaker between two long turns
    of the same speaker is almost always an error -- absorb it."""
    if len(segments) < 3:
        return segments
    for i in range(1, len(segments) - 1):
        prev, cur, nxt = segments[i - 1], segments[i], segments[i + 1]
        short = (cur.end - cur.start) < 0.8 and len(cur.text.split()) <= 2
        if short and prev.speaker == nxt.speaker and cur.speaker != prev.speaker:
            cur.speaker = prev.speaker
    return segments


def _best_speaker(start: float, end: float, turns: List[SpeakerTurn]) -> Optional[str]:
    best, best_overlap = None, 0.0
    for t in turns:
        overlap = min(end, t.end) - max(start, t.start)
        if overlap > best_overlap:
            best_overlap, best = overlap, t.speaker
    if best is None:  # no overlap: snap to nearest turn
        nearest, nearest_gap = None, np.inf
        mid = (start + end) / 2.0
        for t in turns:
            gap = 0.0 if t.start <= mid <= t.end else min(abs(mid - t.start), abs(mid - t.end))
            if gap < nearest_gap:
                nearest_gap, nearest = gap, t.speaker
        return nearest
    return best


def _majority(labels: List[Optional[str]]) -> Optional[str]:
    counts: dict = {}
    for l in labels:
        if l:
            counts[l] = counts.get(l, 0) + 1
    return max(counts, key=counts.get) if counts else None


def friendly_labels(segments: List[Segment]) -> dict:
    """Map raw pyannote labels to 'Voice 1', 'Voice 2'... in order of first
    appearance, so the transcript reads naturally."""
    mapping: dict = {}
    for seg in segments:
        if seg.speaker and seg.speaker not in mapping:
            mapping[seg.speaker] = f"Voice {len(mapping) + 1}"
    return mapping
