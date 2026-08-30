"""/api/admin/* — user management.

The role rules, exactly as specified:
  * GOD is hardcoded to one email address and cannot be granted or revoked.
  * ONLY GOD can promote a user to ADMIN.
  * ONLY GOD can demote an ADMIN back to USER.
  * ADMIN has every feature except these; USER has everything except admin.
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

import datetime as dt

import auth
import db
import models
import settings
import storage

router = APIRouter(prefix="/api/admin", tags=["admin"])


class RoleIn(models.Strict):
    role: str


class UserFlagsIn(models.Strict):
    banned: Optional[bool] = None
    name: Optional[str] = None


def _protect_god(target: dict) -> None:
    if auth.is_god_email(target.get("email", "")):
        raise HTTPException(403, "The owner account cannot be modified.")


@router.get("/users")
async def list_users(
    q: str = Query(""),
    limit: int = Query(100, le=500),
    skip: int = 0,
    actor: dict = Depends(auth.require_admin),
) -> dict:
    query = {}
    if q.strip():
        query = {"$or": [
            {"email": {"$regex": q.strip(), "$options": "i"}},
            {"name": {"$regex": q.strip(), "$options": "i"}},
        ]}
    rows = await db.users().find(query).sort([("created_at", -1)]).skip(skip).limit(limit).to_list(limit)
    total = await db.users().count_documents(query)

    # Attach each user's usage so the list is actually useful.
    out = []
    for row in rows:
        agg = await db.recordings().aggregate([
            {"$match": {"owner_id": row["_id"]}},
            {"$group": {"_id": None, "n": {"$sum": 1},
                        "dur": {"$sum": "$duration_sec"},
                        "bytes": {"$sum": "$size_bytes"}}},
        ]).to_list(1)
        stats = agg[0] if agg else {}
        item = auth.public_user(row)
        item["usage"] = {
            "recordings": int(stats.get("n") or 0),
            "duration_sec": float(stats.get("dur") or 0),
            "bytes": int(stats.get("bytes") or 0),
        }
        out.append(item)

    return {
        "items": out,
        "total": total,
        "actor_role": actor["role"],
        "god_email": settings.GOD_EMAIL,
    }


@router.patch("/users/{user_id}/role")
async def set_role(user_id: str, payload: RoleIn, actor: dict = Depends(auth.require_god)) -> dict:
    """GOD only. Enforced by the dependency -- an ADMIN calling this gets 403."""
    role = payload.role.strip().upper()
    if role not in (auth.ROLE_USER, auth.ROLE_ADMIN):
        raise HTTPException(400, "Role must be USER or ADMIN. GOD is not assignable.")

    target = await db.users().find_one({"_id": user_id})
    if not target:
        raise HTTPException(404, "User not found")
    _protect_god(target)
    if target["_id"] == actor["_id"]:
        raise HTTPException(400, "You cannot change your own role.")

    await db.users().update_one({"_id": user_id}, {"$set": {"role": role}})
    fresh = await db.users().find_one({"_id": user_id})
    return auth.public_user(fresh)


def _guard_target(target: dict, actor: dict) -> None:
    """The shared rule set for every action an admin can take on an account.

    An ADMIN may not ban, promote or demote another ADMIN -- only GOD may.
    Without this, two admins can suspend each other and the owner arrives to
    find nobody can administer anything.
    """
    _protect_god(target)
    target_role = auth.role_for(target.get("email", ""), target.get("role"))
    if target_role == auth.ROLE_ADMIN and actor["role"] != auth.ROLE_GOD:
        raise HTTPException(
            403, "Admins cannot act on other admins. Only the owner can."
        )
    if target["_id"] == actor["_id"]:
        raise HTTPException(400, "You cannot do that to your own account.")


@router.get("/ban-durations")
async def ban_durations(actor: dict = Depends(auth.require_admin)) -> dict:
    return {"durations": [
        {"key": key, "label": label} for key, (label, _) in auth.BAN_DURATIONS.items()
    ]}


@router.post("/users/{user_id}/ban")
async def ban_user(
    user_id: str, payload: models.BanIn, actor: dict = Depends(auth.require_admin)
) -> dict:
    """Suspend an account for a fixed period, or permanently.

    The duration is mandatory. "Banned forever by accident" is the most common
    moderation mistake, and requiring a length forces the decision to be
    deliberate rather than a reflex click.
    """
    if payload.duration not in auth.BAN_DURATIONS:
        raise HTTPException(
            400, f"Duration must be one of: {', '.join(auth.BAN_DURATIONS)}"
        )
    target = await db.users().find_one({"_id": user_id})
    if not target:
        raise HTTPException(404, "User not found")
    _guard_target(target, actor)

    label, delta = auth.BAN_DURATIONS[payload.duration]
    until = (auth.now() + delta) if delta else None

    await db.users().update_one(
        {"_id": user_id},
        {"$set": {"banned": True, "banned_until": until,
                  "ban_reason": payload.reason.strip()[:300],
                  "banned_by": actor.get("email", ""), "banned_at": auth.now(),
                  "ban_duration": payload.duration}},
    )
    # End their sessions now, not at their next page load.
    await db.sessions().delete_many({"user_id": user_id})

    fresh = await db.users().find_one({"_id": user_id})
    return {"user": auth.public_user(fresh), "duration": label}


@router.post("/users/{user_id}/unban")
async def unban_user(user_id: str, actor: dict = Depends(auth.require_admin)) -> dict:
    target = await db.users().find_one({"_id": user_id})
    if not target:
        raise HTTPException(404, "User not found")
    _guard_target(target, actor)
    await db.users().update_one(
        {"_id": user_id},
        {"$set": {"banned": False},
         "$unset": {"banned_until": "", "ban_reason": "", "banned_by": "",
                    "banned_at": "", "ban_duration": ""}},
    )
    return auth.public_user(await db.users().find_one({"_id": user_id}))


@router.patch("/users/{user_id}")
async def update_user(
    user_id: str, payload: UserFlagsIn, actor: dict = Depends(auth.require_admin)
) -> dict:
    target = await db.users().find_one({"_id": user_id})
    if not target:
        raise HTTPException(404, "User not found")
    _guard_target(target, actor)

    if payload.banned is not None:
        raise HTTPException(
            400, "Use /ban with a duration, or /unban. A ban needs a length."
        )
    if payload.name is None:
        raise HTTPException(400, "Nothing to update")

    await db.users().update_one(
        {"_id": user_id}, {"$set": {"name": payload.name.strip()[:80]}}
    )
    return auth.public_user(await db.users().find_one({"_id": user_id}))


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: str,
    keep_recordings: bool = Query(False),
    actor: dict = Depends(auth.require_god),
) -> dict:
    """GOD only. Removes the account and, by default, everything they uploaded."""
    target = await db.users().find_one({"_id": user_id})
    if not target:
        raise HTTPException(404, "User not found")
    _protect_god(target)

    removed = 0
    if not keep_recordings:
        async for rec in db.recordings().find({"owner_id": user_id}, {"media_path": 1}):
            storage.delete_media(rec["media_path"])
            removed += 1
        await db.recordings().delete_many({"owner_id": user_id})

    await db.sessions().delete_many({"user_id": user_id})
    await db.auth_tokens().delete_many({"user_id": user_id})
    await db.users().delete_one({"_id": user_id})
    return {"ok": True, "recordings_deleted": removed}


@router.get("/overview")
async def overview(actor: dict = Depends(auth.require_admin)) -> dict:
    users_total = await db.users().count_documents({})
    banned = await db.users().count_documents({
        "banned": True,
        "$or": [{"banned_until": None}, {"banned_until": {"$gt": auth.now()}}],
    })
    admins = await db.users().count_documents({"role": auth.ROLE_ADMIN})
    verified = await db.users().count_documents({"email_verified": True})

    agg = await db.recordings().aggregate([
        {"$group": {"_id": None, "n": {"$sum": 1},
                    "dur": {"$sum": "$duration_sec"},
                    "bytes": {"$sum": "$size_bytes"}}},
    ]).to_list(1)
    totals = agg[0] if agg else {}

    top = await db.recordings().aggregate([
        {"$group": {"_id": "$owner_email", "n": {"$sum": 1},
                    "dur": {"$sum": "$duration_sec"}}},
        {"$sort": {"dur": -1}}, {"$limit": 10},
    ]).to_list(10)

    return {
        "users": {"total": users_total, "banned": banned, "admins": admins,
                  "verified": verified},
        "recordings": {"total": int(totals.get("n") or 0),
                       "duration_sec": float(totals.get("dur") or 0),
                       "bytes": int(totals.get("bytes") or 0)},
        "top_users": [{"email": t["_id"], "recordings": t["n"],
                       "duration_sec": t["dur"]} for t in top if t["_id"]],
        "disk": storage.disk_usage(),
        "quota_minutes": settings.DAILY_MINUTES_QUOTA,
        "signup_open": settings.ALLOW_SIGNUP,
    }
