import os
from pathlib import Path

from flask import Flask, abort, flash, jsonify, redirect, render_template, request, send_file, send_from_directory, url_for
from werkzeug.utils import secure_filename

import drain_service


app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("FLASK_SECRET_KEY", "drain-tool-mobile")

drain_service.ensure_runtime_dirs()


def _float_arg(name: str, default: float) -> float:
    try:
        return float(request.values.get(name, default))
    except (TypeError, ValueError):
        return default


def _bool_arg(name: str) -> bool:
    return request.values.get(name) in {"1", "true", "on", "yes"}


@app.context_processor
def inject_globals():
    return {"format_minutes": drain_service.format_minutes}


@app.route("/assets/smiley.png")
def smiley_asset():
    return send_from_directory(Path(app.static_folder), "smiley-pixelated.png")


@app.route("/")
def index():
    return render_template(
        "index.html",
        stats=drain_service.stats_summary(),
        playlist=[
            "By Your Side.mp3",
            "222  Unknowable.mp3",
            "G Jones - Maybe (Official Audio).mp3",
            "G Jones - Dancing On The Edge (Official Audio).mp3",
            "Get Hot - G Jones Remix.mp3",
            "G Jones - Which Way (Official Audio).mp3",
            "G Jones - Immortal Light (Official Audio).mp3",
            "Iridescent Leaves Floating Downstream.mp3",
            "G Jones - Remnant (Official Audio).mp3",
        ],
        helpful_links=[
            ("Melbourne Radar", "https://www.bom.gov.au/products/IDR023.loop.shtml"),
            ("Lewis VR Tours", "https://tour.panoee.net/67b282e6ed02439d5b29889b/67b2869ec8fccb419f15cbba"),
            ("Panics Website", "https://www.uer.ca/urbanadventure/www.urbanadventure.org/members/drains/uacity/d_mreps.htm"),
            ("Predators Document", "https://api.tunneltoads.com/documents/Approach%20Doc.html"),
            ("Melbourne Waterways Map", "https://melbournewater.maps.arcgis.com/apps/webappviewer/index.html?id=c6c2ea5762f04ba1a76936e702a9ed28"),
        ],
    )


@app.get("/api/stats")
def stats():
    return jsonify(drain_service.stats_summary())


@app.get("/api/run")
def run_picker():
    return jsonify(
        drain_service.session_results(
            session_type=request.args.get("session_type", "long"),
            min_distance=_float_arg("min_distance", 5),
            max_distance=_float_arg("max_distance", 30),
            only_unvisited=_bool_arg("only_unvisited"),
        )
    )


@app.get("/api/random")
def random_drain():
    drain = drain_service.random_drain(
        min_distance=_float_arg("min_distance", 0),
        max_distance=_float_arg("max_distance", 100),
        only_unvisited=_bool_arg("only_unvisited"),
    )
    if not drain:
        return jsonify({"error": "No drains found."}), 404
    return jsonify(drain)


@app.get("/api/route")
def route_builder():
    return jsonify(
        drain_service.build_route_plan(
            min_distance=_float_arg("min_distance", 5),
            max_distance=_float_arg("max_distance", 30),
            only_unvisited=_bool_arg("only_unvisited"),
        )
    )


@app.get("/api/search")
def search():
    query = request.args.get("q", "")
    return jsonify(drain_service.search_results(query, _bool_arg("only_unvisited")))


@app.post("/api/sync-kml")
def sync_kml():
    payload = request.get_json(silent=True) or request.form
    source_url = ""
    if hasattr(payload, "get"):
        source_url = str(payload.get("source_url", "")).strip()
    try:
        result = drain_service.sync_kml_from_source(source_url or None)
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    return jsonify(
        {
            **result,
            "stats": drain_service.stats_summary(),
        }
    )


@app.get("/api/drains/<path:name>")
def drain_detail(name: str):
    drain = drain_service.get_drain(name)
    if not drain:
        return jsonify({"error": "Drain not found."}), 404
    drain = dict(drain)
    drain["maps_url"] = drain_service.google_earth_url(drain["lat"], drain["lon"], drain["name"])
    drain["photos"] = drain_service.list_photos(name)
    drain["nearby"] = drain_service.nearby_drains(name)
    return jsonify(drain)


@app.post("/api/drains/<path:name>/update")
def update_drain(name: str):
    drain = drain_service.get_drain(name)
    if not drain:
        return jsonify({"error": "Drain not found."}), 404

    payload = request.get_json(silent=True) or request.form
    rating_raw = request.form.get("rating", "").strip()
    rating = None
    if hasattr(payload, "get"):
        rating_raw = str(payload.get("rating", "")).strip()
    if rating_raw and rating_raw != "None":
        try:
            rating = max(0, min(10, int(rating_raw)))
        except ValueError:
            rating = None

    drain_service.update_drain(
        name,
        visited=str(payload.get("visited", "")).lower() in {"1", "true", "on", "yes"},
        favorite=str(payload.get("favorite", "")).lower() in {"1", "true", "on", "yes"},
        description=str(payload.get("description", "")),
        difficulty=str(payload.get("difficulty", "")).strip(),
        value=str(payload.get("value", "")).strip(),
        rating=rating,
        notes=str(payload.get("notes", "")),
        features=payload.get("features") if hasattr(payload, "get") else None,
    )
    return jsonify({"ok": True, "stats": drain_service.stats_summary()})


@app.get("/api/drains/<path:name>/route")
def route_from_drain(name: str):
    return jsonify(drain_service.route_from_drain(name))


@app.post("/api/custom-drains")
def add_custom_drain():
    name = request.form.get("name", "").strip()
    description = request.form.get("description", "").strip()

    try:
        lat = float(request.form.get("lat", ""))
        lon = float(request.form.get("lon", ""))
    except ValueError:
        return jsonify({"error": "Enter valid coordinates for the custom drain."}), 400

    if not name:
        return jsonify({"error": "Give the custom drain a name."}), 400

    drain_service.add_custom_drain(name, lat, lon, description)
    return jsonify({"ok": True, "name": name, "stats": drain_service.stats_summary()})


@app.post("/api/drains/<path:name>/photos")
def upload_photo(name: str):
    if not drain_service.get_drain(name):
        return jsonify({"error": "Drain not found."}), 404

    file = request.files.get("photo")
    if not file or not file.filename:
        return jsonify({"error": "Choose a photo first."}), 400

    drain_service.ensure_upload_dir()
    filename = secure_filename(file.filename)
    root, ext = os.path.splitext(filename)
    counter = 1
    final_name = filename
    absolute_path = os.path.join(drain_service.UPLOAD_DIR, final_name)
    while os.path.exists(absolute_path):
        final_name = f"{root}-{counter}{ext}"
        absolute_path = os.path.join(drain_service.UPLOAD_DIR, final_name)
        counter += 1

    file.save(absolute_path)
    relative_path = f"uploads/{final_name}"
    drain_service.add_uploaded_photo(name, relative_path)
    return jsonify({"ok": True, "photos": drain_service.list_photos(name)})


@app.post("/api/drains/<path:name>/photos/delete")
def delete_photo(name: str):
    path = request.form.get("path", "")
    if not path:
        return jsonify({"error": "Photo path missing."}), 400
    drain_service.remove_photo(name, path)
    return jsonify({"ok": True, "photos": drain_service.list_photos(name)})


@app.get("/uploads/<path:filename>")
def uploaded_file(filename: str):
    return send_from_directory(drain_service.UPLOAD_DIR, filename)


@app.get("/photo-file/<path:filename>")
def photo_file(filename: str):
    path = drain_service.find_photo_file(filename)
    if not path:
        abort(404)
    return send_file(path)


@app.get("/audio/<path:filename>")
def audio_asset(filename: str):
    return send_from_directory(app.root_path, filename)


if __name__ == "__main__":
    app.run(
        debug=os.getenv("FLASK_DEBUG", "").lower() in {"1", "true", "yes", "on"},
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8000")),
    )
