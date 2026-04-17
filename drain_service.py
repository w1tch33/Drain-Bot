import json
import io
import math
import os
import random
import re
import shutil
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime, timedelta, timezone
from typing import Any
from werkzeug.security import check_password_hash, generate_password_hash


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DATA_FILE = os.path.join(BASE_DIR, "drain_data.json")
DEFAULT_KML_FILE = os.path.join(BASE_DIR, "your_map.kml")


def _default_data_dir() -> str:
    railway_mount = os.getenv("RAILWAY_VOLUME_MOUNT_PATH", "").strip()
    if railway_mount:
        return railway_mount
    if os.path.isdir("/data"):
        return "/data"
    return BASE_DIR


DEFAULT_DATA_DIR = _default_data_dir()
DATA_DIR = os.getenv("DRAINTOOL_DATA_DIR", DEFAULT_DATA_DIR)
DATA_FILE = os.getenv("DRAINTOOL_DATA_FILE", os.path.join(DATA_DIR, "drain_data.json"))
KML_FILE = os.getenv("DRAINTOOL_KML_FILE", os.path.join(DATA_DIR, "your_map.kml"))
UPLOAD_DIR = os.getenv("DRAINTOOL_UPLOAD_DIR", os.path.join(DATA_DIR, "uploads"))
ACCOUNTS_FILE = os.getenv("DRAINTOOL_ACCOUNTS_FILE", os.path.join(DATA_DIR, "accounts.json"))
USERS_DIR = os.getenv("DRAINTOOL_USERS_DIR", os.path.join(DATA_DIR, "users"))
SHARED_MEASUREMENT_LINES_FILE = os.path.join(BASE_DIR, "static", "data", "shared_measurement_lines.json")
DEFAULT_KML_SYNC_URL = "https://earth.google.com/earth/d/1jhOxgKG18OSMNaiIXuqAdBXAaV3SMhfC?usp=drive_link"
KML_SYNC_URL = os.getenv("DRAINTOOL_KML_SYNC_URL", DEFAULT_KML_SYNC_URL)
PHOTO_DIR_CANDIDATES = [
    os.path.join(DATA_DIR, "Drain Pics"),
    os.path.join(DATA_DIR, "Drain pics"),
    os.path.join(DATA_DIR, "drain pics"),
    os.path.join(DATA_DIR, "DrainPics"),
    os.path.join(BASE_DIR, "Drain Pics"),
    os.path.join(BASE_DIR, "Drain pics"),
    os.path.join(BASE_DIR, "drain pics"),
    os.path.join(BASE_DIR, "DrainPics"),
]

BASE_LAT = -37.7672
BASE_LON = 145.1182

_LOCK = threading.Lock()
_CACHE_LOCK = threading.Lock()
_METADATA_CACHE: dict[str, Any] = {"stamp": None, "value": {}}
_USER_METADATA_CACHE: dict[str, tuple[float | None, dict[str, Any]]] = {}
_KML_DRAINS_CACHE: dict[str, Any] = {"stamp": None, "value": []}
_SHARED_MEASUREMENT_LINES_CACHE: dict[str, Any] = {"stamp": None, "value": []}


def ensure_runtime_dirs() -> None:
    os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    os.makedirs(USERS_DIR, exist_ok=True)


def bootstrap_metadata_file() -> None:
    ensure_runtime_dirs()
    if os.path.exists(DATA_FILE):
        return
    if os.path.exists(DEFAULT_DATA_FILE):
        shutil.copyfile(DEFAULT_DATA_FILE, DATA_FILE)
        return
    with open(DATA_FILE, "w", encoding="utf-8") as handle:
        json.dump({}, handle, indent=2)


def bootstrap_kml_file() -> None:
    ensure_runtime_dirs()
    if os.path.exists(KML_FILE):
        return
    if os.path.exists(DEFAULT_KML_FILE):
        shutil.copyfile(DEFAULT_KML_FILE, KML_FILE)


def bootstrap_accounts_file() -> None:
    ensure_runtime_dirs()
    if os.path.exists(ACCOUNTS_FILE):
        return
    with open(ACCOUNTS_FILE, "w", encoding="utf-8") as handle:
        json.dump({}, handle, indent=2)


def normalize_username(username: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]", "", (username or "").strip()).lower()


def valid_username(username: str) -> bool:
    return bool(re.fullmatch(r"[a-zA-Z0-9_-]{3,32}", username or ""))


def _unique_usernames(values: list[Any] | None) -> list[str]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values or []:
        normalized = normalize_username(str(value))
        if normalized and normalized not in seen:
            seen.add(normalized)
            ordered.append(normalized)
    return ordered


def _normalize_account_record(username: str, account: dict[str, Any]) -> dict[str, Any]:
    normalized = normalize_username(username or account.get("username", ""))
    return {
        "username": normalized,
        "password_hash": account.get("password_hash", ""),
        "approved": bool(account.get("approved")),
        "map_uploaded": bool(account.get("map_uploaded")),
        "friends": _unique_usernames(account.get("friends")),
        "incoming_requests": _unique_usernames(account.get("incoming_requests")),
        "outgoing_requests": _unique_usernames(account.get("outgoing_requests")),
    }


def user_metadata_path(username: str) -> str:
    return os.path.join(USERS_DIR, normalize_username(username), "metadata.json")


def user_account_path(username: str) -> str:
    return os.path.join(USERS_DIR, normalize_username(username), "account.json")


def user_upload_dir(username: str) -> str:
    return os.path.join(UPLOAD_DIR, normalize_username(username))


def ensure_user_dirs(username: str) -> None:
    os.makedirs(os.path.dirname(user_metadata_path(username)), exist_ok=True)
    os.makedirs(user_upload_dir(username), exist_ok=True)


def _load_user_account(username: str) -> dict[str, Any] | None:
    path = user_account_path(username)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as handle:
        account = json.load(handle)
    if not isinstance(account, dict):
        return None
    normalized = normalize_username(account.get("username", username))
    if not normalized:
        return None
    return _normalize_account_record(normalized, account)


def _save_user_account(username: str, account: dict[str, Any]) -> None:
    ensure_user_dirs(username)
    with open(user_account_path(username), "w", encoding="utf-8") as handle:
        json.dump(account, handle, indent=2, ensure_ascii=False)


def _iter_usernames_from_dirs() -> list[str]:
    ensure_runtime_dirs()
    usernames: list[str] = []
    for entry in os.listdir(USERS_DIR):
        path = os.path.join(USERS_DIR, entry)
        if os.path.isdir(path):
            normalized = normalize_username(entry)
            if normalized:
                usernames.append(normalized)
    usernames.sort()
    return usernames


def _synth_account_from_user_dir(username: str) -> dict[str, Any] | None:
    normalized = normalize_username(username)
    if not normalized:
        return None
    metadata = load_user_metadata(normalized)
    if not isinstance(metadata, dict) or not metadata:
        return None
    return {
        "username": normalized,
        "password_hash": "",
        "approved": True,
        "map_uploaded": bool(metadata.get("_map_uploaded")),
        "friends": _unique_usernames(metadata.get("_friends")),
        "incoming_requests": _unique_usernames(metadata.get("_incoming_requests")),
        "outgoing_requests": _unique_usernames(metadata.get("_outgoing_requests")),
    }


def load_accounts() -> dict[str, Any]:
    bootstrap_accounts_file()
    with open(ACCOUNTS_FILE, "r", encoding="utf-8") as handle:
        accounts = json.load(handle)
    if not isinstance(accounts, dict):
        accounts = {}

    merged: dict[str, Any] = {}
    for key, value in accounts.items():
        normalized = normalize_username(key if isinstance(key, str) else "")
        if normalized and isinstance(value, dict):
            merged[normalized] = _normalize_account_record(normalized, dict(value))

    for username in _iter_usernames_from_dirs():
        account = _load_user_account(username)
        if account:
            merged[username] = account
            continue
        synthetic = _synth_account_from_user_dir(username)
        if synthetic:
            merged[username] = _normalize_account_record(username, synthetic)

    return merged


def save_accounts(accounts: dict[str, Any]) -> None:
    with _LOCK:
        ensure_runtime_dirs()
        with open(ACCOUNTS_FILE, "w", encoding="utf-8") as handle:
            json.dump(accounts, handle, indent=2, ensure_ascii=False)
        for username, account in accounts.items():
            normalized = normalize_username(username)
            if normalized and isinstance(account, dict):
                stored = dict(account)
                stored["username"] = normalized
                _save_user_account(normalized, stored)


def load_user_metadata(username: str | None) -> dict[str, Any]:
    if not username:
        return {}
    path = user_metadata_path(username)
    if not os.path.exists(path):
        return {}
    try:
        stamp = os.path.getmtime(path)
    except OSError:
        return {}
    with _CACHE_LOCK:
        cached = _USER_METADATA_CACHE.get(path)
        if cached and cached[0] == stamp:
            return dict(cached[1])
    with open(path, "r", encoding="utf-8") as handle:
        loaded = json.load(handle)
    if not isinstance(loaded, dict):
        loaded = {}
    with _CACHE_LOCK:
        _USER_METADATA_CACHE[path] = (stamp, dict(loaded))
    return loaded


def save_user_metadata(username: str, data: dict[str, Any]) -> None:
    ensure_user_dirs(username)
    path = user_metadata_path(username)
    with _LOCK:
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, ensure_ascii=False)
    try:
        stamp = os.path.getmtime(path)
    except OSError:
        stamp = None
    with _CACHE_LOCK:
        _USER_METADATA_CACHE[path] = (stamp, dict(data))


NOTIFICATION_MAX = 120
ACTIVITY_MAX = 250
CHALLENGE_MAX = 180


def _normalize_notifications(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    normalized: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        message = str(item.get("message", "")).strip()
        if not message:
            continue
        notification_id = str(item.get("id", "")).strip() or str(uuid.uuid4())
        kind = str(item.get("kind", "")).strip() or "info"
        read = bool(item.get("read"))
        try:
            timestamp = float(item.get("ts", time.time()))
        except (TypeError, ValueError):
            timestamp = time.time()
        normalized.append(
            {
                "id": notification_id,
                "message": message,
                "kind": kind,
                "read": read,
                "ts": timestamp,
            }
        )
    normalized.sort(key=lambda item: item["ts"], reverse=True)
    return normalized[:NOTIFICATION_MAX]


def add_notification(username: str, message: str, kind: str = "info") -> dict[str, Any]:
    normalized = normalize_username(username)
    if not normalized:
        raise ValueError("Account not found.")
    clean_message = str(message or "").strip()
    if not clean_message:
        raise ValueError("Notification message is required.")
    metadata = load_user_metadata(normalized)
    notifications = _normalize_notifications(metadata.get("_notifications"))
    entry = {
        "id": str(uuid.uuid4()),
        "message": clean_message,
        "kind": str(kind or "info").strip() or "info",
        "read": False,
        "ts": time.time(),
    }
    notifications.insert(0, entry)
    metadata["_notifications"] = notifications[:NOTIFICATION_MAX]
    save_user_metadata(normalized, metadata)
    return entry


def get_notifications(username: str, unread_only: bool = False) -> dict[str, Any]:
    metadata = load_user_metadata(username)
    notifications = _normalize_notifications(metadata.get("_notifications"))
    unread_count = sum(1 for item in notifications if not item.get("read"))
    if unread_only:
        notifications = [item for item in notifications if not item.get("read")]
    return {
        "items": notifications,
        "unread": unread_count,
    }


def mark_notifications_read(username: str, ids: list[str] | None = None) -> dict[str, Any]:
    metadata = load_user_metadata(username)
    notifications = _normalize_notifications(metadata.get("_notifications"))
    if not notifications:
        return {"items": [], "unread": 0}

    id_set = {str(item).strip() for item in (ids or []) if str(item).strip()}
    for item in notifications:
        if not id_set or item["id"] in id_set:
            item["read"] = True

    metadata["_notifications"] = notifications
    save_user_metadata(username, metadata)
    return get_notifications(username)


def _normalize_activity(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    normalized: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        message = str(item.get("message", "")).strip()
        if not message:
            continue
        activity_id = str(item.get("id", "")).strip() or str(uuid.uuid4())
        actor = normalize_username(item.get("actor", ""))
        kind = str(item.get("kind", "")).strip() or "info"
        try:
            timestamp = float(item.get("ts", time.time()))
        except (TypeError, ValueError):
            timestamp = time.time()
        normalized.append(
            {
                "id": activity_id,
                "actor": actor,
                "message": message,
                "kind": kind,
                "ts": timestamp,
            }
        )
    normalized.sort(key=lambda entry: entry["ts"], reverse=True)
    return normalized[:ACTIVITY_MAX]


def add_activity(username: str, message: str, kind: str = "info") -> dict[str, Any]:
    normalized = normalize_username(username)
    if not normalized:
        raise ValueError("Account not found.")
    clean_message = str(message or "").strip()
    if not clean_message:
        raise ValueError("Activity message is required.")
    metadata = load_user_metadata(normalized)
    activity = _normalize_activity(metadata.get("_activity"))
    entry = {
        "id": str(uuid.uuid4()),
        "actor": normalized,
        "message": clean_message,
        "kind": str(kind or "info").strip() or "info",
        "ts": time.time(),
    }
    activity.insert(0, entry)
    metadata["_activity"] = activity[:ACTIVITY_MAX]
    save_user_metadata(normalized, metadata)
    return entry


def get_activity_feed(username: str | None, limit: int = 80) -> dict[str, Any]:
    normalized = normalize_username(username)
    if not normalized:
        return {"items": []}

    try:
        account = _account_record(normalized)
        friends = account.get("friends", [])
    except ValueError:
        friends = []

    sources = [normalized, *friends]
    merged: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for source in sources:
        metadata = load_user_metadata(source)
        for entry in _normalize_activity(metadata.get("_activity")):
            actor = normalize_username(entry.get("actor", "")) or source
            item = dict(entry)
            item["actor"] = actor
            entry_id = str(item.get("id", ""))
            if entry_id and entry_id in seen_ids:
                continue
            if entry_id:
                seen_ids.add(entry_id)
            merged.append(item)

    merged.sort(key=lambda item: float(item.get("ts", 0)), reverse=True)
    safe_limit = max(1, min(200, int(limit or 80)))
    return {"items": merged[:safe_limit]}


RANK_TIERS: list[tuple[str, int]] = [
    ("Rookie", 0),
    ("Scout", 350),
    ("Tunnel Rat", 900),
    ("Explorer", 1700),
    ("Urban Legend", 2800),
    ("Drain Wizard", 4200),
    ("Storm King", 6200),
]


def _visit_streaks(activity: list[dict[str, Any]]) -> tuple[int, int]:
    visit_days: set[datetime.date] = set()
    for item in activity:
        if str(item.get("kind", "")).lower() != "visit":
            continue
        try:
            ts = float(item.get("ts", 0))
        except (TypeError, ValueError):
            continue
        visit_days.add(datetime.fromtimestamp(ts, tz=timezone.utc).date())

    if not visit_days:
        return 0, 0

    sorted_days = sorted(visit_days)
    longest = 1
    chain = 1
    for index in range(1, len(sorted_days)):
        if sorted_days[index] - sorted_days[index - 1] == timedelta(days=1):
            chain += 1
            longest = max(longest, chain)
        else:
            chain = 1

    today = datetime.now(timezone.utc).date()
    anchor = today if today in visit_days else today - timedelta(days=1)
    if anchor not in visit_days:
        return 0, longest

    current = 0
    cursor = anchor
    while cursor in visit_days:
        current += 1
        cursor -= timedelta(days=1)

    return current, longest


def _photo_count_from_metadata(metadata: dict[str, Any]) -> int:
    total = 0
    for value in metadata.values():
        if not isinstance(value, dict):
            continue
        photos = value.get("photos", [])
        if isinstance(photos, list):
            total += len([photo for photo in photos if isinstance(photo, str) and photo.strip()])
    return total


def progression_summary(username: str | None) -> dict[str, Any]:
    normalized = normalize_username(username)
    if not normalized:
        return {
            "xp": 0,
            "rank": {"name": "Rookie", "xp": 0, "next_name": "Scout", "next_xp": 350, "progress": 0},
            "streaks": {"current": 0, "longest": 0},
            "badges": [],
            "seasonal": {"label": "Monthly Challenges", "completed": 0, "total": 0, "challenges": []},
        }

    metadata = load_user_metadata(normalized)
    activity = _normalize_activity(metadata.get("_activity"))
    stats = stats_summary(normalized)
    high_scores = get_user_high_scores(normalized)
    score_total = sum(int(item.get("score", 0)) for item in high_scores.values())
    photo_count = _photo_count_from_metadata(metadata)
    game_events = sum(1 for item in activity if str(item.get("kind", "")).lower() == "game")
    photo_events = sum(1 for item in activity if str(item.get("kind", "")).lower() == "photo")
    visit_events = sum(1 for item in activity if str(item.get("kind", "")).lower() == "visit")

    try:
        friend_count = len(_account_record(normalized).get("friends", []))
    except ValueError:
        friend_count = 0

    xp = (
        stats["visited"] * 120
        + photo_count * 35
        + friend_count * 45
        + stats["custom"] * 25
        + int(score_total * 0.18)
    )

    current_rank_name = RANK_TIERS[0][0]
    current_rank_xp = RANK_TIERS[0][1]
    next_rank_name = None
    next_rank_xp = None
    for index, (name, threshold) in enumerate(RANK_TIERS):
        if xp >= threshold:
            current_rank_name = name
            current_rank_xp = threshold
            if index + 1 < len(RANK_TIERS):
                next_rank_name, next_rank_xp = RANK_TIERS[index + 1]
            else:
                next_rank_name, next_rank_xp = None, None

    if next_rank_xp is None:
        rank_progress = 100
    else:
        span = max(1, next_rank_xp - current_rank_xp)
        rank_progress = max(0, min(100, int(((xp - current_rank_xp) / span) * 100)))

    current_streak, longest_streak = _visit_streaks(activity)

    month_start = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0).timestamp()
    monthly_visits = sum(
        1
        for item in activity
        if str(item.get("kind", "")).lower() == "visit" and float(item.get("ts", 0) or 0) >= month_start
    )
    monthly_photos = sum(
        1
        for item in activity
        if str(item.get("kind", "")).lower() == "photo" and float(item.get("ts", 0) or 0) >= month_start
    )
    monthly_games = sum(
        1
        for item in activity
        if str(item.get("kind", "")).lower() == "game" and float(item.get("ts", 0) or 0) >= month_start
    )

    seasonal_challenges = [
        {"id": "visit_5", "label": "Visit 5 drains", "target": 5, "progress": min(5, monthly_visits)},
        {"id": "photo_3", "label": "Upload 3 photos", "target": 3, "progress": min(3, monthly_photos)},
        {"id": "game_2", "label": "Beat 2 high scores", "target": 2, "progress": min(2, monthly_games)},
    ]

    badge_models = [
        ("first_visit", "First Splash", "Visit your first drain", stats["visited"], 1),
        ("week_streak", "Week Walker", "Reach a 7-day visit streak", longest_streak, 7),
        ("photo_hunter", "Photo Hunter", "Upload 20 drain photos", photo_count, 20),
        ("map_maker", "Map Maker", "Add 10 custom drains", stats["custom"], 10),
        ("social_rat", "Social Rat", "Have 5 friends", friend_count, 5),
        ("legend_score", "Arcade Ghost", "Earn 1000+ total game score", score_total, 1000),
    ]
    badges = [
        {
            "id": badge_id,
            "label": label,
            "description": description,
            "progress": int(progress),
            "target": int(target),
            "earned": int(progress) >= int(target),
        }
        for badge_id, label, description, progress, target in badge_models
    ]

    return {
        "xp": int(xp),
        "rank": {
            "name": current_rank_name,
            "xp": int(xp),
            "next_name": next_rank_name,
            "next_xp": int(next_rank_xp) if next_rank_xp is not None else None,
            "progress": rank_progress,
        },
        "streaks": {"current": int(current_streak), "longest": int(longest_streak), "visit_events": int(visit_events)},
        "badges": badges,
        "seasonal": {
            "label": f"{datetime.now(timezone.utc).strftime('%B')} Challenges",
            "completed": sum(1 for challenge in seasonal_challenges if challenge["progress"] >= challenge["target"]),
            "total": len(seasonal_challenges),
            "challenges": seasonal_challenges,
        },
        "metrics": {
            "photos": int(photo_count),
            "high_score_total": int(score_total),
            "friends": int(friend_count),
            "photo_events": int(photo_events),
            "game_events": int(game_events),
        },
    }


GAME_SCORE_LABELS = {
    "ladderclimb": "Drain Climber Turbo",
    "torchsprint": "Drain Runner",
}


def _normalize_high_scores(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    normalized: dict[str, int] = {}
    for key, raw_score in value.items():
        game_key = str(key or "").strip().lower()
        if game_key not in GAME_SCORE_LABELS:
            continue
        try:
            score = int(raw_score)
        except (TypeError, ValueError):
            continue
        normalized[game_key] = max(0, score)
    return normalized


def _normalize_game_challenges(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    normalized: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        challenge_id = str(item.get("id", "")).strip() or str(uuid.uuid4())
        sender = normalize_username(item.get("from", ""))
        recipient = normalize_username(item.get("to", ""))
        game_key = str(item.get("game", "")).strip().lower()
        status = str(item.get("status", "pending")).strip().lower()
        try:
            target = int(item.get("target", 0))
        except (TypeError, ValueError):
            target = 0
        try:
            created_ts = float(item.get("created_ts", time.time()))
        except (TypeError, ValueError):
            created_ts = time.time()
        try:
            resolved_ts = float(item.get("resolved_ts", 0) or 0)
        except (TypeError, ValueError):
            resolved_ts = 0.0
        if not sender or not recipient:
            continue
        if game_key not in GAME_SCORE_LABELS:
            continue
        if target <= 0:
            continue
        if status not in {"pending", "completed"}:
            status = "pending"
        normalized.append(
            {
                "id": challenge_id,
                "from": sender,
                "to": recipient,
                "game": game_key,
                "target": int(target),
                "status": status,
                "created_ts": created_ts,
                "resolved_ts": resolved_ts if status == "completed" else 0.0,
            }
        )
    normalized.sort(key=lambda entry: float(entry.get("created_ts", 0)), reverse=True)
    return normalized[:CHALLENGE_MAX]


def _challenge_payload(entry: dict[str, Any], viewer: str) -> dict[str, Any]:
    sender = normalize_username(entry.get("from", ""))
    recipient = normalize_username(entry.get("to", ""))
    game = str(entry.get("game", "")).lower()
    target = int(entry.get("target", 0))
    status = str(entry.get("status", "pending")).lower()
    return {
        "id": str(entry.get("id", "")),
        "from": sender,
        "to": recipient,
        "opponent": recipient if viewer == sender else sender,
        "game": game,
        "label": GAME_SCORE_LABELS.get(game, game),
        "target": target,
        "status": status,
        "created_ts": float(entry.get("created_ts", 0) or 0),
        "resolved_ts": float(entry.get("resolved_ts", 0) or 0),
    }


def _high_score_for_game(username: str | None, game: str) -> int:
    scores = get_user_high_scores(username)
    return int(scores.get(game, {}).get("score", 0))


def get_user_high_scores(username: str | None) -> dict[str, dict[str, Any]]:
    metadata = load_user_metadata(username)
    scores = _normalize_high_scores(metadata.get("_high_scores"))
    return {
        game_key: {"key": game_key, "label": GAME_SCORE_LABELS[game_key], "score": scores.get(game_key, 0)}
        for game_key in GAME_SCORE_LABELS
    }


def save_high_score(username: str, game: str, score: int) -> dict[str, dict[str, Any]]:
    normalized = normalize_username(username)
    game_key = str(game or "").strip().lower()
    if game_key not in GAME_SCORE_LABELS:
        raise ValueError("Unknown game.")
    try:
        safe_score = max(0, int(score))
    except (TypeError, ValueError) as exc:
        raise ValueError("Invalid score.") from exc

    metadata = load_user_metadata(normalized)
    scores = _normalize_high_scores(metadata.get("_high_scores"))
    if safe_score > scores.get(game_key, 0):
        scores[game_key] = safe_score
        metadata["_high_scores"] = scores
        save_user_metadata(normalized, metadata)
    return get_user_high_scores(normalized)


def leaderboard_for_game(game: str, limit: int = 15, viewer: str | None = None) -> dict[str, Any]:
    game_key = str(game or "").strip().lower()
    if game_key not in GAME_SCORE_LABELS:
        raise ValueError("Unknown game.")
    safe_limit = max(1, min(50, int(limit or 15)))
    viewer_name = normalize_username(viewer or "")
    rows: list[dict[str, Any]] = []
    for username, account in load_accounts().items():
        if not isinstance(account, dict) or not bool(account.get("approved")):
            continue
        score = _high_score_for_game(username, game_key)
        if score <= 0:
            continue
        rows.append({"username": username, "score": score})
    rows.sort(key=lambda entry: (-int(entry["score"]), str(entry["username"])))
    top = [{"rank": idx + 1, **entry} for idx, entry in enumerate(rows[:safe_limit])]
    viewer_rank = None
    if viewer_name:
        for idx, entry in enumerate(rows):
            if entry["username"] == viewer_name:
                viewer_rank = {"rank": idx + 1, "username": viewer_name, "score": int(entry["score"])}
                break
    return {
        "game": game_key,
        "label": GAME_SCORE_LABELS[game_key],
        "items": top,
        "viewer_rank": viewer_rank,
    }


def send_game_challenge(from_username: str, to_username: str, game: str, target: int) -> dict[str, Any]:
    sender = normalize_username(from_username)
    recipient = normalize_username(to_username)
    game_key = str(game or "").strip().lower()
    if sender == recipient:
        raise ValueError("Pick a friend to challenge.")
    if game_key not in GAME_SCORE_LABELS:
        raise ValueError("Unknown game.")
    try:
        target_score = max(1, int(target))
    except (TypeError, ValueError) as exc:
        raise ValueError("Target score must be a number.") from exc
    if target_score > 2_000_000:
        raise ValueError("Target score is too high.")

    sender_account = _account_record(sender)
    if recipient not in sender_account.get("friends", []):
        raise ValueError("You can only challenge people in your friends list.")
    if not account_exists(recipient):
        raise ValueError("Friend account not found.")
    if _high_score_for_game(recipient, game_key) >= target_score:
        raise ValueError("That friend already beat this target. Raise the score and try again.")

    recipient_metadata = load_user_metadata(recipient)
    challenges = _normalize_game_challenges(recipient_metadata.get("_game_challenges"))
    for entry in challenges:
        if (
            entry.get("status") == "pending"
            and normalize_username(entry.get("from", "")) == sender
            and str(entry.get("game", "")).lower() == game_key
        ):
            raise ValueError("You already have a pending challenge for this game.")

    challenge = {
        "id": str(uuid.uuid4()),
        "from": sender,
        "to": recipient,
        "game": game_key,
        "target": target_score,
        "status": "pending",
        "created_ts": time.time(),
        "resolved_ts": 0,
    }
    challenges.insert(0, challenge)
    recipient_metadata["_game_challenges"] = challenges[:CHALLENGE_MAX]
    save_user_metadata(recipient, recipient_metadata)
    add_notification(recipient, f"{sender} challenged you in {GAME_SCORE_LABELS[game_key]}: beat {target_score}.", "game")
    add_activity(sender, f"Sent {recipient} a {GAME_SCORE_LABELS[game_key]} challenge ({target_score})", "game")
    return _challenge_payload(challenge, sender)


def _pending_outgoing_game_challenges(username: str) -> list[dict[str, Any]]:
    current = normalize_username(username)
    account = _account_record(current)
    outgoing: list[dict[str, Any]] = []
    for friend in account.get("friends", []):
        metadata = load_user_metadata(friend)
        for challenge in _normalize_game_challenges(metadata.get("_game_challenges")):
            if challenge.get("from") != current:
                continue
            if challenge.get("status") != "pending":
                continue
            outgoing.append(_challenge_payload(challenge, current))
    outgoing.sort(key=lambda entry: float(entry.get("created_ts", 0)), reverse=True)
    return outgoing


def get_game_challenges(username: str) -> dict[str, Any]:
    current = normalize_username(username)
    metadata = load_user_metadata(current)
    challenges = _normalize_game_challenges(metadata.get("_game_challenges"))
    incoming = [
        _challenge_payload(entry, current)
        for entry in challenges
        if entry.get("status") == "pending" and entry.get("to") == current
    ]
    completed = [
        _challenge_payload(entry, current)
        for entry in challenges
        if entry.get("status") == "completed" and entry.get("to") == current
    ][:12]
    return {
        "incoming": incoming,
        "outgoing": _pending_outgoing_game_challenges(current),
        "completed": completed,
    }


def complete_game_challenges(username: str, game: str, score: int) -> list[dict[str, Any]]:
    current = normalize_username(username)
    game_key = str(game or "").strip().lower()
    if game_key not in GAME_SCORE_LABELS:
        return []
    try:
        safe_score = max(0, int(score))
    except (TypeError, ValueError):
        return []

    metadata = load_user_metadata(current)
    challenges = _normalize_game_challenges(metadata.get("_game_challenges"))
    completed: list[dict[str, Any]] = []
    changed = False
    now = time.time()
    for challenge in challenges:
        if challenge.get("status") != "pending":
            continue
        if challenge.get("to") != current:
            continue
        if challenge.get("game") != game_key:
            continue
        if safe_score < int(challenge.get("target", 0)):
            continue
        challenge["status"] = "completed"
        challenge["resolved_ts"] = now
        completed.append(dict(challenge))
        changed = True

    if not changed:
        return []

    metadata["_game_challenges"] = challenges[:CHALLENGE_MAX]
    save_user_metadata(current, metadata)
    for challenge in completed:
        sender = normalize_username(challenge.get("from", ""))
        label = GAME_SCORE_LABELS.get(game_key, game_key)
        target = int(challenge.get("target", 0))
        add_notification(current, f"Challenge complete: beat {target} in {label}.", "game")
        if sender and account_exists(sender):
            add_notification(sender, f"{current} completed your {label} challenge ({target}).", "game")
            add_activity(sender, f"{current} completed your {label} challenge ({target})", "game")
        add_activity(current, f"Completed {label} challenge from {sender} ({target})", "game")
    return [_challenge_payload(entry, current) for entry in completed]


def create_account(username: str, password: str) -> dict[str, Any]:
    normalized = normalize_username(username)
    if not valid_username(normalized):
        raise ValueError("Usernames must be 3-32 characters and use only letters, numbers, dashes, or underscores.")
    if len(password or "") < 6:
        raise ValueError("Passwords must be at least 6 characters long.")

    accounts = load_accounts()
    if normalized in accounts:
        raise ValueError("That username is already taken.")

    accounts[normalized] = {
        "username": normalized,
        "password_hash": generate_password_hash(password),
        "approved": False,
        "map_uploaded": False,
        "friends": [],
        "incoming_requests": [],
        "outgoing_requests": [],
    }
    save_accounts(accounts)
    metadata = load_user_metadata(normalized)
    metadata["_map_uploaded"] = False
    save_user_metadata(normalized, metadata)
    return {"username": normalized, "approved": False}


def authenticate_account(username: str, password: str) -> dict[str, Any]:
    normalized = normalize_username(username)
    accounts = load_accounts()
    account = accounts.get(normalized)
    if not isinstance(account, dict) or not check_password_hash(account.get("password_hash", ""), password or ""):
        raise ValueError("Invalid username or password.")
    return account


def list_pending_accounts() -> list[dict[str, Any]]:
    pending = []
    for account in load_accounts().values():
        if isinstance(account, dict) and not account.get("approved"):
            pending.append({"username": account.get("username", "")})
    pending.sort(key=lambda item: item["username"])
    return pending


def list_accounts() -> list[dict[str, Any]]:
    accounts_list = []
    for account in load_accounts().values():
        if not isinstance(account, dict):
            continue
        username = str(account.get("username", "")).strip()
        if not username:
            continue
        accounts_list.append(
            {
                "username": username,
                "approved": bool(account.get("approved")),
                "map_uploaded": bool(account.get("map_uploaded")),
                "friend_count": len(_unique_usernames(account.get("friends"))),
            }
        )
    accounts_list.sort(key=lambda item: item["username"])
    return accounts_list


def approve_account(username: str) -> None:
    normalized = normalize_username(username)
    accounts = load_accounts()
    account = accounts.get(normalized)
    if not isinstance(account, dict):
        raise ValueError("Account not found.")
    account["approved"] = True
    accounts[normalized] = account
    save_accounts(accounts)


def account_exists(username: str) -> bool:
    return normalize_username(username) in load_accounts()


def _account_record(username: str) -> dict[str, Any]:
    normalized = normalize_username(username)
    account = load_accounts().get(normalized)
    if not isinstance(account, dict):
        raise ValueError("Account not found.")
    return _normalize_account_record(normalized, account)


def send_friend_request(from_username: str, to_username: str) -> None:
    sender = normalize_username(from_username)
    recipient = normalize_username(to_username)
    if not sender or not recipient:
        raise ValueError("Enter a valid username.")
    if sender == recipient:
        raise ValueError("You can't add yourself.")

    accounts = load_accounts()
    sender_account = accounts.get(sender)
    recipient_account = accounts.get(recipient)
    if not isinstance(sender_account, dict):
        raise ValueError("Your account data couldn't be found. Try logging out and back in.")
    if not isinstance(recipient_account, dict):
        raise ValueError("No account exists with that username.")

    sender_account = _normalize_account_record(sender, sender_account)
    recipient_account = _normalize_account_record(recipient, recipient_account)

    if recipient in sender_account["friends"]:
        raise ValueError("You're already friends.")
    if recipient in sender_account["outgoing_requests"]:
        raise ValueError("Friend request already sent.")
    if sender in recipient_account["incoming_requests"]:
        raise ValueError("Friend request already sent.")

    sender_account["outgoing_requests"].append(recipient)
    recipient_account["incoming_requests"].append(sender)
    accounts[sender] = sender_account
    accounts[recipient] = recipient_account
    save_accounts(accounts)
    add_notification(recipient, f"New friend request from {sender}.", "friend")


def accept_friend_request(username: str, from_username: str) -> None:
    current = normalize_username(username)
    requester = normalize_username(from_username)
    accounts = load_accounts()
    current_account = accounts.get(current)
    requester_account = accounts.get(requester)
    if not isinstance(current_account, dict) or not isinstance(requester_account, dict):
        raise ValueError("Account not found.")

    current_account = _normalize_account_record(current, current_account)
    requester_account = _normalize_account_record(requester, requester_account)

    if requester not in current_account["incoming_requests"]:
        raise ValueError("No friend request from that user.")

    current_account["incoming_requests"] = [name for name in current_account["incoming_requests"] if name != requester]
    requester_account["outgoing_requests"] = [name for name in requester_account["outgoing_requests"] if name != current]

    if requester not in current_account["friends"]:
        current_account["friends"].append(requester)
    if current not in requester_account["friends"]:
        requester_account["friends"].append(current)

    accounts[current] = current_account
    accounts[requester] = requester_account
    save_accounts(accounts)


def remove_friend(username: str, friend_username: str) -> None:
    current = normalize_username(username)
    friend = normalize_username(friend_username)
    accounts = load_accounts()
    current_account = accounts.get(current)
    friend_account = accounts.get(friend)
    if not isinstance(current_account, dict) or not isinstance(friend_account, dict):
        raise ValueError("Account not found.")

    current_account = _normalize_account_record(current, current_account)
    friend_account = _normalize_account_record(friend, friend_account)

    if friend not in current_account["friends"]:
        raise ValueError("That user is not in your friends list.")

    current_account["friends"] = [name for name in current_account["friends"] if name != friend]
    friend_account["friends"] = [name for name in friend_account["friends"] if name != current]
    current_account["incoming_requests"] = [name for name in current_account["incoming_requests"] if name != friend]
    current_account["outgoing_requests"] = [name for name in current_account["outgoing_requests"] if name != friend]
    friend_account["incoming_requests"] = [name for name in friend_account["incoming_requests"] if name != current]
    friend_account["outgoing_requests"] = [name for name in friend_account["outgoing_requests"] if name != current]

    accounts[current] = current_account
    accounts[friend] = friend_account
    save_accounts(accounts)


def profile_summary(username: str, viewer_username: str | None = None) -> dict[str, Any]:
    normalized = normalize_username(username)
    try:
        account = _account_record(normalized)
    except ValueError:
        if viewer_username and normalize_username(viewer_username) == normalized:
            account = {
                "username": normalized,
                "approved": True,
                "map_uploaded": account_uses_personal_map(normalized),
                "friends": [],
                "incoming_requests": [],
                "outgoing_requests": [],
            }
        else:
            raise
    stats = stats_summary(normalized)
    friends = []
    for friend_name in account.get("friends", []):
        if not account_exists(friend_name):
            continue
        friends.append(
            {
                "username": friend_name,
                "stats": stats_summary(friend_name),
                "high_scores": get_user_high_scores(friend_name),
                "progression": progression_summary(friend_name),
            }
        )

    payload = {
        "username": normalized,
        "stats": stats,
        "friends": friends,
        "high_scores": get_user_high_scores(normalized),
        "progression": progression_summary(normalized),
    }

    if viewer_username and normalize_username(viewer_username) == normalized:
        payload["incoming_requests"] = [
            {"username": requester}
            for requester in account.get("incoming_requests", [])
            if account_exists(requester)
        ]
        payload["outgoing_requests"] = [
            {"username": recipient}
            for recipient in account.get("outgoing_requests", [])
            if account_exists(recipient)
        ]
        payload["game_challenges"] = get_game_challenges(normalized)

    return payload


def delete_account(username: str) -> None:
    normalized = normalize_username(username)
    if not normalized:
        raise ValueError("Account not found.")
    if normalized == "witch":
        raise ValueError("The witch account cannot be deleted.")

    accounts = load_accounts()
    if normalized not in accounts:
        raise ValueError("Account not found.")

    accounts.pop(normalized, None)
    save_accounts(accounts)

    metadata_path = user_metadata_path(normalized)
    account_path = user_account_path(normalized)
    upload_path = user_upload_dir(normalized)
    user_dir = os.path.dirname(metadata_path)

    if os.path.isdir(upload_path):
        shutil.rmtree(upload_path, ignore_errors=True)
    if os.path.isfile(metadata_path):
        try:
            os.remove(metadata_path)
        except OSError:
            pass
    if os.path.isfile(account_path):
        try:
            os.remove(account_path)
        except OSError:
            pass
    if os.path.isdir(user_dir):
        shutil.rmtree(user_dir, ignore_errors=True)


def mark_account_map_uploaded(username: str) -> None:
    normalized = normalize_username(username)
    metadata = load_user_metadata(normalized)
    metadata["_map_uploaded"] = True
    save_user_metadata(normalized, metadata)

    accounts = load_accounts()
    account = accounts.get(normalized)
    if isinstance(account, dict):
        account["map_uploaded"] = True
        accounts[normalized] = account
        save_accounts(accounts)


def account_uses_personal_map(username: str | None) -> bool:
    if not username:
        return False
    metadata = load_user_metadata(username)
    if isinstance(metadata, dict) and "_map_uploaded" in metadata:
        return True
    account = load_accounts().get(normalize_username(username))
    if not isinstance(account, dict):
        return True
    if "map_uploaded" not in account:
        return False
    return True


def include_shared_map(username: str | None) -> bool:
    if not username:
        return True
    metadata = load_user_metadata(username)
    if isinstance(metadata, dict) and "_map_uploaded" in metadata:
        return False
    account = load_accounts().get(normalize_username(username))
    if not isinstance(account, dict):
        return False
    if "map_uploaded" not in account:
        return True
    return False


def get_user_origin(username: str | None) -> tuple[float, float]:
    metadata = load_user_metadata(username)
    origin = metadata.get("_origin", {}) if isinstance(metadata, dict) else {}
    lat = origin.get("lat")
    lon = origin.get("lon")
    try:
        return float(lat), float(lon)
    except (TypeError, ValueError):
        return BASE_LAT, BASE_LON


def save_user_origin(username: str, lat: float, lon: float) -> None:
    metadata = load_user_metadata(username)
    metadata["_origin"] = {"lat": float(lat), "lon": float(lon)}
    save_user_metadata(username, metadata)


def _normalize_measurement_points(points: Any) -> list[list[float]]:
    normalized: list[list[float]] = []
    if not isinstance(points, list):
        return normalized
    for point in points:
        if not isinstance(point, (list, tuple)) or len(point) < 2:
            continue
        try:
            lat = round(float(point[0]), 6)
            lon = round(float(point[1]), 6)
        except (TypeError, ValueError):
            continue
        normalized.append([lat, lon])
    return normalized


def _normalize_measurement_line(item: Any, *, default_source: str) -> dict[str, Any] | None:
    if not isinstance(item, dict):
        return None
    points = _normalize_measurement_points(item.get("points"))
    if len(points) < 2:
        return None
    name = clean_description(str(item.get("name", "")).strip()) or "Measurement Line"
    line_id = str(item.get("id", "")).strip() or str(uuid.uuid4())
    color = str(item.get("color", "")).strip() or "#fbc02d"
    source = str(item.get("source", "")).strip() or default_source
    return {
        "id": line_id,
        "name": name,
        "points": points,
        "color": color,
        "source": source,
    }


def get_shared_measurement_lines() -> list[dict[str, Any]]:
    if not os.path.exists(SHARED_MEASUREMENT_LINES_FILE):
        return []
    try:
        stamp = os.path.getmtime(SHARED_MEASUREMENT_LINES_FILE)
    except OSError:
        stamp = None
    with _CACHE_LOCK:
        if _SHARED_MEASUREMENT_LINES_CACHE.get("stamp") == stamp:
            cached = _SHARED_MEASUREMENT_LINES_CACHE.get("value", [])
            return [dict(item) for item in cached]
    try:
        with open(SHARED_MEASUREMENT_LINES_FILE, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError):
        payload = []
    lines = []
    if isinstance(payload, list):
        for item in payload:
            normalized = _normalize_measurement_line(item, default_source="shared")
            if normalized:
                lines.append(normalized)
    with _CACHE_LOCK:
        _SHARED_MEASUREMENT_LINES_CACHE["stamp"] = stamp
        _SHARED_MEASUREMENT_LINES_CACHE["value"] = [dict(item) for item in lines]
    return lines


def get_user_measurement_lines(username: str | None) -> list[dict[str, Any]]:
    metadata = load_user_metadata(username)
    payload = metadata.get("_measurement_lines", [])
    if not isinstance(payload, list):
        return []
    lines = []
    for item in payload:
        normalized = _normalize_measurement_line(item, default_source="user")
        if normalized:
            lines.append(normalized)
    return lines


def get_map_measurement_lines(username: str | None) -> list[dict[str, Any]]:
    return get_shared_measurement_lines() + get_user_measurement_lines(username)


def save_user_measurement_line(username: str, name: str, points: Any, color: str = "#fbc02d") -> dict[str, Any]:
    normalized_name = clean_description(name).strip() or f"Measurement {datetime.now().strftime('%H:%M')}"
    normalized_points = _normalize_measurement_points(points)
    if len(normalized_points) < 2:
        raise ValueError("A measurement line needs at least 2 points.")
    metadata = load_user_metadata(username)
    existing = metadata.get("_measurement_lines", [])
    if not isinstance(existing, list):
        existing = []
    line = {
        "id": str(uuid.uuid4()),
        "name": normalized_name,
        "points": normalized_points,
        "color": str(color or "#fbc02d").strip() or "#fbc02d",
        "source": "user",
    }
    existing.append(line)
    metadata["_measurement_lines"] = existing
    save_user_metadata(username, metadata)
    return line


def delete_user_measurement_line(username: str, line_id: str) -> bool:
    target = str(line_id or "").strip()
    if not target:
        return False
    metadata = load_user_metadata(username)
    existing = metadata.get("_measurement_lines", [])
    if not isinstance(existing, list) or not existing:
        return False
    kept = [item for item in existing if str(item.get("id", "")).strip() != target]
    if len(kept) == len(existing):
        return False
    metadata["_measurement_lines"] = kept
    save_user_metadata(username, metadata)
    return True


def distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_km = 6371
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return radius_km * c


def km_to_drive_minutes(km: float, speed_kmh: float = 50) -> int:
    return int(round((km / speed_kmh) * 60))


def format_minutes(minutes: float) -> str:
    rounded = int(round(minutes))
    if rounded < 60:
        return f"{rounded} min"
    hours = rounded // 60
    mins = rounded % 60
    if mins == 0:
        return f"{hours}h"
    return f"{hours}h {mins}m"


def load_metadata() -> dict[str, Any]:
    bootstrap_metadata_file()
    try:
        stamp = os.path.getmtime(DATA_FILE)
    except OSError:
        stamp = None
    with _CACHE_LOCK:
        if _METADATA_CACHE.get("stamp") == stamp:
            cached = _METADATA_CACHE.get("value", {})
            if isinstance(cached, dict):
                return dict(cached)
    with open(DATA_FILE, "r", encoding="utf-8") as handle:
        loaded = json.load(handle)
    if not isinstance(loaded, dict):
        loaded = {}
    with _CACHE_LOCK:
        _METADATA_CACHE["stamp"] = stamp
        _METADATA_CACHE["value"] = dict(loaded)
    return loaded


def save_metadata(data: dict[str, Any]) -> None:
    with _LOCK:
        ensure_runtime_dirs()
        with open(DATA_FILE, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, ensure_ascii=False)
    try:
        stamp = os.path.getmtime(DATA_FILE)
    except OSError:
        stamp = None
    with _CACHE_LOCK:
        _METADATA_CACHE["stamp"] = stamp
        _METADATA_CACHE["value"] = dict(data)


def clean_description(description: str | None) -> str:
    if not description:
        return ""
    return re.sub(r"<.*?>", "", description).strip()


def is_valid_name(name: str) -> bool:
    lowered = name.lower()
    blocked = [
        "untitled measurement",
        "pipe",
        "line",
        "chamber",
        "split",
        "north",
        "south",
        "northern",
        "southern",
        "upstream",
        "manhole",
        "grille",
        "grill",
        "room",
        "junction",
        "links",
        "exit",
        "potentially",
        "here",
        "maybe",
        "potential",
        "new",
        "small",
        "massive",
    ]
    return not any(word in lowered for word in blocked)


def _parse_kml_drains() -> list[dict[str, Any]]:
    bootstrap_kml_file()
    if not os.path.exists(KML_FILE):
        return []
    try:
        stamp = os.path.getmtime(KML_FILE)
    except OSError:
        stamp = None
    with _CACHE_LOCK:
        if _KML_DRAINS_CACHE.get("stamp") == stamp:
            cached = _KML_DRAINS_CACHE.get("value", [])
            return [dict(item) for item in cached]

    tree = ET.parse(KML_FILE)
    root = tree.getroot()
    drains = _parse_kml_root(root)
    with _CACHE_LOCK:
        _KML_DRAINS_CACHE["stamp"] = stamp
        _KML_DRAINS_CACHE["value"] = [dict(item) for item in drains]
    return drains


def _parse_kml_root(root: ET.Element) -> list[dict[str, Any]]:
    ns = {"kml": "http://www.opengis.net/kml/2.2"}
    drains: list[dict[str, Any]] = []
    seen: set[str] = set()
    seen_coords: set[tuple[float, float]] = set()

    for placemark in root.findall(".//kml:Placemark", ns):
        name_elem = placemark.find("kml:name", ns)
        coords_elem = placemark.find(".//kml:Point/kml:coordinates", ns)
        desc_elem = placemark.find("kml:description", ns)

        if name_elem is None or coords_elem is None:
            continue

        name = (name_elem.text or "Unnamed").strip()
        if not is_valid_name(name):
            continue

        dedupe_key = name.casefold()
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)

        coord_text = coords_elem.text.strip().split()[0]
        lon, lat, _alt = map(float, coord_text.split(","))
        coord_key = (round(lat, 7), round(lon, 7))
        if coord_key in seen_coords:
            continue
        seen_coords.add(coord_key)
        drains.append(
            {
                "name": name,
                "lat": lat,
                "lon": lon,
                "description": clean_description(desc_elem.text if desc_elem is not None else ""),
                "source": "kml",
                "custom": False,
            }
        )

    return drains


def _parse_kml_bytes_to_drains(payload: bytes) -> list[dict[str, Any]]:
    root = ET.fromstring(payload)
    return _parse_kml_root(root)


def _extract_drive_file_id(value: str) -> str | None:
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme and parsed.netloc:
        if parsed.netloc.endswith("google.com"):
            parts = [part for part in parsed.path.split("/") if part]
            if "d" in parts:
                index = parts.index("d")
                if index + 1 < len(parts):
                    return parts[index + 1]
            query_id = urllib.parse.parse_qs(parsed.query).get("id")
            if query_id:
                return query_id[0]
    if re.fullmatch(r"[-\w]{20,}", value.strip()):
        return value.strip()
    return None


def _kml_download_url(source: str) -> str:
    file_id = _extract_drive_file_id(source)
    if file_id:
        return f"https://drive.google.com/uc?export=download&id={file_id}"
    return source


def _extract_kml_bytes(payload: bytes) -> bytes:
    if zipfile.is_zipfile(io.BytesIO(payload)):
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            kml_names = [name for name in archive.namelist() if name.lower().endswith(".kml")]
            if not kml_names:
                raise ValueError("The synced file was a ZIP/KMZ archive without a KML inside.")
            with archive.open(kml_names[0]) as handle:
                return handle.read()

    trimmed = payload.lstrip()
    if trimmed.startswith(b"<?xml") or b"<kml" in trimmed[:4096].lower():
        return payload

    preview = trimmed[:200].decode("utf-8", errors="ignore").lower()
    if "<html" in preview or "<!doctype" in preview:
        raise ValueError("Google returned an HTML page instead of a KML/KMZ file. Check that the shared file is directly downloadable.")

    raise ValueError("The synced file was not a KML or KMZ.")


def _drain_identity_key(name: str, lat: float, lon: float) -> tuple[str, float, float]:
    return (name.casefold(), round(float(lat), 7), round(float(lon), 7))


def sync_kml_payload(username: str, payload: bytes) -> dict[str, Any]:
    kml_bytes = _extract_kml_bytes(payload)
    imported_drains = _parse_kml_bytes_to_drains(kml_bytes)
    before_total = len(get_all_drains(username))
    metadata = load_user_metadata(username)
    existing_keys = {
        _drain_identity_key(drain["name"], drain["lat"], drain["lon"])
        for drain in get_all_drains(username)
    }
    added = 0
    added_names: list[str] = []

    for drain in imported_drains:
        key = _drain_identity_key(drain["name"], drain["lat"], drain["lon"])
        if key in existing_keys:
            continue

        current = metadata.get(drain["name"], {})
        if not isinstance(current, dict):
            current = {}

        current["synced"] = True
        current["lat"] = drain["lat"]
        current["lon"] = drain["lon"]
        current["description"] = drain.get("description", "")
        metadata[drain["name"]] = current
        existing_keys.add(key)
        added += 1
        added_names.append(drain["name"])

    metadata["_last_sync_added"] = added_names
    if added:
        mark_account_map_uploaded(username)
    save_user_metadata(username, metadata)
    after_total = len(get_all_drains(username))
    visible_added = max(0, after_total - before_total)

    return {
        "ok": True,
        "count": len(imported_drains),
        "added": visible_added,
    }


def sync_kml_from_source(username: str, source: str | None = None) -> dict[str, Any]:
    sync_source = (source or KML_SYNC_URL or "").strip()
    if not sync_source:
        raise ValueError("No sync URL is configured.")

    request = urllib.request.Request(
        _kml_download_url(sync_source),
        headers={
            "User-Agent": "DrainBot/1.0 (+https://github.com/w1tch33/Drain-Bot)",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = response.read()
    except urllib.error.URLError as error:
        raise ValueError(f"Could not download the KML source: {error}") from error

    result = sync_kml_payload(username, payload)
    result["source_url"] = sync_source
    return result


def undo_last_sync(username: str) -> dict[str, Any]:
    metadata = load_user_metadata(username)
    added_names = metadata.get("_last_sync_added", [])
    if not isinstance(added_names, list) or not added_names:
        return {"removed": 0}

    removed = 0
    for name in added_names:
        item = metadata.get(name)
        if isinstance(item, dict) and item.get("synced"):
            metadata.pop(name, None)
            removed += 1

    metadata["_last_sync_added"] = []
    save_user_metadata(username, metadata)
    return {"removed": removed}


def _custom_drains(metadata: dict[str, Any]) -> list[dict[str, Any]]:
    drains: list[dict[str, Any]] = []
    for name, item in metadata.items():
        if str(name).startswith("_"):
            continue
        if not isinstance(item, dict) or not (item.get("custom") or item.get("synced")):
            continue
        lat = item.get("lat")
        lon = item.get("lon")
        if lat is None or lon is None:
            continue
        drains.append(
            {
                "name": name,
                "lat": lat,
                "lon": lon,
                "description": clean_description(item.get("description", "")),
                "source": "synced" if item.get("synced") else "custom",
                "custom": bool(item.get("custom")),
            }
        )
    return drains


def _merge_metadata(base: dict[str, Any], item: dict[str, Any] | None) -> dict[str, Any]:
    merged = dict(base)
    meta = item if isinstance(item, dict) else {}
    merged["storage_name"] = base.get("name", "")
    if meta.get("display_name"):
        merged["name"] = str(meta.get("display_name", "")).strip() or merged["name"]
    if meta.get("description"):
        merged["description"] = meta["description"]
    merged["visited"] = bool(meta.get("visited"))
    merged["favorite"] = bool(meta.get("favorite"))
    merged["difficulty"] = meta.get("difficulty", "")
    merged["rating"] = meta.get("rating")
    merged["value"] = meta.get("value", "")
    merged["photos"] = [p for p in meta.get("photos", []) if isinstance(p, str)]
    merged["notes"] = meta.get("witch_notes") or meta.get("notes") or ""
    merged["features"] = meta.get("features", {})
    return merged


def resolve_storage_name(name: str, username: str | None = None) -> str | None:
    for drain in get_all_drains(username):
        if drain["name"] == name:
            return str(drain.get("storage_name") or drain["name"])
    return None


def _apply_origin(drain: dict[str, Any], origin_lat: float, origin_lon: float) -> dict[str, Any]:
    merged = dict(drain)
    dist = distance_km(origin_lat, origin_lon, float(merged["lat"]), float(merged["lon"]))
    merged["distance_km"] = round(dist, 2)
    merged["drive_minutes"] = km_to_drive_minutes(dist)
    return merged


def _source_rank(source: str) -> int:
    return {"custom": 0, "synced": 1, "kml": 2}.get(source, 9)


def get_all_drains(username: str | None = None) -> list[dict[str, Any]]:
    metadata = load_metadata()
    user_metadata = load_user_metadata(username)
    origin = user_metadata.get("_origin", {}) if isinstance(user_metadata, dict) else {}
    try:
        origin_lat = float(origin.get("lat"))
        origin_lon = float(origin.get("lon"))
    except (TypeError, ValueError):
        origin_lat, origin_lon = BASE_LAT, BASE_LON
    if not username:
        shared_map_enabled = True
    elif isinstance(user_metadata, dict) and "_map_uploaded" in user_metadata:
        shared_map_enabled = False
    else:
        account = load_accounts().get(normalize_username(username))
        if not isinstance(account, dict):
            shared_map_enabled = False
        elif "map_uploaded" not in account:
            shared_map_enabled = True
        else:
            shared_map_enabled = False
    combined: dict[str, dict[str, Any]] = {}

    if shared_map_enabled:
        for drain in _parse_kml_drains():
            combined[drain["name"]] = drain

    if shared_map_enabled:
        for drain in _custom_drains(metadata):
            combined[drain["name"]] = drain

    for drain in _custom_drains(user_metadata):
        combined[drain["name"]] = drain

    merged_raw = []
    for drain in combined.values():
        merged_item = _merge_metadata(drain, metadata.get(drain["name"]))
        merged_item = _merge_metadata(merged_item, user_metadata.get(drain["name"]))
        merged_raw.append(_apply_origin(merged_item, origin_lat, origin_lon))

    deduped_by_coords: dict[tuple[float, float], dict[str, Any]] = {}
    for drain in merged_raw:
        key = (round(float(drain["lat"]), 7), round(float(drain["lon"]), 7))
        current = deduped_by_coords.get(key)
        if current is None or _source_rank(drain.get("source", "")) < _source_rank(current.get("source", "")):
            deduped_by_coords[key] = drain

    merged = list(deduped_by_coords.values())
    merged.sort(key=lambda item: item["distance_km"])
    return merged


def get_drain(name: str, username: str | None = None) -> dict[str, Any] | None:
    for drain in get_all_drains(username):
        if drain["name"] == name:
            return drain
    return None


def random_drain(
    username: str | None = None,
    min_distance: float = 0,
    max_distance: float = 100,
    only_unvisited: bool = False,
    only_visited: bool = False,
) -> dict[str, Any] | None:
    candidates = filter_drains(username, min_distance, max_distance, only_unvisited, only_visited=only_visited)
    if not candidates:
        return None
    return random.choice(candidates)


def filter_drains(
    username: str | None = None,
    min_distance: float = 0,
    max_distance: float = 60,
    only_unvisited: bool = False,
    search: str = "",
    only_visited: bool = False,
) -> list[dict[str, Any]]:
    drains = []
    term = search.strip().casefold()
    words = [part for part in re.split(r"\s+", term) if part]

    for drain in get_all_drains(username):
        if drain["distance_km"] < min_distance or drain["distance_km"] > max_distance:
            continue
        if only_unvisited and drain["visited"]:
            continue
        if only_visited and not drain["visited"]:
            continue
        if term:
            name_text = drain["name"].casefold()
            description_text = str(drain.get("description", "")).casefold()
            notes_text = str(drain.get("notes", "")).casefold()
            exact_name = term == name_text
            phrase_in_name = term in name_text
            all_words_in_name = bool(words) and all(word in name_text for word in words)
            phrase_in_description = len(term) >= 4 and term in description_text
            phrase_in_notes = len(term) >= 4 and term in notes_text
            if not (exact_name or phrase_in_name or all_words_in_name or phrase_in_description or phrase_in_notes):
                continue
        drains.append(drain)

    return drains


def recommend_session(
    username: str | None = None,
    session_type: str = "long",
    min_distance: float = 0,
    max_distance: float = 60,
    only_unvisited: bool = False,
    only_visited: bool = False,
) -> dict[str, Any]:
    candidates = filter_drains(username, min_distance, max_distance, only_unvisited, only_visited=only_visited)
    if not candidates:
        return {"primary": None, "route": [], "options": []}

    primary = random.choice(candidates)
    nearby = sorted(
        [d for d in candidates if d["name"] != primary["name"]],
        key=lambda item: distance_km(primary["lat"], primary["lon"], item["lat"], item["lon"]),
    )
    route_count = 2 if session_type == "short" else 4
    route = [primary] + nearby[:route_count]

    options = [d for d in candidates if d["name"] not in {item["name"] for item in route}][:5]
    return {"primary": primary, "route": route, "options": options}


def build_route_plan(
    username: str | None = None,
    min_distance: float = 0,
    max_distance: float = 60,
    only_unvisited: bool = False,
    only_visited: bool = False,
    stop_limit: int = 4,
    max_leg_km: float = 5,
    max_total_minutes: float = 120,
) -> dict[str, Any]:
    pool = filter_drains(username, min_distance, max_distance, only_unvisited, only_visited=only_visited)
    if len(pool) < 2:
        return {"route": [], "total_minutes": 0, "total_distance_km": 0}

    shuffled = pool[:]
    random.shuffle(shuffled)

    route = [shuffled[0]]
    total_minutes = route[0]["drive_minutes"]
    total_distance = 0.0

    for candidate in shuffled[1:]:
        last = route[-1]
        leg_distance = distance_km(last["lat"], last["lon"], candidate["lat"], candidate["lon"])
        if leg_distance > max_leg_km:
            continue

        leg_minutes = km_to_drive_minutes(leg_distance)
        if total_minutes + leg_minutes > max_total_minutes:
            continue

        route.append(candidate)
        total_minutes += leg_minutes
        total_distance += leg_distance

        if len(route) >= stop_limit:
            break

    if len(route) < 2:
        return {"route": [], "total_minutes": 0, "total_distance_km": 0}

    ordered = [route[0]] + sorted(
        route[1:],
        key=lambda item: distance_km(route[0]["lat"], route[0]["lon"], item["lat"], item["lon"]),
    )

    return {
        "route": ordered,
        "total_minutes": int(round(total_minutes)),
        "total_distance_km": round(total_distance, 2),
    }


def nearby_drains(name: str, username: str | None = None, limit: int = 3, radius_km: float = 5) -> list[dict[str, Any]]:
    current = get_drain(name, username)
    if not current:
        return []

    nearby: list[dict[str, Any]] = []
    for drain in get_all_drains(username):
        if drain["name"] == name:
            continue
        dist = distance_km(current["lat"], current["lon"], drain["lat"], drain["lon"])
        if dist <= radius_km:
            enriched = dict(drain)
            enriched["distance_from_current_km"] = round(dist, 2)
            nearby.append(enriched)

    nearby.sort(key=lambda item: item["distance_from_current_km"])
    return nearby[:limit]


def route_from_drain(name: str, username: str | None = None, radius_km: float = 5, stop_limit: int = 4) -> dict[str, Any]:
    start = get_drain(name, username)
    if not start:
        return {"route": [], "total_minutes": 0, "total_distance_km": 0}

    nearby = nearby_drains(name, username, limit=max(0, stop_limit - 1), radius_km=radius_km)
    route = [start] + nearby
    if len(route) < 2:
        return {"route": [], "total_minutes": 0, "total_distance_km": 0}

    total_minutes = 0
    total_distance = 0.0
    for index in range(1, len(route)):
        prev = route[index - 1]
        current = route[index]
        leg_distance = distance_km(prev["lat"], prev["lon"], current["lat"], current["lon"])
        total_distance += leg_distance
        total_minutes += km_to_drive_minutes(leg_distance)

    return {
        "route": route,
        "total_minutes": total_minutes,
        "total_distance_km": round(total_distance, 2),
    }


def stats_summary(username: str | None = None) -> dict[str, int]:
    drains = get_all_drains(username)
    return {
        "total": len(drains),
        "visited": sum(1 for item in drains if item["visited"]),
        "favorites": sum(1 for item in drains if item["favorite"]),
        "custom": sum(1 for item in drains if item["custom"]),
    }


def update_drain(
    name: str,
    username: str | None = None,
    *,
    display_name: str | None = None,
    visited: bool | None = None,
    favorite: bool | None = None,
    description: str | None = None,
    difficulty: str | None = None,
    value: str | None = None,
    rating: int | None = None,
    notes: str | None = None,
    features: dict[str, Any] | None = None,
) -> bool:
    if not username:
        raise ValueError("A user account is required.")
    metadata = load_user_metadata(username)
    storage_name = resolve_storage_name(name, username) or name
    current = metadata.get(storage_name, {})
    if not isinstance(current, dict):
        current = {}

    if display_name is not None:
        cleaned_name = display_name.strip()
        current["display_name"] = cleaned_name or storage_name

    if visited is not None:
        current["visited"] = 1 if visited else 0
    if favorite is not None:
        current["favorite"] = 1 if favorite else 0
    if description is not None:
        current["description"] = description.strip()
    if difficulty is not None:
        current["difficulty"] = difficulty
    if value is not None:
        current["value"] = value
    if rating is not None:
        current["rating"] = rating
    if notes is not None:
        current["witch_notes"] = notes.strip()
    if features is not None:
        current["features"] = {key: 1 if value else 0 for key, value in features.items()}

    metadata[storage_name] = current
    save_user_metadata(username, metadata)
    return True


def add_custom_drain(username: str, name: str, lat: float, lon: float, description: str = "") -> None:
    metadata = load_user_metadata(username)
    current = metadata.get(name, {})
    if not isinstance(current, dict):
        current = {}

    current["custom"] = True
    current["lat"] = lat
    current["lon"] = lon
    if description.strip():
        current["description"] = description.strip()

    metadata[name] = current
    save_user_metadata(username, metadata)


def ensure_upload_dir() -> None:
    ensure_runtime_dirs()


def normalize_photo_path(path: str) -> str:
    normalized = path.replace("\\", "/")
    if normalized.startswith("uploads/"):
        return normalized
    if os.path.isabs(path):
        return path
    return normalized


def resolve_photo_asset(path: str) -> dict[str, Any]:
    normalized = normalize_photo_path(path)

    if normalized.startswith("uploads/"):
        relative_upload = normalized.removeprefix("uploads/").replace("/", os.sep)
        absolute = os.path.join(UPLOAD_DIR, relative_upload)
        return {
            "path": normalized,
            "url": f"/{normalized}",
            "kind": "uploaded",
            "available": os.path.exists(absolute),
            "filename": os.path.basename(normalized),
        }

    basename = os.path.basename(normalized)

    if os.path.isabs(path) and os.path.exists(path):
        return {
            "path": normalized,
            "url": f"/photo-file/{basename}",
            "kind": "local",
            "available": True,
            "filename": basename,
        }

    for candidate_dir in PHOTO_DIR_CANDIDATES:
        candidate_path = os.path.join(candidate_dir, basename)
        if os.path.exists(candidate_path):
            rel = os.path.relpath(candidate_path, BASE_DIR).replace("\\", "/")
            return {
                "path": rel,
                "url": f"/photo-file/{basename}",
                "kind": "local",
                "available": True,
                "filename": basename,
            }

    return {
        "path": normalized,
        "url": "",
        "kind": "local",
        "available": False,
        "filename": basename,
    }


def list_photos(name: str, username: str | None = None) -> list[dict[str, Any]]:
    drain = get_drain(name, username)
    if not drain:
        return []

    return [resolve_photo_asset(photo) for photo in drain.get("photos", [])]


def find_photo_file(filename: str) -> str | None:
    upload_path = os.path.join(UPLOAD_DIR, filename)
    if os.path.exists(upload_path):
        return upload_path

    for candidate_dir in PHOTO_DIR_CANDIDATES:
        candidate_path = os.path.join(candidate_dir, filename)
        if os.path.exists(candidate_path):
            return candidate_path

    return None


def add_uploaded_photo(name: str, username: str, relative_path: str) -> None:
    metadata = load_user_metadata(username)
    current = metadata.get(name, {})
    if not isinstance(current, dict):
        current = {}
    current.setdefault("photos", [])
    current["photos"].append(normalize_photo_path(relative_path))
    metadata[name] = current
    save_user_metadata(username, metadata)


def remove_photo(name: str, username: str, path: str) -> None:
    metadata = load_user_metadata(username)
    current = metadata.get(name, {})
    if not isinstance(current, dict):
        return
    photos = [normalize_photo_path(photo) for photo in current.get("photos", [])]
    target = normalize_photo_path(path)
    current["photos"] = [photo for photo in photos if photo != target]
    metadata[name] = current
    save_user_metadata(username, metadata)

    if target.startswith("uploads/"):
        absolute = os.path.join(UPLOAD_DIR, target.removeprefix("uploads/").replace("/", os.sep))
        if os.path.exists(absolute):
            os.remove(absolute)


def delete_user_drain(username: str, name: str) -> bool:
    metadata = load_user_metadata(username)
    storage_name = resolve_storage_name(name, username) or name
    current = metadata.get(storage_name)
    if not isinstance(current, dict):
        return False
    if not (current.get("custom") or current.get("synced")):
        return False

    for photo in [normalize_photo_path(photo) for photo in current.get("photos", [])]:
        if photo.startswith("uploads/"):
            absolute = os.path.join(UPLOAD_DIR, photo.removeprefix("uploads/").replace("/", os.sep))
            if os.path.exists(absolute):
                os.remove(absolute)

    metadata.pop(storage_name, None)
    save_user_metadata(username, metadata)
    return True


def result_rows(
    drains: list[dict[str, Any]],
    *,
    include_drive_time: bool = True,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for drain in drains:
        rows.append(
            {
                "name": drain["name"],
                "distance_km": round(drain["distance_km"], 1),
                "drive_time_text": format_minutes(drain["drive_minutes"]) if include_drive_time else "",
                "visited": drain.get("visited", False),
                "favorite": drain.get("favorite", False),
            }
        )
    return rows


def session_results(
    username: str | None = None,
    session_type: str = "long",
    min_distance: float = 0,
    max_distance: float = 60,
    only_unvisited: bool = False,
    only_visited: bool = False,
) -> list[dict[str, Any]]:
    recommendation = recommend_session(username, session_type, min_distance, max_distance, only_unvisited, only_visited)
    ordered: list[dict[str, Any]] = []
    seen: set[str] = set()
    for bucket in ("primary", "route", "options"):
        items = recommendation.get(bucket)
        if not items:
            continue
        if isinstance(items, dict):
            items = [items]
        for item in items:
            if item["name"] in seen:
                continue
            seen.add(item["name"])
            ordered.append(item)
    return result_rows(ordered)


def search_results(username: str | None, query: str, only_unvisited: bool = False, only_visited: bool = False) -> list[dict[str, Any]]:
    term = str(query or "").strip().casefold()
    if len(term) < 2:
        return []
    words = [piece for piece in re.split(r"\s+", term) if piece]
    ranked: list[tuple[int, dict[str, Any]]] = []
    for drain in get_all_drains(username):
        if only_unvisited and drain.get("visited"):
            continue
        if only_visited and not drain.get("visited"):
            continue
        name_text = str(drain.get("name", "")).casefold()
        score = 0
        if term == name_text:
            score = 200
        elif name_text.startswith(term):
            score = 150
        elif words and all(word in name_text for word in words):
            score = 120
        elif term in name_text:
            score = 90
        elif len(term) >= 5:
            description_text = str(drain.get("description", "")).casefold()
            notes_text = str(drain.get("notes", "")).casefold()
            if term in description_text:
                score = 40
            elif term in notes_text:
                score = 24
        if score <= 0:
            continue
        ranked.append((score, drain))
    ranked.sort(key=lambda item: (-item[0], float(item[1].get("distance_km", 99999)), str(item[1].get("name", ""))))
    top = [item[1] for item in ranked[:40]]
    return result_rows(top)


def visited_results(username: str | None) -> list[dict[str, Any]]:
    visited = [drain for drain in get_all_drains(username) if bool(drain.get("visited"))]
    visited.sort(key=lambda item: str(item.get("name", "")).casefold())
    return result_rows(visited)


def google_earth_url(lat: float, lon: float, name: str) -> str:
    return f"https://earth.google.com/web/search/{lat},{lon}"
