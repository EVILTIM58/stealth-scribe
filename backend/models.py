"""Request/response shapes.

Every request body is a Pydantic model with extra='forbid' -- never a bare
dict. A client typo then becomes a loud 422 instead of a silent no-op.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class Strict(BaseModel):
    model_config = {"extra": "forbid"}


class UploadInit(Strict):
    filename: str
    size: int = 0
    total_chunks: int = 1
    mime: str = ""  # what the browser says it is; beats guessing from extension
    folder: str = ""
    tags: List[str] = Field(default_factory=list)
    title: str = ""
    recorded_at: Optional[str] = None


class UploadComplete(Strict):
    folder: str = ""
    tags: List[str] = Field(default_factory=list)
    title: str = ""
    notes: str = ""
    recorded_at: Optional[str] = None


class RecordingPatch(Strict):
    title: Optional[str] = None
    folder: Optional[str] = None
    tags: Optional[List[str]] = None
    notes: Optional[str] = None
    recorded_at: Optional[str] = None


class SpeakerRename(Strict):
    labels: Dict[str, str]  # {"SPEAKER_00": "Tim", ...}


class SettingsPatch(Strict):
    model_size: Optional[str] = None
    translate: Optional[str] = None   # off | auto | always
    language: Optional[str] = None
    speaker_mode: Optional[str] = None
    num_speakers: Optional[int] = None
    summary_mode: Optional[str] = None
    show_timestamps: Optional[bool] = None


class WorkerClaim(Strict):
    worker: str = "worker"
    device: str = "unknown"
    models: List[str] = Field(default_factory=list)


class WorkerProgress(Strict):
    progress: float = 0.0
    stage: str = ""


class WorkerError(Strict):
    message: str


class SegmentIn(Strict):
    start: float
    end: float
    text: str
    speaker: Optional[str] = None


class SummaryIn(Strict):
    overview: str = ""
    key_points: List[str] = Field(default_factory=list)
    action_items: List[str] = Field(default_factory=list)
    topics: List[str] = Field(default_factory=list)
    questions: List[str] = Field(default_factory=list)
    source: str = "offline"


class WorkerResult(Strict):
    segments: List[SegmentIn]
    summary: SummaryIn
    speakers: List[str] = Field(default_factory=list)
    # One voiceprint per detected speaker, plus which engine produced them.
    # Vectors from different engines are never compared -- see voiceid.py.
    speaker_embeddings: Dict[str, List[float]] = Field(default_factory=dict)
    embedding_engine: str = "none"
    # Whisper's native any-language -> English pass, speaker-aligned to the
    # same diarization turns as the original.
    translation: List[SegmentIn] = Field(default_factory=list)
    translated_from: str = ""
    language: str = "unknown"
    language_probability: float = 0.0
    duration: float = 0.0
    engine: Dict[str, Any] = Field(default_factory=dict)


class RequeueOptions(Strict):
    """Body for POST /api/recordings/{id}/requeue -- all optional overrides."""

    model_size: Optional[str] = None
    translate: Optional[str] = None
    language: Optional[str] = None
    speaker_mode: Optional[str] = None
    num_speakers: Optional[int] = None
    summary_mode: Optional[str] = None


class ReassignIn(Strict):
    """Move one turn (or a whole speaker's turns) to a different speaker."""

    segment_index: Optional[int] = None
    from_speaker: Optional[str] = None
    to_speaker: str


class PersonPatch(Strict):
    name: Optional[str] = None
    notes: Optional[str] = None


class ConfirmIn(Strict):
    speaker: str
    accept: bool = True


class NukeIn(Strict):
    """Irreversible bulk deletion of the caller's own data."""

    confirm: str                      # must be exactly "NUKE"
    forget_voices: bool = True        # also drop their voiceprint library
    delete_account: bool = False      # and erase the account itself
