import os
from pathlib import Path
from functools import wraps
from datetime import timedelta

from flask import Flask, abort, flash, jsonify, redirect, render_template, request, send_file, send_from_directory, session, url_for
from werkzeug.utils import secure_filename

import drain_service


app = Flask(__name__)
app.config["SECRET_KEY"] = os.getenv("FLASK_SECRET_KEY", "drain-tool-mobile")
app.config["PERMANENT_SESSION_LIFETIME"] = timedelta(days=30)
APPROVAL_PASSWORD = os.getenv("DRAINBOT_APPROVAL_PASSWORD") or app.config["SECRET_KEY"]

drain_service.ensure_runtime_dirs()


def _float_arg(name: str, default: float) -> float:
    try:
        return float(request.values.get(name, default))
    except (TypeError, ValueError):
        return default


def _bool_arg(name: str) -> bool:
    return request.values.get(name) in {"1", "true", "on", "yes"}


def current_username() -> str | None:
    username = session.get("username")
    if not isinstance(username, str) or not username:
        return None
    return username


def is_witch_account() -> bool:
    return current_username() == "witch"


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not current_username():
            if request.path.startswith("/api/"):
                return jsonify({"error": "Login required."}), 401
            return redirect(url_for("login"))
        return view(*args, **kwargs)

    return wrapped


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not is_witch_account():
            abort(403)
        if not session.get("admin_verified"):
            return redirect(url_for("admin_login"))
        return view(*args, **kwargs)

    return wrapped


@app.context_processor
def inject_globals():
    return {
        "format_minutes": drain_service.format_minutes,
        "current_username": current_username(),
        "admin_verified": bool(session.get("admin_verified")),
        "is_witch_account": is_witch_account(),
    }


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_username():
        return redirect(url_for("index"))

    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        try:
            account = drain_service.authenticate_account(username, password)
        except ValueError as error:
            flash(str(error))
            return render_template("login.html")

        if not account.get("approved"):
            flash("Your account is still waiting for approval.")
            return redirect(url_for("login"))

        session.clear()
        session.permanent = True
        session["username"] = account["username"]
        return redirect(url_for("index"))

    return render_template("login.html")


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if current_username():
        return redirect(url_for("index"))

    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        try:
            drain_service.create_account(username, password)
        except ValueError as error:
            flash(str(error))
            return render_template("signup.html")

        flash("Account created. It now needs your approval before login.")
        return redirect(url_for("login"))

    return render_template("signup.html")


@app.post("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if not is_witch_account():
        abort(403)
    if request.method == "POST":
        password = request.form.get("password", "")
        if password == APPROVAL_PASSWORD:
            session["admin_verified"] = True
            return redirect(url_for("admin_accounts"))
        flash("Wrong admin approval password.")
    return render_template("admin_login.html")


@app.get("/admin/accounts")
@admin_required
def admin_accounts():
    return render_template(
        "admin_accounts.html",
        pending_accounts=drain_service.list_pending_accounts(),
        all_accounts=drain_service.list_accounts(),
    )


@app.post("/admin/accounts/<username>/approve")
@admin_required
def approve_account(username: str):
    try:
        drain_service.approve_account(username)
        flash(f"Approved {drain_service.normalize_username(username)}.")
    except ValueError as error:
        flash(str(error))
    return redirect(url_for("admin_accounts"))


@app.post("/admin/accounts/<username>/delete")
@admin_required
def delete_account(username: str):
    try:
        drain_service.delete_account(username)
        flash(f"Deleted {drain_service.normalize_username(username)}.")
    except ValueError as error:
        flash(str(error))
    return redirect(url_for("admin_accounts"))


@app.route("/assets/smiley.png")
def smiley_asset():
    return send_from_directory(Path(app.static_folder), "smiley-pixelated.png")


@app.route("/")
@login_required
def index():
    return render_template(
        "index.html",
        stats=drain_service.stats_summary(current_username()),
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
@login_required
def stats():
    return jsonify(drain_service.stats_summary(current_username()))


@app.get("/api/run")
@login_required
def run_picker():
    return jsonify(
        drain_service.session_results(
            current_username(),
            session_type=request.args.get("session_type", "long"),
            min_distance=_float_arg("min_distance", 5),
            max_distance=_float_arg("max_distance", 30),
            only_unvisited=_bool_arg("only_unvisited"),
        )
    )


@app.get("/api/random")
@login_required
def random_drain():
    drain = drain_service.random_drain(
        current_username(),
        min_distance=_float_arg("min_distance", 0),
        max_distance=_float_arg("max_distance", 100),
        only_unvisited=_bool_arg("only_unvisited"),
    )
    if not drain:
        return jsonify({"error": "No drains found."}), 404
    return jsonify(drain)


@app.get("/api/route")
@login_required
def route_builder():
    return jsonify(
        drain_service.build_route_plan(
            current_username(),
            min_distance=_float_arg("min_distance", 5),
            max_distance=_float_arg("max_distance", 30),
            only_unvisited=_bool_arg("only_unvisited"),
        )
    )


@app.get("/api/search")
@login_required
def search():
    query = request.args.get("q", "")
    return jsonify(drain_service.search_results(current_username(), query, _bool_arg("only_unvisited")))


@app.post("/api/sync-kml")
@login_required
def sync_kml():
    file = request.files.get("kml_file")
    if not file or not file.filename:
        return jsonify({"error": "Choose a KML or KMZ file first."}), 400
    try:
        result = drain_service.sync_kml_payload(current_username(), file.read())
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    return jsonify(
        {
            **result,
            "stats": drain_service.stats_summary(current_username()),
        }
    )


@app.post("/api/sync-kml/undo")
@login_required
def undo_sync_kml():
    result = drain_service.undo_last_sync(current_username())
    return jsonify({**result, "stats": drain_service.stats_summary(current_username())})


@app.post("/api/location")
@login_required
def save_location():
    payload = request.get_json(silent=True) or request.form
    try:
        lat = float(payload.get("lat"))
        lon = float(payload.get("lon"))
    except (TypeError, ValueError, AttributeError):
        return jsonify({"error": "Invalid location."}), 400
    drain_service.save_user_origin(current_username(), lat, lon)
    return jsonify({"ok": True})


@app.get("/api/drains/<path:name>")
@login_required
def drain_detail(name: str):
    drain = drain_service.get_drain(name, current_username())
    if not drain:
        return jsonify({"error": "Drain not found."}), 404
    drain = dict(drain)
    drain["maps_url"] = drain_service.google_earth_url(drain["lat"], drain["lon"], drain["name"])
    drain["photos"] = drain_service.list_photos(name, current_username())
    drain["nearby"] = drain_service.nearby_drains(name, current_username())
    return jsonify(drain)


@app.post("/api/drains/<path:name>/update")
@login_required
def update_drain(name: str):
    drain = drain_service.get_drain(name, current_username())
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
        current_username(),
        visited=str(payload.get("visited", "")).lower() in {"1", "true", "on", "yes"},
        favorite=str(payload.get("favorite", "")).lower() in {"1", "true", "on", "yes"},
        description=str(payload.get("description", "")),
        difficulty=str(payload.get("difficulty", "")).strip(),
        value=str(payload.get("value", "")).strip(),
        rating=rating,
        notes=str(payload.get("notes", "")),
        features=payload.get("features") if hasattr(payload, "get") else None,
    )
    return jsonify({"ok": True, "stats": drain_service.stats_summary(current_username())})


@app.post("/api/drains/<path:name>/delete")
@login_required
def delete_drain(name: str):
    deleted = drain_service.delete_user_drain(current_username(), name)
    if not deleted:
        return jsonify({"error": "Only user-added drains can be deleted."}), 400
    return jsonify({"ok": True, "stats": drain_service.stats_summary(current_username())})


@app.get("/api/drains/<path:name>/route")
@login_required
def route_from_drain(name: str):
    return jsonify(drain_service.route_from_drain(name, current_username()))


@app.post("/api/custom-drains")
@login_required
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

    drain_service.add_custom_drain(current_username(), name, lat, lon, description)
    return jsonify({"ok": True, "name": name, "stats": drain_service.stats_summary(current_username())})


@app.post("/api/drains/<path:name>/photos")
@login_required
def upload_photo(name: str):
    username = current_username()
    if not drain_service.get_drain(name, username):
        return jsonify({"error": "Drain not found."}), 404

    file = request.files.get("photo")
    if not file or not file.filename:
        return jsonify({"error": "Choose a photo first."}), 400

    drain_service.ensure_user_dirs(username)
    filename = secure_filename(file.filename)
    root, ext = os.path.splitext(filename)
    counter = 1
    final_name = filename
    upload_dir = drain_service.user_upload_dir(username)
    absolute_path = os.path.join(upload_dir, final_name)
    while os.path.exists(absolute_path):
        final_name = f"{root}-{counter}{ext}"
        absolute_path = os.path.join(upload_dir, final_name)
        counter += 1

    file.save(absolute_path)
    relative_path = f"uploads/{drain_service.normalize_username(username)}/{final_name}"
    drain_service.add_uploaded_photo(name, username, relative_path)
    return jsonify({"ok": True, "photos": drain_service.list_photos(name, username)})


@app.post("/api/drains/<path:name>/photos/delete")
@login_required
def delete_photo(name: str):
    path = request.form.get("path", "")
    if not path:
        return jsonify({"error": "Photo path missing."}), 400
    drain_service.remove_photo(name, current_username(), path)
    return jsonify({"ok": True, "photos": drain_service.list_photos(name, current_username())})


@app.get("/uploads/<path:filename>")
@login_required
def uploaded_file(filename: str):
    return send_from_directory(drain_service.UPLOAD_DIR, filename)


@app.get("/photo-file/<path:filename>")
@login_required
def photo_file(filename: str):
    path = drain_service.find_photo_file(filename)
    if not path:
        abort(404)
    return send_file(path)


@app.get("/audio/<path:filename>")
@login_required
def audio_asset(filename: str):
    return send_from_directory(app.root_path, filename)


if __name__ == "__main__":
    app.run(
        debug=os.getenv("FLASK_DEBUG", "").lower() in {"1", "true", "yes", "on"},
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8000")),
    )
