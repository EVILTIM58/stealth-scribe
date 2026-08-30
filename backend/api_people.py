"""/api/people/* — the voiceprint library.

Every named voice belongs to exactly one user. Voiceprints are biometric data,
so they are never shared between accounts, not even with admins.
"""

from __future__ import annotations

import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query

import auth
import db
import models
import voiceid

router = APIRouter(prefix="/api/people", tags=["people"])


def _public(doc: dict) -> dict:
    return {
        "id": doc["_id"],
        "name": doc.get("name", ""),
        "notes": doc.get("notes", ""),
        "engine": doc.get("engine", "none"),
        "samples": int(doc.get("samples") or 0),
        "recordings": len(doc.get("recording_ids") or []),
        "created_at": (doc["created_at"].isoformat() if doc.get("created_at") else None),
        "updated_at": (doc["updated_at"].isoformat() if doc.get("updated_at") else None),
        # The centroid itself is never sent to the browser. It is biometric
        # data and the UI has no use for 512 floats.
    }


async def enroll(
    owner_id: str, name: str, vector: Optional[List[float]], engine: str,
    recording_id: str = "",
) -> Optional[dict]:
    """Teach the library a voice, or reinforce one it already knows.

    Called whenever a human puts a name to a speaker -- that naming action is
    the training signal, so recognition improves purely by using the app.
    """
    name = (name or "").strip()[:60]
    if not name:
        return None

    existing = await db.voiceprints().find_one({"owner_id": owner_id, "name": name})

    # A name with no usable vector still earns a record, so the person exists
    # in the library and picks up a voiceprint on the next recording.
    if not vector or engine not in ("pyannote", "builtin"):
        if existing:
            return existing
        doc = {
            "_id": uuid.uuid4().hex, "owner_id": owner_id, "name": name, "notes": "",
            "engine": "none", "centroid": [], "samples": 0,
            "recording_ids": [recording_id] if recording_id else [],
            "created_at": auth.now(), "updated_at": auth.now(),
        }
        await db.voiceprints().insert_one(doc)
        return doc

    vector = voiceid.normalise(vector)

    if not existing:
        doc = {
            "_id": uuid.uuid4().hex, "owner_id": owner_id, "name": name, "notes": "",
            "engine": engine, "centroid": vector, "samples": 1,
            "recording_ids": [recording_id] if recording_id else [],
            "created_at": auth.now(), "updated_at": auth.now(),
        }
        await db.voiceprints().insert_one(doc)
        return doc

    # An existing entry from a weaker engine is replaced outright by a real
    # neural voiceprint rather than averaged -- the two aren't commensurable.
    if existing.get("engine") != engine:
        if engine == "pyannote":
            centroid, samples = vector, 1
        else:
            return existing  # never downgrade a good voiceprint
    else:
        centroid = voiceid.updated_centroid(
            existing.get("centroid") or [], int(existing.get("samples") or 0), vector
        )
        samples = int(existing.get("samples") or 0) + 1

    await db.voiceprints().update_one(
        {"_id": existing["_id"]},
        {"$set": {"centroid": centroid, "samples": samples, "engine": engine,
                  "updated_at": auth.now()},
         "$addToSet": {"recording_ids": recording_id} if recording_id else {}},
    )
    return await db.voiceprints().find_one({"_id": existing["_id"]})


@router.get("")
async def list_people(user: dict = Depends(auth.current_user)) -> dict:
    rows = await db.voiceprints().find({"owner_id": user["_id"]}).sort(
        [("updated_at", -1)]
    ).to_list(500)
    return {
        "items": [_public(r) for r in rows],
        "trained": sum(1 for r in rows if r.get("engine") == "pyannote"),
        "thresholds": {"auto": voiceid.AUTO_ASSIGN, "suggest": voiceid.SUGGEST},
    }


@router.patch("/{person_id}")
async def update_person(
    person_id: str, patch: models.PersonPatch, user: dict = Depends(auth.current_user)
) -> dict:
    doc = await db.voiceprints().find_one({"_id": person_id, "owner_id": user["_id"]})
    if not doc:
        raise HTTPException(404, "Person not found")

    update = {}
    if patch.notes is not None:
        update["notes"] = patch.notes[:500]
    if patch.name is not None:
        new_name = patch.name.strip()[:60]
        if not new_name:
            raise HTTPException(400, "Name cannot be empty")
        clash = await db.voiceprints().find_one(
            {"owner_id": user["_id"], "name": new_name, "_id": {"$ne": person_id}}
        )
        if clash:
            raise HTTPException(409, f"You already have someone called {new_name}.")
        update["name"] = new_name
        # Renaming a person renames them on every transcript they appear in.
        await _rename_everywhere(user["_id"], doc["name"], new_name)

    if not update:
        raise HTTPException(400, "Nothing to update")
    update["updated_at"] = auth.now()
    await db.voiceprints().update_one({"_id": person_id}, {"$set": update})
    return _public(await db.voiceprints().find_one({"_id": person_id}))


async def _rename_everywhere(owner_id: str, old: str, new: str) -> int:
    """speaker_labels maps raw diarizer ids to display names, so renaming means
    rewriting the values, which Mongo cannot do with a single $set."""
    changed = 0
    async for rec in db.recordings().find(
        {"owner_id": owner_id, "speaker_labels": {"$exists": True}},
        {"speaker_labels": 1},
    ):
        labels = rec.get("speaker_labels") or {}
        if old not in labels.values():
            continue
        updated = {k: (new if v == old else v) for k, v in labels.items()}
        await db.recordings().update_one(
            {"_id": rec["_id"]}, {"$set": {"speaker_labels": updated}}
        )
        changed += 1
    return changed


@router.delete("/{person_id}")
async def delete_person(
    person_id: str,
    keep_labels: bool = Query(True),
    user: dict = Depends(auth.current_user),
) -> dict:
    doc = await db.voiceprints().find_one({"_id": person_id, "owner_id": user["_id"]})
    if not doc:
        raise HTTPException(404, "Person not found")
    await db.voiceprints().delete_one({"_id": person_id})
    # By default the name stays on transcripts already labelled -- forgetting a
    # voice shouldn't silently rewrite history.
    return {"ok": True, "labels_kept": keep_labels}


@router.post("/{person_id}/merge/{other_id}")
async def merge_people(
    person_id: str, other_id: str, user: dict = Depends(auth.current_user)
) -> dict:
    """Fold a duplicate into the real person (same voice named twice)."""
    keep = await db.voiceprints().find_one({"_id": person_id, "owner_id": user["_id"]})
    drop = await db.voiceprints().find_one({"_id": other_id, "owner_id": user["_id"]})
    if not keep or not drop:
        raise HTTPException(404, "Person not found")
    if keep["_id"] == drop["_id"]:
        raise HTTPException(400, "Cannot merge someone into themselves")

    centroid = keep.get("centroid") or []
    samples = int(keep.get("samples") or 0)
    if drop.get("engine") == keep.get("engine") and drop.get("centroid"):
        centroid = voiceid.updated_centroid(centroid, samples, drop["centroid"])
        samples += int(drop.get("samples") or 0)
    elif not centroid and drop.get("centroid"):
        centroid, samples = drop["centroid"], int(drop.get("samples") or 0)

    await _rename_everywhere(user["_id"], drop["name"], keep["name"])
    await db.voiceprints().update_one(
        {"_id": keep["_id"]},
        {"$set": {"centroid": centroid, "samples": samples,
                  "engine": keep.get("engine") or drop.get("engine", "none"),
                  "updated_at": auth.now()},
         "$addToSet": {"recording_ids": {"$each": drop.get("recording_ids") or []}}},
    )
    await db.voiceprints().delete_one({"_id": drop["_id"]})
    return _public(await db.voiceprints().find_one({"_id": keep["_id"]}))


@router.get("/{person_id}/recordings")
async def person_recordings(
    person_id: str, user: dict = Depends(auth.current_user)
) -> dict:
    """Everything this person has ever been recorded saying."""
    doc = await db.voiceprints().find_one({"_id": person_id, "owner_id": user["_id"]})
    if not doc:
        raise HTTPException(404, "Person not found")

    rows = await db.recordings().find(
        {"owner_id": user["_id"], "status": "done"},
        {"segments": 0, "text": 0},
    ).sort([("recorded_at", -1)]).to_list(300)

    name = doc["name"]
    items = [
        {"id": r["_id"], "title": r.get("title"),
         "recorded_at": (r["recorded_at"].isoformat() if r.get("recorded_at") else None),
         "duration_sec": r.get("duration_sec", 0)}
        for r in rows if name in (r.get("speaker_labels") or {}).values()
    ]
    return {"person": _public(doc), "items": items, "total": len(items)}
