"""Stealth-Scribe GPU worker.

Runs on your Windows PC. Asks the NAS for transcription jobs, does the heavy
lifting on your GPU, and posts the results back. Your audio never leaves your
own network.

    python worker.py                 # uses stealthscribe-worker.json next to this file
    python worker.py --once          # process one job then exit
    python worker.py --server http://10.0.0.146:8454 --token secret
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import sys
import tempfile
import time
import traceback
from typing import Any, Dict, Optional

import requests

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core import diarize, embed, summarize, transcribe  # noqa: E402
from core.audio import load_audio  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(HERE, "stealthscribe-worker.json")

DEFAULTS = {
    "server_url": "http://10.0.0.146:8458",
    "worker_token": "change-me",
    "worker_name": platform.node() or "gpu-worker",
    "hf_token": "",
    "ai_provider": "anthropic",
    "ai_key": "",
    "ai_model": "",
    "poll_seconds": 5,
    "device": "auto",
}

BANNER = r"""
  ___ _____ ___   _   _  _____ _  _     ___  ___ ___ ___ ___ ___
 / __|_   _| __| /_\ | ||_   _| || |   / __|/ __| _ \_ _| _ ) __|
 \__ \ | | | _| / _ \| |__| | | __ |   \__ \ (__|   /| || _ \ _|
 |___/ |_| |___/_/ \_\____|_| |_||_|   |___/\___|_|_\___|___/___|

  Audio in. Transcribe to English. Save as PDF.
  Worker -- smart transcription, on your own hardware
"""


def log(message: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def load_config(args: argparse.Namespace) -> Dict[str, Any]:
    cfg = dict(DEFAULTS)
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                cfg.update({k: v for k, v in json.load(f).items() if v not in (None, "")})
        except (OSError, ValueError) as exc:
            log(f"Could not read {os.path.basename(CONFIG_PATH)}: {exc}")

    for key, env in (
        ("server_url", "STEALTHSCRIBE_SERVER"),
        ("worker_token", "STEALTHSCRIBE_TOKEN"),
        ("worker_name", "STEALTHSCRIBE_WORKER_NAME"),
        ("hf_token", "HF_TOKEN"),
        ("ai_key", "ANTHROPIC_API_KEY"),
    ):
        if os.environ.get(env):
            cfg[key] = os.environ[env]

    if args.server:
        cfg["server_url"] = args.server
    if args.token:
        cfg["worker_token"] = args.token
    if args.name:
        cfg["worker_name"] = args.name
    if args.device:
        cfg["device"] = args.device

    cfg["server_url"] = str(cfg["server_url"]).rstrip("/")
    return cfg


class Client:
    def __init__(self, cfg: Dict[str, Any]):
        self.base = cfg["server_url"]
        self.session = requests.Session()
        self.session.headers["X-Worker-Token"] = cfg["worker_token"]
        self.name = cfg["worker_name"]
        self.device = "unknown"

    def _url(self, path: str) -> str:
        return path if path.startswith("http") else f"{self.base}{path}"

    def claim(self) -> Optional[dict]:
        r = self.session.post(
            self._url("/api/worker/claim"),
            json={"worker": self.name, "device": self.device, "models": []},
            timeout=30,
        )
        if r.status_code == 204:
            return None
        if r.status_code == 401:
            raise PermissionError(
                "Server rejected the worker token. Check worker_token in "
                "stealthscribe-worker.json matches WORKER_TOKEN on the NAS."
            )
        r.raise_for_status()
        return r.json()

    def heartbeat(self) -> None:
        try:
            self.session.post(
                self._url("/api/worker/heartbeat"),
                json={"worker": self.name, "device": self.device, "models": []},
                timeout=15,
            )
        except requests.RequestException:
            pass

    def download(self, job: dict, dest_dir: str) -> str:
        name = job.get("original_name") or f"{job['id']}.audio"
        path = os.path.join(dest_dir, os.path.basename(name))
        with self.session.get(self._url(job["audio_url"]), stream=True, timeout=600) as r:
            r.raise_for_status()
            with open(path, "wb") as f:
                for chunk in r.iter_content(1024 * 512):
                    if chunk:
                        f.write(chunk)
        return path

    def progress(self, job_id: str, value: float, stage: str) -> None:
        try:
            self.session.post(
                self._url(f"/api/worker/jobs/{job_id}/progress"),
                json={"progress": float(value), "stage": stage},
                timeout=20,
            )
        except requests.RequestException:
            pass

    def result(self, job_id: str, payload: dict) -> None:
        r = self.session.post(
            self._url(f"/api/worker/jobs/{job_id}/result"), json=payload, timeout=180
        )
        r.raise_for_status()

    def fail(self, job_id: str, message: str) -> None:
        try:
            self.session.post(
                self._url(f"/api/worker/jobs/{job_id}/error"),
                json={"message": message},
                timeout=30,
            )
        except requests.RequestException:
            pass


def run_job(client: Client, cfg: Dict[str, Any], job: dict) -> None:
    job_id = job["id"]
    options = job.get("options") or {}
    model_size = options.get("model_size") or "medium"
    language = options.get("language") or "auto"
    speaker_mode = options.get("speaker_mode") or "auto"
    num_speakers = int(options.get("num_speakers") or 0)
    summary_mode = options.get("summary_mode") or "offline"
    translate_mode = options.get("translate") or "auto"   # off | auto | always

    log(f"Job {job_id[:8]} -- {job.get('title') or job.get('original_name')}")

    with tempfile.TemporaryDirectory(prefix="stealthscribe-") as tmp:
        client.progress(job_id, 0.02, "downloading audio")
        path = client.download(job, tmp)
        audio = load_audio(path)
        minutes = audio.size / 16000 / 60
        log(f"  {minutes:.1f} minutes of audio")

        client.progress(job_id, 0.05, "loading model")
        result = transcribe.transcribe(
            audio,
            model_size=model_size,
            device_preference=cfg.get("device", "auto"),
            language=None if language in ("auto", "", None) else language,
            log=lambda m: log(f"  {m}"),
            progress=lambda f: client.progress(
                job_id, 0.05 + 0.65 * f, f"transcribing ({int(f * 100)}%)"
            ),
        )
        client.device = result.device

        diarizer_used = "off"
        # Bound here, not inside the branch: the translation step below reads
        # `turns` to reuse the same speaker alignment, and with speakers turned
        # off on a non-English recording that was a NameError mid-job.
        turns = []
        if speaker_mode != "off" and result.segments:
            client.progress(job_id, 0.74, "identifying speakers")
            if speaker_mode == "auto" and cfg.get("hf_token"):
                try:
                    turns = diarize.diarize_pyannote(
                        audio,
                        hf_token=cfg["hf_token"],
                        num_speakers=num_speakers or None,
                        device_preference=cfg.get("device", "auto"),
                        log=lambda m: log(f"  {m}"),
                    )
                    diarizer_used = "pyannote 3.1"
                except Exception as exc:
                    log(f"  speaker model unavailable ({exc}); using built-in detector")
                    turns = []
            if not turns:
                turns = diarize.diarize_builtin(
                    audio, result.segments, num_speakers=num_speakers or None,
                    log=lambda m: log(f"  {m}")
                )
                diarizer_used = "built-in (approximate)"
            if turns:
                result.segments = diarize.assign_speakers(result.segments, turns)

        # ---- translation ---------------------------------------------------
        # Whisper translates any supported language straight to English with a
        # decoder flag -- same model, second pass, no separate MT system. It
        # only ever goes TO English; that is a Whisper limitation, not ours.
        detected = (result.language or "").lower()
        wants_translation = (
            translate_mode == "always"
            or (translate_mode == "auto" and detected not in ("en", "english", ""))
        )
        translation = []
        translated_from = ""
        if wants_translation and result.segments:
            client.progress(job_id, 0.76, f"translating {detected or 'audio'} to English")
            try:
                tr = transcribe.transcribe(
                    audio,
                    model_size=model_size,
                    device_preference=cfg.get("device", "auto"),
                    language=detected or None,
                    task="translate",
                    log=lambda m: log(f"  {m}"),
                    progress=lambda f: client.progress(
                        job_id, 0.76 + 0.06 * f, f"translating ({int(f * 100)}%)"
                    ),
                )
                # Reuse the SAME diarization turns, so the English text carries
                # the same speaker labels as the original.
                if turns and tr.segments:
                    tr.segments = diarize.assign_speakers(tr.segments, turns)
                translation = [
                    {"start": round(s.start, 3), "end": round(s.end, 3),
                     "text": s.text, "speaker": s.speaker}
                    for s in tr.segments
                ]
                translated_from = detected
                log(f"  translated {len(translation)} segments from {detected} to English")
            except Exception as exc:
                log(f"  translation failed ({exc}); keeping the original only")

        # ---- voiceprints ---------------------------------------------------
        # One vector per speaker so the server can recognise these people in
        # future recordings. Never fatal: a failure here still ships a
        # perfectly good transcript.
        voiceprints = {"engine": "none", "vectors": {}}
        if diarizer_used != "off" and result.segments:
            client.progress(job_id, 0.84, "capturing voiceprints")
            speakers = []
            for seg in result.segments:
                if seg.speaker and seg.speaker not in speakers:
                    speakers.append(seg.speaker)
            voiceprints = embed.extract(
                audio, result.segments, speakers,
                hf_token=cfg.get("hf_token", ""),
                device_preference=cfg.get("device", "auto"),
                log=lambda m: log(f"  {m}"),
            )

        client.progress(job_id, 0.88, "writing summary")
        # Summarise the English text when a translation exists -- a summary in
        # a language the reader can't read is worthless.
        plain = ("\n".join(s["text"] for s in translation) if translation
                 else "\n".join(s.text for s in result.segments))
        summary = None
        if summary_mode == "ai" and cfg.get("ai_key"):
            try:
                summary = summarize.summarize_ai(
                    plain,
                    provider=cfg.get("ai_provider", "anthropic"),
                    api_key=cfg["ai_key"],
                    model=cfg.get("ai_model") or None,
                    log=lambda m: log(f"  {m}"),
                )
            except Exception as exc:
                log(f"  AI summary failed ({exc}); using the offline summary")
        if summary is None:
            summary = summarize.summarize_offline(plain)

        client.progress(job_id, 0.96, "uploading results")
        payload = {
            "segments": [
                {"start": round(s.start, 3), "end": round(s.end, 3),
                 "text": s.text, "speaker": s.speaker}
                for s in result.segments
            ],
            "summary": {
                "overview": summary.overview,
                "key_points": summary.key_points,
                "action_items": summary.action_items,
                "topics": summary.topics,
                "questions": summary.questions,
                "source": summary.source,
            },
            "translation": translation,
            "translated_from": translated_from,
            "speaker_embeddings": voiceprints["vectors"],
            "embedding_engine": voiceprints["engine"],
            "language": result.language,
            "language_probability": result.language_probability,
            "duration": result.duration,
            "engine": {
                "model": result.model_size,
                "device": result.device,
                "diarizer": diarizer_used,
                "worker": client.name,
            },
        }
        client.result(job_id, payload)
        log(f"  done ({len(result.segments)} segments)")


def main() -> int:
    p = argparse.ArgumentParser(description="Stealth-Scribe transcription worker")
    p.add_argument("--server", help="e.g. http://10.0.0.146:8458")
    p.add_argument("--token", help="must match WORKER_TOKEN on the NAS")
    p.add_argument("--name", help="how this worker shows up in the web app")
    p.add_argument("--device", choices=["auto", "cuda", "cpu"])
    p.add_argument("--once", action="store_true", help="process one job then exit")
    args = p.parse_args()

    cfg = load_config(args)
    print(BANNER)
    log(f"Server : {cfg['server_url']}")
    log(f"Worker : {cfg['worker_name']}")

    device = transcribe.detect_device(cfg.get("device", "auto"))
    gpu = transcribe.gpu_name()
    log(f"Device : {device.upper()}" + (f" ({gpu})" if gpu else ""))
    if device == "cpu":
        log("No GPU detected -- transcription will be slow. That is fine, just slower.")
    if not cfg.get("hf_token"):
        log("No Hugging Face token set -- using the built-in speaker detector.")

    client = Client(cfg)
    client.device = f"{device}" + (f" / {gpu}" if gpu else "")

    idle_logged = False
    poll = max(2, int(cfg.get("poll_seconds") or 5))

    while True:
        try:
            job = client.claim()
            if job is None:
                if not idle_logged:
                    log("Waiting for jobs... (leave this window open)")
                    idle_logged = True
                if args.once:
                    return 0
                time.sleep(poll)
                continue

            idle_logged = False
            try:
                run_job(client, cfg, job)
            except Exception as exc:
                log(f"  FAILED: {exc}")
                traceback.print_exc(limit=3)
                client.fail(job["id"], f"{type(exc).__name__}: {exc}")
            if args.once:
                return 0

        except PermissionError as exc:
            log(str(exc))
            return 1
        except KeyboardInterrupt:
            log("Stopped.")
            return 0
        except requests.RequestException as exc:
            log(f"Cannot reach the server ({exc.__class__.__name__}). Retrying in 15s.")
            time.sleep(15)
        except Exception as exc:
            log(f"Unexpected error: {exc}")
            traceback.print_exc(limit=3)
            time.sleep(15)


if __name__ == "__main__":
    raise SystemExit(main())
