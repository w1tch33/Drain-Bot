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


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DATA_FILE = os.path.join(BASE_DIR, "drain_data.json")
DEFAULT_KML_FILE = os.path.join(BASE_DIR, "your_map.kml")
DEFAULT_DATA_DIR = os.getenv("RAILWAY_VOLUME_MOUNT_PATH", BASE_DIR)
DATA_DIR = os.getenv("DRAINTOOL_DATA_DIR", DEFAULT_DATA_DIR)
DATA_FILE = os.getenv("DRAINTOOL_DATA_FILE", os.path.join(DATA_DIR, "drain_data.json"))
KML_FILE = os.getenv("DRAINTOOL_KML_FILE", os.path.join(DATA_DIR, "your_map.kml"))
UPLOAD_DIR = os.getenv("DRAINTOOL_UPLOAD_DIR", os.path.join(DATA_DIR, "uploads"))
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
    ]
    return not any(word in lowered for word in blocked)


def _parse_kml_drains() -> list[dict[str, Any]]:
    bootstrap_kml_file()
    if not os.path.exists(KML_FILE):
        return []

    tree = ET.parse(KML_FILE)
    root = tree.getroot()
    ns = {"kml": "http://www.opengis.net/kml/2.2"}
    drains: list[dict[str, Any]] = []
    seen: set[str] = set()

    for placemark in root.findall(".//kml:Placemark", ns):
        name_elem = placemark.find("kml:name", ns)
        coords_elem = placemark.find(".//kml:coordinates", ns)
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
        dist = distance_km(BASE_LAT, BASE_LON, lat, lon)

        drains.append(
            {
                "name": name,
                "lat": lat,
                "lon": lon,
                "distance_km": round(dist, 2),
                "drive_minutes": km_to_drive_minutes(dist),
                "description": clean_description(desc_elem.text if desc_elem is not None else ""),
                "source": "kml",
                "custom": False,
            }
        )

    return drains


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


def sync_kml_from_source(source: str | None = None) -> dict[str, Any]:
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

    kml_bytes = _extract_kml_bytes(payload)
    ensure_runtime_dirs()
    with open(KML_FILE, "wb") as handle:
        handle.write(kml_bytes)

    drains = _parse_kml_drains()
    return {
        "ok": True,
        "count": len(drains),
        "source_url": sync_source,
        "kml_file": KML_FILE,
    }


def _custom_drains(metadata: dict[str, Any]) -> list[dict[str, Any]]:
    drains: list[dict[str, Any]] = []
    for name, item in metadata.items():
        if not isinstance(item, dict) or not item.get("custom"):
            continue
        lat = item.get("lat")
        lon = item.get("lon")
        if lat is None or lon is None:
            continue
        dist = distance_km(BASE_LAT, BASE_LON, lat, lon)
        drains.append(
            {
                "name": name,
                "lat": lat,
                "lon": lon,
                "distance_km": round(dist, 2),
                "drive_minutes": km_to_drive_minutes(dist),
                "description": clean_description(item.get("description", "")),
                "source": "custom",
                "custom": True,
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
    merged["notes"] = meta.get("witch_notes") or meta.get("description", "") or merged.get("description", "")
    merged["features"] = meta.get("features", {})
    return merged


def get_all_drains() -> list[dict[str, Any]]:
    metadata = load_metadata()
    combined: dict[str, dict[str, Any]] = {}

    for drain in _parse_kml_drains():
        combined[drain["name"]] = drain

    for drain in _custom_drains(metadata):
        combined[drain["name"]] = drain

    merged = [_merge_metadata(drain, metadata.get(drain["name"])) for drain in combined.values()]
    merged.sort(key=lambda item: item["distance_km"])
    return merged


def get_drain(name: str) -> dict[str, Any] | None:
    for drain in get_all_drains():
        if drain["name"] == name:
            return drain
    return None


def random_drain(
    min_distance: float = 0,
    max_distance: float = 100,
    only_unvisited: bool = False,
) -> dict[str, Any] | None:
    candidates = filter_drains(min_distance, max_distance, only_unvisited)
    if not candidates:
        return None
    return random.choice(candidates)


def filter_drains(
    min_distance: float = 0,
    max_distance: float = 60,
    only_unvisited: bool = False,
    search: str = "",
) -> list[dict[str, Any]]:
    drains = []
    term = search.strip().casefold()

    for drain in get_all_drains():
        if drain["distance_km"] < min_distance or drain["distance_km"] > max_distance:
            continue
        if only_unvisited and drain["visited"]:
            continue
        haystack = " ".join(
            [
                drain["name"],
                drain.get("description", ""),
                drain.get("difficulty", ""),
                drain.get("value", ""),
            ]
        ).casefold()
        if term and term not in haystack:
            continue
        drains.append(drain)

    return drains


def recommend_session(
    session_type: str = "long",
    min_distance: float = 0,
    max_distance: float = 60,
    only_unvisited: bool = False,
) -> dict[str, Any]:
    candidates = filter_drains(min_distance, max_distance, only_unvisited)
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
    min_distance: float = 0,
    max_distance: float = 60,
    only_unvisited: bool = False,
    stop_limit: int = 4,
    max_leg_km: float = 5,
    max_total_minutes: float = 120,
) -> dict[str, Any]:
    pool = filter_drains(min_distance, max_distance, only_unvisited)
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


def nearby_drains(name: str, limit: int = 3, radius_km: float = 5) -> list[dict[str, Any]]:
    current = get_drain(name)
    if not current:
        return []

    nearby: list[dict[str, Any]] = []
    for drain in get_all_drains():
        if drain["name"] == name:
            continue
        dist = distance_km(current["lat"], current["lon"], drain["lat"], drain["lon"])
        if dist <= radius_km:
            enriched = dict(drain)
            enriched["distance_from_current_km"] = round(dist, 2)
            nearby.append(enriched)

    nearby.sort(key=lambda item: item["distance_from_current_km"])
    return nearby[:limit]


def route_from_drain(name: str, radius_km: float = 5, stop_limit: int = 4) -> dict[str, Any]:
    start = get_drain(name)
    if not start:
        return {"route": [], "total_minutes": 0, "total_distance_km": 0}

    nearby = nearby_drains(name, limit=max(0, stop_limit - 1), radius_km=radius_km)
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


def stats_summary() -> dict[str, int]:
    drains = get_all_drains()
    return {
        "total": len(drains),
        "visited": sum(1 for item in drains if item["visited"]),
        "favorites": sum(1 for item in drains if item["favorite"]),
        "custom": sum(1 for item in drains if item["custom"]),
    }


def update_drain(
    name: str,
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
    metadata = load_metadata()
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
    save_metadata(metadata)
    return True


def add_custom_drain(name: str, lat: float, lon: float, description: str = "") -> None:
    metadata = load_metadata()
    current = metadata.get(name, {})
    if not isinstance(current, dict):
        current = {}

    current["custom"] = True
    current["lat"] = lat
    current["lon"] = lon
    if description.strip():
        current["description"] = description.strip()

    metadata[name] = current
    save_metadata(metadata)


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
        absolute = os.path.join(BASE_DIR, normalized.replace("/", os.sep))
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


def list_photos(name: str) -> list[dict[str, Any]]:
    drain = get_drain(name)
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


def add_uploaded_photo(name: str, relative_path: str) -> None:
    metadata = load_metadata()
    current = metadata.get(name, {})
    if not isinstance(current, dict):
        current = {}
    current.setdefault("photos", [])
    current["photos"].append(normalize_photo_path(relative_path))
    metadata[name] = current
    save_metadata(metadata)


def remove_photo(name: str, path: str) -> None:
    metadata = load_metadata()
    current = metadata.get(name, {})
    if not isinstance(current, dict):
        return
    photos = [normalize_photo_path(photo) for photo in current.get("photos", [])]
    target = normalize_photo_path(path)
    current["photos"] = [photo for photo in photos if photo != target]
    metadata[name] = current
    save_metadata(metadata)

    if target.startswith("uploads/"):
        absolute = os.path.join(BASE_DIR, target.replace("/", os.sep))
        if os.path.exists(absolute):
            os.remove(absolute)


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
    session_type: str = "long",
    min_distance: float = 0,
    max_distance: float = 60,
    only_unvisited: bool = False,
) -> list[dict[str, Any]]:
    recommendation = recommend_session(session_type, min_distance, max_distance, only_unvisited)
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


def search_results(query: str, only_unvisited: bool = False) -> list[dict[str, Any]]:
    drains = filter_drains(0, 9999, only_unvisited, query)
    return result_rows(drains)


def google_earth_url(lat: float, lon: float, name: str) -> str:
    encoded_name = re.sub(r"\s+", "+", name.strip())
    return (
        "https://earth.google.com/web/search/"
        f"{encoded_name}/@{lat},{lon},-26.54449985a,339492.64726963d,35y,-0h,0t,0r/"
        "data=CgRCAggBMikKJwolCiExamhPeGdLRzE4T1NNTmFpSVh1cUFkQlhBYVYzU01oZkMgAToDCgEwQgIIAEoHCOv6sjsQAQ"
    )
