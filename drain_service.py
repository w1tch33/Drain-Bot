import json
import io
import math
import os
import random
import re
import shutil
import threading
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
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
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def save_user_metadata(username: str, data: dict[str, Any]) -> None:
    ensure_user_dirs(username)
    with _LOCK:
        with open(user_metadata_path(username), "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, ensure_ascii=False)


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
    if not isinstance(sender_account, dict) or not isinstance(recipient_account, dict):
        raise ValueError("That username doesn't exist.")

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
            }
        )

    payload = {
        "username": normalized,
        "stats": stats,
        "friends": friends,
        "high_scores": {},
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
    with open(DATA_FILE, "r", encoding="utf-8") as handle:
        return json.load(handle)


def save_metadata(data: dict[str, Any]) -> None:
    with _LOCK:
        ensure_runtime_dirs()
        with open(DATA_FILE, "w", encoding="utf-8") as handle:
            json.dump(data, handle, indent=2, ensure_ascii=False)


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

    tree = ET.parse(KML_FILE)
    root = tree.getroot()
    return _parse_kml_root(root)


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


def _apply_origin(drain: dict[str, Any], username: str | None) -> dict[str, Any]:
    merged = dict(drain)
    origin_lat, origin_lon = get_user_origin(username)
    dist = distance_km(origin_lat, origin_lon, float(merged["lat"]), float(merged["lon"]))
    merged["distance_km"] = round(dist, 2)
    merged["drive_minutes"] = km_to_drive_minutes(dist)
    return merged


def _source_rank(source: str) -> int:
    return {"custom": 0, "synced": 1, "kml": 2}.get(source, 9)


def get_all_drains(username: str | None = None) -> list[dict[str, Any]]:
    metadata = load_metadata()
    user_metadata = load_user_metadata(username)
    combined: dict[str, dict[str, Any]] = {}

    if include_shared_map(username):
        for drain in _parse_kml_drains():
            combined[drain["name"]] = drain

    if include_shared_map(username):
        for drain in _custom_drains(metadata):
            combined[drain["name"]] = drain

    for drain in _custom_drains(user_metadata):
        combined[drain["name"]] = drain

    merged_raw = []
    for drain in combined.values():
        merged_item = _merge_metadata(drain, metadata.get(drain["name"]))
        merged_item = _merge_metadata(merged_item, user_metadata.get(drain["name"]))
        merged_raw.append(_apply_origin(merged_item, username))

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
) -> dict[str, Any] | None:
    candidates = filter_drains(username, min_distance, max_distance, only_unvisited)
    if not candidates:
        return None
    return random.choice(candidates)


def filter_drains(
    username: str | None = None,
    min_distance: float = 0,
    max_distance: float = 60,
    only_unvisited: bool = False,
    search: str = "",
) -> list[dict[str, Any]]:
    drains = []
    term = search.strip().casefold()
    words = [part for part in re.split(r"\s+", term) if part]

    for drain in get_all_drains(username):
        if drain["distance_km"] < min_distance or drain["distance_km"] > max_distance:
            continue
        if only_unvisited and drain["visited"]:
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
) -> dict[str, Any]:
    candidates = filter_drains(username, min_distance, max_distance, only_unvisited)
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
    stop_limit: int = 4,
    max_leg_km: float = 5,
    max_total_minutes: float = 120,
) -> dict[str, Any]:
    pool = filter_drains(username, min_distance, max_distance, only_unvisited)
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
    current = metadata.get(name, {})
    if not isinstance(current, dict):
        current = {}

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

    metadata[name] = current
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
    current = metadata.get(name)
    if not isinstance(current, dict):
        return False
    if not (current.get("custom") or current.get("synced")):
        return False

    for photo in [normalize_photo_path(photo) for photo in current.get("photos", [])]:
        if photo.startswith("uploads/"):
            absolute = os.path.join(UPLOAD_DIR, photo.removeprefix("uploads/").replace("/", os.sep))
            if os.path.exists(absolute):
                os.remove(absolute)

    metadata.pop(name, None)
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
) -> list[dict[str, Any]]:
    recommendation = recommend_session(username, session_type, min_distance, max_distance, only_unvisited)
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


def search_results(username: str | None, query: str, only_unvisited: bool = False) -> list[dict[str, Any]]:
    drains = filter_drains(username, 0, 9999, only_unvisited, query)
    return result_rows(drains)


def google_earth_url(lat: float, lon: float, name: str) -> str:
    return f"https://earth.google.com/web/search/{lat},{lon}"
