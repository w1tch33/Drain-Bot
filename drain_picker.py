import re
import xml.etree.ElementTree as ET
import math
import os
import random

BASE_LAT = -37.7672
BASE_LON = 145.1182


def get_settings():
    return {
        "SESSION_TYPE": os.getenv("SESSION_TYPE", "long"),
        "MAX_DISTANCE": float(os.getenv("MAX_DISTANCE", "60")),
        "MIN_DISTANCE": float(os.getenv("MIN_DISTANCE", "0")),
        "IS_RAINING": os.getenv("RAIN", "0") == "1"
    }


def distance(lat1, lon1, lat2, lon2):
    R = 6371
    value = (
        math.cos(math.radians(lat1)) *
        math.cos(math.radians(lat2)) *
        math.cos(math.radians(lon2 - lon1)) +
        math.sin(math.radians(lat1)) *
        math.sin(math.radians(lat2))
    )

    # 🔥 CLAMP to valid range
    value = max(-1, min(1, value))

    return R * math.acos(value)


def estimate_drive_time(distance_km):
    AVG_SPEED_KMH = 50
    return int((distance_km / AVG_SPEED_KMH) * 60)


def is_valid_name(name):
    n = name.lower()
    blocked = [
        "untitled measurement", "pipe", "line", "chamber",
        "split", "north", "south", "northern", "southern",
        "upstream", "manhole", "grille", "grill",
        "room", "junction", "links", "exit", "potentially",
        "here", "maybe", "potential", "new"
    ]
    return not any(word in n for word in blocked)


def clean_description(desc):
    if not desc:
        return ""
    desc = re.sub(r"<.*?>", "", desc)
    return desc.strip()


def load_kml(min_distance, max_distance):
    tree = ET.parse("your_map.kml")
    root = tree.getroot()

    ns = {"kml": "http://www.opengis.net/kml/2.2"}

    drains = []
    seen = set()

    for p in root.findall(".//kml:Placemark", ns):
        name_elem = p.find("kml:name", ns)
        coords_elem = p.find(".//kml:coordinates", ns)
        desc_elem = p.find("kml:description", ns)

        if name_elem is None or coords_elem is None:
            continue

        name = name_elem.text or "Unnamed"
        raw_desc = desc_elem.text if desc_elem is not None else ""
        description = clean_description(raw_desc)

        if not is_valid_name(name):
            continue

        key = name.strip().lower()
        if key in seen:
            continue
        seen.add(key)

        coord_text = coords_elem.text.strip().split()[0]
        lon, lat, _ = map(float, coord_text.split(","))

        dist = distance(BASE_LAT, BASE_LON, lat, lon)

        if min_distance <= dist <= max_distance:
            drains.append((name, lat, lon, dist, description))

    return drains


def build_plan(drains, session_type):
    if not drains:
        return []

    start = random.choice(drains)

    nearby = sorted(
        drains,
        key=lambda d: distance(start[1], start[2], d[1], d[2])
    )

    count = 2 if session_type == "short" else min(5, len(nearby))
    return nearby[:count]


def build_route(start, drains, max_jump_km):
    route = [start]
    remaining = drains[:]

    while remaining:
        last = route[-1]

        nearby = sorted(
            remaining,
            key=lambda d: distance(last[1], last[2], d[1], d[2])
        )

        next_drain = nearby[0]

        if distance(last[1], last[2], next_drain[1], next_drain[2]) > max_jump_km:
            break

        route.append(next_drain)
        remaining.remove(next_drain)

    return route


def estimate(route, max_route_km):
    if len(route) < 2:
        return 0, 0.33, route

    total_distance = 0
    new_route = [route[0]]

    for i in range(len(route) - 1):
        step = distance(
            route[i][1], route[i][2],
            route[i+1][1], route[i+1][2]
        )

        if total_distance + step > max_route_km:
            break

        total_distance += step
        new_route.append(route[i+1])

    walk_time = total_distance / 4
    explore_time = len(new_route) * 0.33
    total_time = walk_time + explore_time

    return round(total_distance, 2), round(total_time, 2), new_route


def get_all_drains():
    return load_kml(0, 9999)


def format_drain(d):
    """🔥 ensures consistent structure everywhere"""
    return (
        d[0],              # name
        0,                 # placeholder (unchanged)
        d[3],              # distance
        estimate_drive_time(d[3])  # drive time
    )


def run_picker():
    settings = get_settings()

    if settings["IS_RAINING"]:
        return {"error": "Unsafe (rain detected)"}

    drains = load_kml(settings["MIN_DISTANCE"], settings["MAX_DISTANCE"])

    if not drains:
        return {"error": "No drains found in range"}

    selected = build_plan(drains, settings["SESSION_TYPE"])

    primary = selected[0]
    route = build_route(primary, selected[1:], settings["MAX_DISTANCE"] / 10)

    total_dist, total_time, route = estimate(route, settings["MAX_DISTANCE"] * 0.6)

    return {
        "primary": format_drain(primary),
        "route": [format_drain(d) for d in route],
        "options": [format_drain(d) for d in drains if d not in selected][:5],
        "meta": {
            "distance_km": total_dist,
            "time_hours": total_time
        }
    }