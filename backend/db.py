"""MongoDB access."""

from __future__ import annotations

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

import settings

_client: AsyncIOMotorClient | None = None
_db: AsyncIOMotorDatabase | None = None


def get_db() -> AsyncIOMotorDatabase:
    global _client, _db
    if _db is None:
        _client = AsyncIOMotorClient(settings.MONGO_URL, uuidRepresentation="standard")
        _db = _client[settings.DB_NAME]
    return _db


def recordings():
    return get_db()["recordings"]


def uploads():
    return get_db()["uploads"]


def workers():
    return get_db()["workers"]


def app_settings():
    return get_db()["settings"]


def users():
    return get_db()["users"]


def sessions():
    return get_db()["sessions"]


def auth_tokens():
    """Single-use email tokens: verification and password reset."""
    return get_db()["auth_tokens"]


def oauth_states():
    return get_db()["oauth_states"]


def voiceprints():
    """Named voices, per user. The library that makes recognition improve."""
    return get_db()["voiceprints"]


async def ensure_indexes() -> None:
    db = get_db()
    await db["recordings"].create_index([("created_at", -1)])
    await db["recordings"].create_index([("status", 1), ("created_at", 1)])
    await db["recordings"].create_index([("folder", 1)])
    await db["recordings"].create_index([("tags", 1)])
    # text_en carries the English translation, so searching in English finds
    # an Arabic recording. Mongo allows only ONE text index per collection and
    # refuses to redefine one in place, so an older index must be dropped first.
    fulltext = dict(
        keys=[("title", "text"), ("text", "text"), ("text_en", "text"),
              ("notes", "text"), ("tags", "text")],
        name="fulltext",
        weights={"title": 8, "tags": 5, "notes": 3, "text": 1, "text_en": 1},
        default_language="english",
    )
    try:
        await db["recordings"].create_index(fulltext["keys"], name=fulltext["name"],
                                            weights=fulltext["weights"],
                                            default_language=fulltext["default_language"])
    except Exception:
        # IndexKeySpecsConflict: the index exists with a different definition.
        try:
            await db["recordings"].drop_index("fulltext")
        except Exception:
            pass
        await db["recordings"].create_index(fulltext["keys"], name=fulltext["name"],
                                            weights=fulltext["weights"],
                                            default_language=fulltext["default_language"])
    await db["recordings"].create_index([("owner_id", 1), ("created_at", -1)])
    await db["uploads"].create_index([("created_at", 1)], expireAfterSeconds=60 * 60 * 24)
    await db["workers"].create_index([("last_seen", -1)])

    await db["users"].create_index([("email", 1)], unique=True)
    await db["users"].create_index([("created_at", -1)])
    # Mongo expires these on its own, so there is no cleanup code to forget.
    await db["sessions"].create_index([("expires_at", 1)], expireAfterSeconds=0)
    await db["sessions"].create_index([("user_id", 1)])
    await db["auth_tokens"].create_index([("expires_at", 1)], expireAfterSeconds=0)
    await db["auth_tokens"].create_index([("user_id", 1), ("purpose", 1)])
    await db["oauth_states"].create_index([("created_at", 1)], expireAfterSeconds=900)

    await db["voiceprints"].create_index([("owner_id", 1), ("name", 1)], unique=True)
    await db["voiceprints"].create_index([("owner_id", 1), ("updated_at", -1)])


DEFAULT_SETTINGS = {
    "_id": "defaults",
    "model_size": "medium",
    "language": "auto",
    "speaker_mode": "auto",     # auto | builtin | off
    "num_speakers": 0,          # 0 = detect
    "summary_mode": "offline",  # offline | ai
    # off = never, auto = whenever the audio isn't English, always = every time
    "translate": "auto",
    "show_timestamps": True,
}


async def get_settings() -> dict:
    doc = await app_settings().find_one({"_id": "defaults"})
    if not doc:
        await app_settings().insert_one(dict(DEFAULT_SETTINGS))
        return dict(DEFAULT_SETTINGS)
    merged = dict(DEFAULT_SETTINGS)
    merged.update(doc)
    return merged
