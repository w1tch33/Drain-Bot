import tkinter as tk
from tkinter import filedialog, messagebox
import os
import json
import importlib
import sys
import webbrowser
import pygame
import drain_picker

SONG_END = None

smiley_sound = None

try:
    from PIL import Image, ImageTk, ImageDraw
    PIL_AVAILABLE = True
except:
    PIL_AVAILABLE = False

DATA_FILE = os.path.join(os.path.dirname(__file__), "drain_data.json")

BASE_LAT = -37.7672
BASE_LON = 145.1182


def slide_in_up(window, start_y, end_y, step=20):
    y = start_y
    def animate():
        nonlocal y
        if y > end_y:
            y -= step
            window.geometry(f"+{window.winfo_x()}+{y}")
            window.after(10, animate)
        else:
            window.geometry(f"+{window.winfo_x()}+{end_y}")
    animate()


def slide_in_right(window, start_x, end_x, y, step=30):
    x = start_x
    def animate():
        nonlocal x
        if x > end_x:
            x -= step
            window.geometry(f"+{x}+{y}")
            window.after(10, animate)
        else:
            window.geometry(f"+{end_x}+{y}")
    animate()


def show_loading():
    loading = tk.Toplevel(app)
    loading.title("Loading")
    loading.geometry("200x100")
    loading.transient(app)
    loading.grab_set()

    lbl = tk.Label(loading, text="Loading")
    lbl.pack(pady=20)

    dots = ["", ".", "..", "..."]

    def animate(i=0):
        lbl.config(text="Loading" + dots[i % len(dots)])
        loading.after(300, animate, i+1)

    animate()
    return loading


def resource_path(filename):
    try:
        base_path = sys._MEIPASS
    except:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, filename)


def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {}


def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)


drain_data = load_data()

def update_visited_counter():
    count = sum(
        1 for d in drain_data.values()
        if isinstance(d, dict) and d.get("visited") == 1
    )
    visited_label.config(text=f"Visited: {count}")


def add_dither(canvas, w, h):
    for x in range(0, w, 3):
        for y in range(0, h, 3):
            if (x + y) % 6 == 0:
                canvas.create_rectangle(x, y, x+1, y+1, fill="black", outline="")

import math

def distance_km(lat1, lon1, lat2, lon2):
    R = 6371

    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)

    a = (math.sin(dlat/2)**2 +
         math.cos(math.radians(lat1)) *
         math.cos(math.radians(lat2)) *
         math.sin(dlon/2)**2)

    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c


def format_time(minutes):
    minutes = int(round(minutes))

    if minutes < 60:
        return f"{minutes} min"

    hours = minutes // 60
    mins = minutes % 60

    return f"{hours}h {mins}m"


def km_to_minutes(km):
    SPEED_KMH = 60  # adjust if you want
    return (km / SPEED_KMH) * 60


def sort_route_from_start(route):
    if not route:
        return route

    start = route[0]

    # sort everything AFTER the first drain by distance from start
    rest = route[1:]

    rest_sorted = sorted(
        rest,
        key=lambda d: distance_km(start[1], start[2], d[1], d[2])
    )

    return [start] + rest_sorted


def mac_window(parent, title):
    outer = tk.Frame(parent, bg="black", bd=1)

    title_bar = tk.Canvas(outer, height=20, bg="white", highlightthickness=0)
    title_bar.pack(fill="x")

    def draw_title(event=None):
        title_bar.delete("all")

        w = title_bar.winfo_width()

        # background lines
        for i in range(0, w, 6):
            title_bar.create_line(i, 0, i, 20, fill="#888", width=2)

        box_width = 120
        x1 = (w - box_width) // 2
        x2 = x1 + box_width

        title_bar.create_rectangle(x1, 2, x2, 18, fill="white", outline="black")
        title_bar.create_text(w // 2, 10, text=title, font=("Courier", 10, "bold"))

    title_bar.bind("<Configure>", draw_title)

    inner = tk.Frame(outer, bg="#dcdcdc")
    inner.pack(fill="both", expand=True)

    return outer, inner


def mac_window_wide_title(parent, title):
    outer = tk.Frame(parent, bg="black", bd=1)

    title_bar = tk.Canvas(outer, height=20, bg="white", highlightthickness=0)
    title_bar.pack(fill="x")

    def draw_title(event=None):
        title_bar.delete("all")

        w = title_bar.winfo_width()

        for i in range(0, w, 6):
            title_bar.create_line(i, 0, i, 20, fill="#888", width=2)

        box_width = 240
        x1 = (w - box_width) // 2
        x2 = x1 + box_width

        title_bar.create_rectangle(x1, 2, x2, 18, fill="white", outline="black")
        title_bar.create_text(w // 2, 10, text=title, font=("Courier", 10, "bold"))

    title_bar.bind("<Configure>", draw_title)

    inner = tk.Frame(outer, bg="#dcdcdc")
    inner.pack(fill="both", expand=True)

    return outer, inner


def run_picker_ui():
    os.environ["SESSION_TYPE"] = "long"
    os.environ["MAX_DISTANCE"] = str(max_distance_var.get())
    os.environ["MIN_DISTANCE"] = str(min_distance_var.get())

    importlib.reload(drain_picker)

    loading = show_loading()
    app.update()

    result = drain_picker.run_picker()

    loading.destroy()
    display_results(result)


def random_drain():
    importlib.reload(drain_picker)

    # 🔥 limit to 100km radius
    drains = drain_picker.load_kml(0, 100)

    for name, d in drain_data.items():

        if not isinstance(d, dict):
            continue

        if d.get("custom"):
            lat = d["lat"]
            lon = d["lon"]

            dist = distance_km(BASE_LAT, BASE_LON, lat, lon)

            drains.append((name, lat, lon, dist))

    if not drains:
        return

    import random
    choice = random.choice(drains)
    open_drain_menu(choice[0])


def build_route():
    importlib.reload(drain_picker)

    try:
        drains = drain_picker.load_kml(0, 100)
    except:
        return

    # 🔥 ADD CUSTOM DRAINS (WITH DISTANCE FILTER)
    for name, d in drain_data.items():

        if not isinstance(d, dict):
            continue

        if d.get("custom"):
            lat = d["lat"]
            lon = d["lon"]

            dist = distance_km(BASE_LAT, BASE_LON, lat, lon)

            # 🔥 APPLY DISTANCE FILTER HERE
            if dist < min_distance_var.get() or dist > max_distance_var.get():
                continue

            drains.append((name, lat, lon, dist))

    # filter bad names
    filtered = []

    for d in drains:
        name = d[0].lower()

        # skip bad names
        if any(word in name for word in ["potentially", "maybe", "here"]):
            continue

        # 🔥 skip visited if toggle is ON
        if only_unvisited_var.get() == 1:
            if drain_data.get(d[0], {}).get("visited") == 1:
                continue

        filtered.append(d)

    import random
    random.shuffle(filtered)

    route = []
    total_time = 0
    start_lat = None
    start_lon = None

    for d in filtered:
        drive_time = d[3]

        # first drain always allowed
        if not route:
            route.append(d)

            # first drain = use its original drive time (from you)
            total_time += d[3]

            continue

        last = route[-1]

        lat1, lon1 = last[1], last[2]
        lat2, lon2 = d[1], d[2]

        # 🔥 must be within 5km
        if distance_km(lat1, lon1, lat2, lon2) > 5:
            continue

        # 🔥 max total time 2 hours
        if total_time + drive_time > 120:
            continue

        route.append(d)

        # calculate time from previous drain
        prev = route[-2]
        dist = distance_km(prev[1], prev[2], d[1], d[2])
        total_time += km_to_minutes(dist)

        if len(route) >= 4:
            break

    route = sort_route_from_start(route)

    # clear results
    for w in results_inner.winfo_children():
        w.destroy()

    if len(route) < 2:
        tk.Label(results_inner, text="No valid route found").pack()
        return

    # display route
    parts = []

    for i, d in enumerate(route):
        if i == 0:
            parts.append(d[0])
        else:
            prev = route[i-1]

            dist = distance_km(prev[1], prev[2], d[1], d[2])
            dist_text = f"{dist:.1f}km"

            parts.append(f"{dist_text} → {d[0]}")

    names = " → ".join(parts)

    tk.Label(results_inner, text=names, wraplength=300).pack(pady=5)
    tk.Label(results_inner, text=f"Total time: {format_time(total_time)}").pack(pady=5)

    for d in route:
        tk.Button(
            results_inner,
            text=f"{d[0]} ({format_time(d[3])})",
            command=lambda n=d[0]: open_drain_menu(n)
        ).pack(fill="x", padx=4, pady=2)


def display_results(data):
    for w in results_inner.winfo_children():
        w.destroy()

    seen = set()

    # 🔥 COMBINE picker results + custom drains
    combined = [data["primary"]] + data["route"] + data["options"]

    # 🔥 ADD CUSTOM DRAINS
    for name, d in drain_data.items():

        if not isinstance(d, dict):
            continue

        if d.get("custom"):
            lat = d["lat"]
            lon = d["lon"]

            dist = distance_km(BASE_LAT, BASE_LON, lat, lon)

            combined.append((name, lat, lon, dist))

    for d in combined:
        name = d[0]

        # 🔥 HANDLE CUSTOM VS KML PROPERLY
        if len(d) >= 4:
            lat = d[1]
            lon = d[2]

            # if it's a custom drain → calculate distance
            if drain_data.get(name, {}).get("custom"):
                dist = distance_km(BASE_LAT, BASE_LON, lat, lon)
                drive_time = format_time(km_to_minutes(dist))
            else:
                # KML drains already have correct distance
                dist = d[2] if isinstance(d[2], (int, float)) else d[1]
                drive_time = d[3] if len(d) > 3 else 0
        else:
            dist = 0
            drive_time = 0

        # 🔥 ONLY UNVISITED FILTER
        if only_unvisited_var.get() == 1:
            if drain_data.get(name, {}).get("visited") == 1:
                continue

        # 🔥 DISTANCE FILTER FOR EVERYTHING
        if dist < min_distance_var.get() or dist > max_distance_var.get():
            continue

        if name in seen:
            continue
        seen.add(name)

        tk.Button(
            results_inner,
            text=f"{name} ({dist:.1f} km) ({drive_time})",
            command=lambda n=name: open_drain_menu(n)
        ).pack(fill="x", padx=4, pady=2)


def open_drain_menu(name):
    win = tk.Toplevel(app)
    win.geometry("680x520")
    win.lift()
    win.transient(app)
    win.attributes("-topmost", True)
    win.after(100, lambda: win.attributes("-topmost", False))
    win.focus_force()

    win.update_idletasks()
    screen_w = win.winfo_screenwidth()
    screen_h = win.winfo_screenheight()

    final_x = int(screen_w / 2 - 340)
    final_y = int(screen_h / 2 - 260)

    win.geometry(f"+{screen_w}+{final_y}")
    slide_in_right(win, screen_w, final_x, final_y)

    outer, inner = mac_window_wide_title(win, name)
    outer.pack(fill="both", expand=True)

    # 🔥 SCROLL SETUP
    canvas = tk.Canvas(inner, bg="#dcdcdc", highlightthickness=0)
    scrollbar = tk.Scrollbar(inner, orient="vertical", command=canvas.yview)

    scrollable_frame = tk.Frame(canvas, bg="#dcdcdc")

    scrollable_frame.bind(
        "<Configure>",
        lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
    )

    canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")

    canvas.configure(yscrollcommand=scrollbar.set)

    canvas.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")

    # 🔥 IMPORTANT: replace inner
    inner = scrollable_frame

    def _on_mousewheel(event):
        canvas.yview_scroll(int(-1*(event.delta/120)), "units")

    canvas.bind_all("<MouseWheel>", _on_mousewheel)

    data = drain_data.get(name, {})

    # 🔥 NEARBY + ROUTE FUNCTIONS

    def show_nearby():
        try:
            all_drains = drain_picker.load_kml(0, 9999)
        except:
            all_drains = []

        for n, d in drain_data.items():

            if not isinstance(d, dict):
                continue

            if d.get("custom"):
                all_drains.append((n, d["lat"], d["lon"], 0))

        current = None
        for d in all_drains:
            if d[0] == name:
                current = d
                break

        if not current:
            return

        lat1, lon1 = current[1], current[2]

        distances = []

        for d in all_drains:
            if d[0] == name:
                continue

            lat2, lon2 = d[1], d[2]
            dist = distance_km(lat1, lon1, lat2, lon2)

            distances.append((d[0], dist, lat2, lon2))

        closest = sorted(distances, key=lambda x: x[1])[:3]

        for w in nearby_frame.winfo_children():
            w.destroy()

        for n, dist, lat, lon in closest:
            tk.Button(
                nearby_frame,
                text=f"{n} ({dist:.2f} km)",
                command=lambda x=n: open_drain_menu(x)
            ).pack(fill="x", pady=2)


    def build_route_from_here():
        try:
            all_drains = drain_picker.load_kml(0, 9999)
        except:
            return

        for n, d in drain_data.items():

            if not isinstance(d, dict):   # 🔥 ADD THIS
                continue

            if d.get("custom"):
                all_drains.append((n, d["lat"], d["lon"], 0))

        start = None
        for d in all_drains:
            if d[0] == name:
                start = d
                break

        if not start:
            return

        lat1, lon1 = start[1], start[2]

        nearby = []

        for d in all_drains:
            if d[0] == name:
                continue

            lat2, lon2 = d[1], d[2]
            dist = distance_km(lat1, lon1, lat2, lon2)

            if dist <= 5:  # 🔥 route radius
                nearby.append((d[0], lat2, lon2, dist))

        # sort + take 3
        nearby = sorted(nearby, key=lambda x: x[3])[:3]

        route = [start] + nearby

        # 🔥 DISPLAY IN RESULTS PANEL
        for w in results_inner.winfo_children():
            w.destroy()

        parts = [start[0]]

        total_time = 0

        for i in range(1, len(route)):
            prev = route[i-1]
            curr = route[i]

            dist = distance_km(prev[1], prev[2], curr[1], curr[2])
            total_time += km_to_minutes(dist)

            parts.append(f"{dist:.1f}km → {curr[0]}")

        tk.Label(results_inner, text=" → ".join(parts), wraplength=300).pack(pady=5)
        tk.Label(results_inner, text=f"Total time: {format_time(total_time)}").pack(pady=5)

        for d in route:
            tk.Button(
                results_inner,
                text=d[0],
                command=lambda n=d[0]: open_drain_menu(n)
            ).pack(fill="x", padx=4, pady=2)


    # 🔥 get description from KML if not already saved
    try:
        all_drains = drain_picker.get_all_drains()
        kml_match = next((d for d in all_drains if d[0] == name), None)
        if kml_match:
            kml_description = kml_match[4]  # NEW INDEX
        else:
            kml_description = ""
    except:
        kml_description = ""

    def save():
        drain_data[name] = data
        save_data(drain_data)

    # 🔥 TOP ACTION BUTTONS
    top_actions = tk.Frame(inner, bg="#dcdcdc")
    top_actions.pack(fill="x", pady=6)

    tk.Button(
        top_actions,
        text="Nearby",
        command=show_nearby
    ).pack(side="left", padx=4)

    tk.Button(
        top_actions,
        text="Build Route",
        command=build_route_from_here
    ).pack(side="left", padx=4)

    nearby_frame = tk.Frame(inner, bg="#dcdcdc")
    nearby_frame.pack(fill="x")

    fav_var = tk.IntVar(value=data.get("favorite", 0))
    tk.Checkbutton(inner, text="Favorite", variable=fav_var,
                   command=lambda: (data.update({"favorite": fav_var.get()}), save())
                   ).pack(anchor="w")

    visited_var = tk.IntVar(value=data.get("visited", 0))

    def update_visited():
        data["visited"] = visited_var.get()
        save()
        update_visited_counter()

    tk.Checkbutton(
        inner,
        text="Visited",
        variable=visited_var,
        command=update_visited
    ).pack(anchor="w")

    # 📦 DESCRIPTION WITH SCROLLBAR
    desc_frame = tk.Frame(inner, bg="#dcdcdc")
    desc_frame.pack(fill="x")

    desc_scroll = tk.Scrollbar(desc_frame)

    desc = tk.Text(
        desc_frame,
        height=6,
        yscrollcommand=desc_scroll.set
    )

    desc_scroll.config(command=desc.yview)

    desc.pack(side="left", fill="both", expand=True)
    desc_scroll.pack(side="right", fill="y")

    # priority: saved description > KML description
    initial_desc = data.get("description") or kml_description
    desc.insert("1.0", initial_desc)

    def _scroll_desc(event):
        desc.yview_scroll(int(-1*(event.delta/120)), "units")

    def enable_desc_scroll(event):
        canvas.unbind_all("<MouseWheel>")
        desc.bind_all("<MouseWheel>", _scroll_desc)

    def disable_desc_scroll(event):
        desc.unbind_all("<MouseWheel>")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)

    desc.bind("<Enter>", enable_desc_scroll)
    desc.bind("<Leave>", disable_desc_scroll)

    desc.bind("<MouseWheel>", _scroll_desc)

    tk.Button(inner, text="Save Description",
              command=lambda: (data.update({"description": desc.get("1.0", "end").strip()}), save())
              ).pack(pady=4)

    # 🧙 WITCH'S NOTES
    tk.Label(inner, text="Witch's Notes", bg="#dcdcdc").pack(anchor="w")

    notes = tk.Text(inner, height=5)

    # load saved notes
    initial_notes = data.get("witch_notes", "")
    notes.insert("1.0", initial_notes)

    notes.pack(fill="x")

    tk.Button(
        inner,
        text="Save Notes",
        command=lambda: (
            data.update({"witch_notes": notes.get("1.0", "end").strip()}),
            save()
        )
    ).pack(pady=4)

    # 🔥 FEATURES CHECKLIST
    tk.Label(inner, text="FEATURES:", bg="#dcdcdc").pack(anchor="w")

    features = [
        "Junction",
        "Split",
        "Slide",
        "Grille Room",
        "Chamber",
        "Waterfall",
        "Side-Pipe"
    ]

    feature_vars = {}

    for f in features:
        var = tk.IntVar(value=data.get("features", {}).get(f, 0))

        def make_cmd(feature_name, var_ref):
            return lambda: (
                data.setdefault("features", {}),
                data["features"].update({feature_name: var_ref.get()}),
                save()
            )

        cb = tk.Checkbutton(
            inner,
            text=f,
            variable=var,
            command=make_cmd(f, var)
        )
        cb.pack(anchor="w")

        feature_vars[f] = var

    # Difficulty
    tk.Label(inner, text="Difficulty", bg="#dcdcdc").pack(anchor="w")
    difficulty = tk.StringVar(value=data.get("difficulty", ""))

    btn_frame = tk.Frame(inner, bg="#dcdcdc")
    btn_frame.pack(anchor="w")

    buttons = {}
    def update_buttons():
        for k, btn in buttons.items():
            if difficulty.get() == k:
                colors = {"easy":"#4CAF50","medium":"#FFD54F","hard":"#E53935"}
                btn.config(bg=colors[k])
            else:
                btn.config(bg="SystemButtonFace")

    def set_diff(level):
        difficulty.set(level)
        data["difficulty"] = level
        save()
        update_buttons()

    for lvl in ["easy","medium","hard"]:
        b = tk.Button(btn_frame, text=lvl.upper(), width=8,
                      command=lambda l=lvl: set_diff(l))
        b.pack(side="left", padx=4)
        buttons[lvl]=b

    update_buttons()

    # Value
    tk.Label(inner, text="Value", bg="#dcdcdc").pack(anchor="w")
    value = tk.StringVar(value=data.get("value", ""))

    value_frame = tk.Frame(inner, bg="#dcdcdc")
    value_frame.pack(anchor="w")

    value_buttons = {}
    def update_value():
        for k, btn in value_buttons.items():
            if value.get()==k:
                colors={
                    "trash":"#E53935",
                    "bad":"#FFD54F",      # yellow
                    "mid":"#2196F3",      # blue
                    "good":"#4CAF50",
                    "amazing":"#8E24AA"
                }
                btn.config(bg=colors[k], fg="white" if k=="amazing" else "black")
            else:
                btn.config(bg="SystemButtonFace", fg="black")

    def set_value(level):
        value.set(level)
        data["value"]=level
        save()
        update_value()

    for lvl in ["trash","bad","mid","good","amazing"]:
        b=tk.Button(value_frame,text=lvl.upper(),width=9,
                    command=lambda l=lvl:set_value(l))
        b.pack(side="left",padx=3)
        value_buttons[lvl]=b

    update_value()

    # ⭐ RATING (1–10)
    tk.Label(inner, text="Rating (1–10)", bg="#dcdcdc").pack(anchor="w")

    rating = tk.IntVar(value=data.get("rating", 0))

    rating_frame = tk.Frame(inner, bg="#dcdcdc")
    rating_frame.pack(anchor="w")

    rating_buttons = {}

    def update_rating():
        for i, btn in rating_buttons.items():
            if rating.get() == i:
                colors = [
                    "#E53935", "#EF5350", "#FB8C00", "#FFB300",
                    "#FDD835", "#C0CA33", "#7CB342", "#43A047",
                    "#1E88E5", "#8E24AA"
                ]

                btn.config(bg=colors[i-1], fg="white")  # selected
            else:
                btn.config(bg="SystemButtonFace", fg="black")

    def set_rating(val):
        rating.set(val)
        data["rating"] = val
        save()
        update_rating()

    # create buttons 1–10
    for i in range(1, 11):
        b = tk.Button(
            rating_frame,
            text=str(i),
            width=3,
            command=lambda v=i: set_rating(v)
        )
        b.pack(side="left", padx=2, pady=2)
        rating_buttons[i] = b

    update_rating()

    def show_nearby():
        try:
            all_drains = drain_picker.load_kml(0, 9999)
        except:
            all_drains = []

        # include custom drains
        for n, d in drain_data.items():

            if not isinstance(d, dict):
                continue

            if d.get("custom"):
                all_drains.append((n, d["lat"], d["lon"], 0))

        # get current drain coords
        current = None

        for d in all_drains:
            if d[0] == name:
                current = d
                break

        if not current:
            return

        lat1, lon1 = current[1], current[2]

        distances = []

        for d in all_drains:
            if d[0] == name:
                continue

            lat2, lon2 = d[1], d[2]

            dist = distance_km(lat1, lon1, lat2, lon2)
            distances.append((d[0], dist))

        # sort by distance
        closest = sorted(
            [d for d in distances if d[1] <= 5],  # only within 5km
            key=lambda x: x[1]
        )[:3]

        # clear previous nearby results
        for w in nearby_frame.winfo_children():
            w.destroy()

        # display results
        for n, dist in closest:
            tk.Button(
                nearby_frame,
                text=f"{n} ({dist:.2f} km)",
                command=lambda x=n: open_drain_menu(x)
            ).pack(fill="x", pady=2)


    # Photos
    tk.Label(inner, text="Photos", bg="#dcdcdc").pack(anchor="w")
    frame = tk.Frame(inner, bg="#dcdcdc")
    frame.pack(anchor="w")

    images = []

    def open_large(path):
        top = tk.Toplevel(app)
        top.title("Photo Viewer")

        try:
            big = Image.open(path)
            big.thumbnail((400, 400))
            tk_big = ImageTk.PhotoImage(big)

            panel = tk.Label(top, image=tk_big)
            panel.image = tk_big
            panel.pack(padx=10, pady=10)

        except:
            tk.Label(top, text="Failed to load image").pack(anchor="w")


    def refresh():
        for w in frame.winfo_children():
            w.destroy()

        for p in data.get("photos", []):
            if not os.path.exists(p):
                continue

            img = Image.open(p)
            img.thumbnail((80, 80))
            tk_img = ImageTk.PhotoImage(img)
            images.append(tk_img)

            c = tk.Frame(frame, bg="#dcdcdc")
            c.pack(side="left", padx=6)

            # 🔥 IMAGE (CLICKABLE)
            lbl = tk.Label(c, image=tk_img, cursor="hand2")
            lbl.pack()

            # 🔥 FIXED CLICK BINDING
            lbl.bind("<Button-1>", lambda e, path=p: open_large(path))

            # 🗑 DELETE
            def confirm_delete(path):
                result = messagebox.askyesno(
                    "Delete Photo",
                    "Are you sure you want to delete this photo?"
                )

                if result:
                    data["photos"].remove(path)
                    save()
                    refresh()

            tk.Button(
                c,
                text="Delete",
                command=lambda x=p: confirm_delete(x)
            ).pack()


    def add():
        p = filedialog.askopenfilename()
        if p:
            data.setdefault("photos", []).append(os.path.abspath(p))
            save()
            refresh()

    btn_wrapper = tk.Frame(inner, bg="#dcdcdc", height=40)
    btn_wrapper.pack(fill="x", pady=6)

    btn_wrapper.pack_propagate(False)

    btn = tk.Button(btn_wrapper, text="Add Photo", command=add)
    btn.place(relx=0.5, rely=0.5, anchor="center")

    refresh()

def open_drain_navigator():
    import random

    win = tk.Toplevel(app)
    win.title("Drain Navigator")
    win.geometry("500x540")

    outer, inner = mac_window(win, "Drain Navigator")
    outer.pack(fill="both", expand=True)

    SIZE = random.choice([21, 25, 31])  # 🔥 BIGGER MAZES
    TILE = 480 // SIZE

    canvas = tk.Canvas(inner, width=480, height=480, bg="black")
    canvas.pack(pady=10)
    light_image = None

    # 🔥 RANDOM MAZE GENERATOR
    def generate_maze(size):
        # 🔥 FORCE ODD SIZE
        if size % 2 == 0:
            size += 1

        maze = [[1]*size for _ in range(size)]

        def carve(x, y):
            directions = [(2,0), (-2,0), (0,2), (0,-2)]
            random.shuffle(directions)

            for dx, dy in directions:
                nx, ny = x + dx, y + dy

                if 1 <= nx < size-1 and 1 <= ny < size-1:
                    if maze[ny][nx] == 1:
                        maze[y + dy//2][x + dx//2] = 0
                        maze[ny][nx] = 0
                        carve(nx, ny)

        # carve main maze
        maze[1][1] = 0
        carve(1, 1)

        # 🔥 ADD CONTROLLED LOOPS (NO OPEN ROOMS)
        for _ in range(size):
            x = random.randrange(2, size-2)
            y = random.randrange(2, size-2)

            # only break walls BETWEEN corridors (grid-aligned)
            if maze[y][x] == 1:

                # horizontal tunnel connection
                if maze[y][x-1] == 0 and maze[y][x+1] == 0:
                    if maze[y-1][x] == 1 and maze[y+1][x] == 1:
                        maze[y][x] = 0

                # vertical tunnel connection
                elif maze[y-1][x] == 0 and maze[y+1][x] == 0:
                    if maze[y][x-1] == 1 and maze[y][x+1] == 1:
                        maze[y][x] = 0

        # start + exit
        maze[1][1] = 2
        maze[size-2][size-2] = 3

        return maze

    maze = generate_maze(SIZE)

    import time
    start_time = time.time()

    player_pos = [1, 1]
    drips = []

    def spawn_drip():
        import random

        if random.random() < 0.3:
            x = random.randint(0, SIZE-1)
            y = random.randint(0, SIZE-1)

            if maze[y][x] == 0:
                drips.append([x, y, 0])
    game_started = False
    countdown = 3

    def draw():
        canvas.delete("all")

        import random
        import time

        # 🔥 WALL + FLOOR TEXTURE
        for y, row in enumerate(maze):
            for x, val in enumerate(row):

                if val == 1:
                    # textured wall
                    base = random.choice(["#3a3a3a", "#444", "#505050"])

                    canvas.create_rectangle(
                        x*TILE, y*TILE,
                        x*TILE+TILE, y*TILE+TILE,
                        fill=base,
                        outline="#111"
                    )

                    # random dark specks
                    if random.random() < 0.3:
                        canvas.create_rectangle(
                            x*TILE + random.randint(0, TILE-3),
                            y*TILE + random.randint(0, TILE-3),
                            x*TILE + random.randint(2, TILE),
                            y*TILE + random.randint(2, TILE),
                            fill="#2a2a2a",
                            outline=""
                        )

                elif val == 3:
                    # 🔥 EXIT GLOW (PULSING)
                    pulse = int((time.time() * 4) % 2)

                    glow_color = "#66FF66" if pulse == 0 else "#33CC33"

                    # outer glow
                    canvas.create_rectangle(
                        x*TILE-2, y*TILE-2,
                        x*TILE+TILE+2, y*TILE+TILE+2,
                        fill=glow_color,
                        outline=""
                    )

                    # inner core
                    canvas.create_rectangle(
                        x*TILE, y*TILE,
                        x*TILE+TILE, y*TILE+TILE,
                        fill="#00FF88",
                        outline=""
                    )

                else:
                    # floor
                    canvas.create_rectangle(
                        x*TILE, y*TILE,
                        x*TILE+TILE, y*TILE+TILE,
                        fill="#111",
                        outline=""
                    )

        # 🔥 WATER DRIPS
        spawn_drip()

        for drip in drips[:]:
            dx, dy, life = drip

            px = dx * TILE + TILE//2
            py = dy * TILE + life

            canvas.create_oval(
                px-2, py-2,
                px+2, py+2,
                fill="#4FC3F7",
                outline=""
            )

            drip[2] += 4

            if drip[2] > TILE:
                drips.remove(drip)

        # player
        px, py = player_pos

        canvas.create_rectangle(
            px*TILE+4, py*TILE+4,
            px*TILE+TILE-4, py*TILE+TILE-4,
            fill="#00E5FF"
        )

        # 🔦 SOFT GRADIENT FLASHLIGHT
        if game_started:

            global light_image

            canvas_w = SIZE * TILE
            canvas_h = SIZE * TILE

            img = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 220))
            draw_img = ImageDraw.Draw(img)

            px = player_pos[0] * TILE + TILE // 2
            py = player_pos[1] * TILE + TILE // 2

            max_radius = TILE * 5

            for r in range(max_radius, 0, -8):

                alpha = int(220 * (r / max_radius) ** 2)

                draw_img.ellipse(
                    (px - r, py - r, px + r, py + r),
                    fill=(0, 0, 0, alpha)
                )

            light_image = ImageTk.PhotoImage(img)

            canvas.create_image(0, 0, image=light_image, anchor="nw")

        # 🔥 REDRAW EXIT ON TOP (SO IT GLOWS)
        import time

        for y, row in enumerate(maze):
            for x, val in enumerate(row):

                if val == 3:
                    pulse = int((time.time() * 4) % 2)

                    glow_color = "#66FF66" if pulse == 0 else "#33CC33"

                    # outer glow
                    canvas.create_rectangle(
                        x*TILE-3, y*TILE-3,
                        x*TILE+TILE+3, y*TILE+TILE+3,
                        fill=glow_color,
                        outline=""
                    )

                    # inner core
                    canvas.create_rectangle(
                        x*TILE, y*TILE,
                        x*TILE+TILE, y*TILE+TILE,
                        fill="#00FF88",
                        outline=""
                    )


    def move(dx, dy):
        if not game_started:
            return

        x, y = player_pos
        nx, ny = x + dx, y + dy

        if 0 <= nx < SIZE and 0 <= ny < SIZE:
            if maze[ny][nx] != 1:
                player_pos[0] = nx
                player_pos[1] = ny

                if maze[ny][nx] == 3:
                    end_time = time.time()
                    elapsed = round(end_time - start_time, 1)

                    show_win_screen(elapsed)
                    return

        draw()
        win.after(50, draw)

    def restart_game():
        nonlocal maze, player_pos, start_time, game_started, countdown

        maze = generate_maze(SIZE)
        player_pos = [1, 1]
        start_time = time.time()

        game_started = False
        countdown = 3

        draw()
        start_countdown()


    def show_win_screen(seconds):
        overlay = tk.Frame(inner, bg="#000000")
        overlay.place(relx=0, rely=0, relwidth=1, relheight=1)

        box = tk.Frame(overlay, bg="#dcdcdc", bd=2, relief="solid")
        box.place(relx=0.5, rely=0.5, anchor="center")

        tk.Label(
            box,
            text="YOU ESCAPED THE DRAIN!",
            font=("Courier", 14, "bold"),
            bg="#dcdcdc"
        ).pack(padx=20, pady=10)

        tk.Label(
            box,
            text=f"You escaped in {seconds}s",
            font=("Courier", 11),
            bg="#dcdcdc"
        ).pack(pady=5)

        def play_again():
            overlay.destroy()
            restart_game()

        tk.Button(
            box,
            text="Play Again",
            command=play_again
        ).pack(pady=10)

    def start_countdown():
        nonlocal countdown, game_started

        countdown_label = tk.Label(
            inner,
            text="",
            font=("Courier", 40, "bold"),
            bg="#dcdcdc"
        )
        countdown_label.place(relx=0.5, rely=0.5, anchor="center")

        def tick():
            nonlocal countdown, game_started

            if countdown > 0:
                countdown_label.config(text=str(countdown))
                countdown -= 1
                win.after(1000, tick)
            else:
                countdown_label.destroy()
                game_started = True
                draw()

        tick()


    def key(event):
        if event.keysym == "w":
            move(0, -1)
        elif event.keysym == "s":
            move(0, 1)
        elif event.keysym == "a":
            move(-1, 0)
        elif event.keysym == "d":
            move(1, 0)

    win.bind("<Key>", key)
    win.focus_force()

    draw()
    start_countdown()

def open_drain_man():
    import random

    win = tk.Toplevel(app)
    win.title("Drain Man")
    win.geometry("520x600")

    outer, inner = mac_window(win, "Drain Man")
    outer.pack(fill="both", expand=True)

    WIDTH = 21
    HEIGHT = 21
    TILE = 22

    canvas = tk.Canvas(inner, width=WIDTH*TILE, height=HEIGHT*TILE, bg="black")
    canvas.pack(pady=10)

    grid = [[1]*WIDTH for _ in range(HEIGHT)]

    player = [1, 1]   # 🔥 MOVE THIS HERE (ABOVE generate_map)

    def generate_map():
        layout = [
            "#####################",
            "#.........#.........#",
            "#.###.###.#.###.###.#",
            "#o###.###.#.###.###o#",
            "#...................#",
            "#.###.#.#####.#.###.#",
            "#.....#...#...#.....#",
            "#####.### # ###.#####",
            "    #.#       #.#    ",
            "#####.# ## ## #.#####",
            "     .  #   #  .     ",
            "#####.# ##### #.#####",
            "    #.#       #.#    ",
            "#####.# ##### #.#####",
            "#.........#.........#",
            "#.###.###.#.###.###.#",
            "#o..#.....P.....#..o#",
            "###.#.#.#####.#.#.###",
            "#.....#...#...#.....#",
            "#.######### #########",
            "#...................#",
            "#####################"
        ]

        for y in range(HEIGHT):
            for x in range(WIDTH):
                char = layout[y][x]

                if char == "#":
                    grid[y][x] = 1
                elif char == ".":
                    grid[y][x] = 2
                elif char == "o":
                    grid[y][x] = 3  # power can
                elif char == "P":
                    player[0], player[1] = x, y
                    grid[y][x] = 0
                else:
                    grid[y][x] = 0

    generate_map()

    direction = [1, 0]
    next_direction = [1, 0]

    TURN_BUFFER_TIME = 5   # how many ticks input is remembered
    turn_buffer_timer = 0

    cops = [
        [WIDTH-2, HEIGHT-2],
        [WIDTH-2, 1]
    ]

    cop_spawns = [
        [WIDTH-2, HEIGHT-2],
        [WIDTH-2, 1]
    ]

    game_running = True

    score = 0
    high_score = drain_data.get("_drain_man_high_score", 0)
    level = 1

    frightened = False
    frightened_timer = 0

    BASE_FRIGHT_TIME = 80
    FRIGHT_TIME = BASE_FRIGHT_TIME

    mouth_open = True

    score_label = tk.Label(inner, text="Score: 0", bg="#dcdcdc")
    score_label.pack()

    level_label = tk.Label(inner, text="Level: 1", bg="#dcdcdc")
    level_label.pack()

    high_score_label = tk.Label(inner, text=f"High Score: {high_score}", bg="#dcdcdc")
    high_score_label.pack()

    def draw():
        canvas.delete("all")

        for y in range(HEIGHT):
            for x in range(WIDTH):
                val = grid[y][x]

                px = x * TILE
                py = y * TILE

                if val == 1:
                    canvas.create_rectangle(
                        px, py, px+TILE, py+TILE,
                        fill="#0D47A1", outline=""
                    )

                elif val == 2:
                    canvas.create_oval(
                        px+TILE//3, py+TILE//3,
                        px+2*TILE//3, py+2*TILE//3,
                        fill="#FFD54F", outline=""
                    )

                elif val == 3:
                    canvas.create_oval(
                        px+TILE//4, py+TILE//4,
                        px+3*TILE//4, py+3*TILE//4,
                        fill="#FFEB3B", outline=""
                    )

        # player (circle like pacman)
        px = player[0]*TILE
        py = player[1]*TILE

        if mouth_open:
            canvas.create_arc(
                px+2, py+2,
                px+TILE-2, py+TILE-2,
                start=30, extent=300,
                fill="#FFEB3B",
                outline=""
            )
        else:
            canvas.create_oval(
                px+2, py+2,
                px+TILE-2, py+TILE-2,
                fill="#FFEB3B",
                outline=""
            )

        # cops
        for cx, cy in cops:

            if frightened:
                if frightened_timer < 20 and frightened_timer % 4 < 2:
                    color = "#FFFFFF"
                else:
                    color = "#1E88E5"
            else:
                color = "#E53935"

            canvas.create_oval(
                cx*TILE+4, cy*TILE+4,
                cx*TILE+TILE-4, cy*TILE+TILE-4,
                fill=color
            )

    def move_player():
        nonlocal score, game_running, turn_buffer_timer, direction
        nonlocal frightened, frightened_timer, mouth_open
        nonlocal high_score

        if not game_running:
            return

        # 🔥 PRE-TURN BUFFER SYSTEM
        if turn_buffer_timer > 0:
            nx = (player[0] + next_direction[0]) % WIDTH
            ny = (player[1] + next_direction[1]) % HEIGHT

            if grid[ny][nx] != 1:
                direction[0], direction[1] = next_direction
                turn_buffer_timer = 0
            else:
                turn_buffer_timer -= 1

        nx = player[0] + direction[0]
        ny = player[1] + direction[1]

        # 🔥 FULL SAFE WRAP (NO CRASHES)
        nx = nx % WIDTH
        ny = ny % HEIGHT

        if grid[ny][nx] != 1:
            player[0], player[1] = nx, ny

        if grid[player[1]][player[0]] == 2:
            grid[player[1]][player[0]] = 0
            score += 10
            score_label.config(text=f"Score: {score}")

        if score > high_score:
            high_score = score
            high_score_label.config(text=f"High Score: {high_score}")
            drain_data["_drain_man_high_score"] = high_score
            save_data(drain_data)

        elif grid[player[1]][player[0]] == 3:
            grid[player[1]][player[0]] = 0
            frightened = True
            frightened_timer = FRIGHT_TIME

        remaining = sum(row.count(2) for row in grid)
        if remaining == 0:
            next_level()
            return

        for i, c in enumerate(cops):
            if c == player:

                # 🔥 IF POWER MODE → EAT COP
                if frightened:
                    cops[i] = cop_spawns[i][:]  # respawn at spawn
                    score += 50
                    score_label.config(text=f"Score: {score}")

                else:
                    show_game_over()
                    return

        # 🔥 SLOWER COPS
        speed = min(0.9, 0.4 + (level * 0.05))

        cop_moves = 1 + (level // 2)

        for _ in range(cop_moves):
            move_cops()

        # 🔥 FRIGHT TIMER
        if frightened:
            frightened_timer -= 1
            if frightened_timer <= 0:
                frightened = False

        # 🔥 MOUTH ANIMATION
        mouth_open = not mouth_open

        draw()
        win.after(110, move_player)

    def move_cops():
        for c in cops:
            px, py = player
            cx, cy = c

            options = [(1,0), (-1,0), (0,1), (0,-1)]
            random.shuffle(options)

            best = None

            if frightened:
                best_dist = -1

                for dx, dy in options:
                    nx = (cx + dx) % WIDTH
                    ny = (cy + dy) % HEIGHT

                    if grid[ny][nx] == 1:
                        continue

                    dist = abs(nx - px) + abs(ny - py)

                    if dist > best_dist:
                        best_dist = dist
                        best = (nx, ny)

            else:
                best_dist = 9999

                for dx, dy in options:
                    nx = (cx + dx) % WIDTH
                    ny = (cy + dy) % HEIGHT

                    if grid[ny][nx] == 1:
                        continue

                    dist = abs(nx - px) + abs(ny - py)

                    if dist < best_dist:
                        best_dist = dist
                        best = (nx, ny)

            if best:
                c[0], c[1] = best

    def next_level():
        nonlocal level, FRIGHT_TIME, game_running

        level += 1
        level_label.config(text=f"Level: {level}")

        # 🔥 increase difficulty
        FRIGHT_TIME = max(30, BASE_FRIGHT_TIME - (level * 5))

        game_running = False

        # reset grid + map
        for y in range(HEIGHT):
            for x in range(WIDTH):
                grid[y][x] = 1

        generate_map()


        # reset cops
        for i in range(len(cops)):
            cops[i] = cop_spawns[i][:]

        draw()
        start_countdown()


    def restart_game():
        nonlocal grid, player, direction, next_direction, cops
        nonlocal game_running, score, turn_buffer_timer, level, FRIGHT_TIME

        # reset grid + map
        grid = [[1]*WIDTH for _ in range(HEIGHT)]
        generate_map()

        # reset player + movement
        direction = [1, 0]
        next_direction = [1, 0]
        turn_buffer_timer = 0

        # reset cops
        cops[:] = [
            [WIDTH-2, HEIGHT-2],
            [WIDTH-2, 1]
        ]

        # reset score + level
        score = 0
        level = 1
        FRIGHT_TIME = BASE_FRIGHT_TIME

        score_label.config(text="Score: 0")
        level_label.config(text="Level: 1")

        # restart state
        game_running = False

        draw()
        start_countdown()

    def show_game_over():
        nonlocal high_score

        if score > high_score:
            high_score = score
            drain_data["_drain_man_high_score"] = high_score
            save_data(drain_data)

        nonlocal game_running
        game_running = False

        overlay = tk.Frame(inner, bg="black")
        overlay.place(relwidth=1, relheight=1)

        box = tk.Frame(overlay, bg="#dcdcdc", bd=2, relief="solid")
        box.place(relx=0.5, rely=0.5, anchor="center")

        tk.Label(
            box,
            text=f"GAME OVER\nScore: {score}\nHigh Score: {high_score}",
            fg="black",
            bg="#dcdcdc",
            font=("Courier", 14, "bold")
        ).pack(padx=20, pady=10)

        def play_again():
            overlay.destroy()
            restart_game()

        tk.Button(
            box,
            text="Play Again",
            command=play_again
        ).pack(pady=10)

    def show_win():
        nonlocal game_running
        game_running = False

        overlay = tk.Frame(inner, bg="black")
        overlay.place(relwidth=1, relheight=1)

        box = tk.Frame(overlay, bg="#dcdcdc", bd=2, relief="solid")
        box.place(relx=0.5, rely=0.5, anchor="center")

        tk.Label(
            box,
            text="ALL CANS COLLECTED",
            fg="black",
            bg="#dcdcdc",
            font=("Courier", 14, "bold")
        ).pack(padx=20, pady=10)

        def play_again():
            overlay.destroy()
            restart_game()

        tk.Button(
            box,
            text="Play Again",
            command=play_again
        ).pack(pady=10)

        if score > high_score:
            high_score = score
            drain_data["_drain_man_high_score"] = high_score
            save_data(drain_data)

    def start_countdown():
        nonlocal game_running

        countdown = 3

        countdown_label = tk.Label(
            inner,
            text="",
            font=("Courier", 40, "bold"),
            bg="#dcdcdc"
        )
        countdown_label.place(relx=0.5, rely=0.5, anchor="center")

        def tick():
            nonlocal countdown, game_running

            if countdown > 0:
                countdown_label.config(text=f"LEVEL {level}\n{countdown}")
                countdown -= 1
                win.after(1000, tick)
            else:
                countdown_label.destroy()
                game_running = True
                move_player()

        tick()

    def key(event):
        nonlocal next_direction, turn_buffer_timer

        if event.keysym == "w":
            next_direction = [0, -1]
        elif event.keysym == "s":
            next_direction = [0, 1]
        elif event.keysym == "a":
            next_direction = [-1, 0]
        elif event.keysym == "d":
            next_direction = [1, 0]

        # 🔥 reset buffer timer every time key is pressed
        turn_buffer_timer = TURN_BUFFER_TIME

    win.bind("<Key>", key)
    win.focus_force()

    draw()
    start_countdown()


def open_drain_climber():
    import random

    win = tk.Toplevel(app)
    win.title("Drain Climber")
    win.geometry("420x600")

    outer, inner = mac_window(win, "Drain Climber")
    outer.pack(fill="both", expand=True)

    WIDTH = 10
    HEIGHT = 200
    TILE = 20

    canvas = tk.Canvas(inner, width=WIDTH*TILE, height=500, bg="#1E1E2F")
    canvas.pack(pady=10)

    # 🔥 PLAYER (FIXED SPAWN)
    player = [WIDTH//2, HEIGHT-4]
    velocity_y = 0
    velocity_x = 0
    trail = []

    on_ground = False

    keys = {
        "a": False,
        "d": False,
        "space": False
    }

    # 🔥 BETTER PHYSICS
    gravity = 0.36
    jump_strength = -2.5
    move_speed = 0.40
    friction = 0.1

    platforms = []

    camera_y = player[1]

    # 🔥 WATER FIX
    water_level = HEIGHT + 10
    water_speed = 0.05

    score = 0
    max_height = player[1]
    high_score = drain_data.get("_drain_climber_high_score", 0)

    # 🔥 NEW SYSTEMS
    combo = 0
    combo_timer = 0
    shake = 0

    game_running = False

    score_label = tk.Label(inner, text="Score: 0", bg="#dcdcdc")
    score_label.pack()

    high_score_label = tk.Label(inner, text=f"High Score: {high_score}", bg="#dcdcdc")
    high_score_label.pack()

    # 🔥 FIXED PLATFORM GENERATION
    def generate_platforms():
        platforms.clear()

        # FULL WIDTH START PLATFORM
        start_y = HEIGHT - 3
        platforms.append([0, start_y, WIDTH, "normal"])

        y = start_y - 5

        while y > 0:
            gap = 5
            width = random.randint(2, 4)
            x = random.randint(0, WIDTH - width)

            ptype = random.choice(["normal", "bounce", "break"])
            platforms.append([x, y, width, ptype])
            y -= gap

    generate_platforms()

    def draw():
        canvas.delete("all")

        import random

        offset_y = camera_y * TILE - 250

        # 🔥 GRADIENT BACKGROUND
        for i in range(25):
            color = f"#1E1E{format(40 + i*4, '02x')}"
            canvas.create_rectangle(
                0, i*20,
                WIDTH*TILE, (i+1)*20,
                fill=color,
                outline=""
            )

        # platforms
        for x, y, w, ptype in platforms:
            for i in range(w):
                px = (x+i)*TILE
                py = y*TILE - offset_y

                if ptype == "normal":
                    color = "#E0E0E0"
                elif ptype == "bounce":
                    color = "#4CAF50"
                elif ptype == "break":
                    color = "#E0E0E0"

                canvas.create_rectangle(
                    px, py,
                    px+TILE, py+TILE,
                    fill=color,
                    outline=""
                )

        # 🧵 DRAW TRAIL
        for (tx, ty) in trail:
            px = tx*TILE
            py = ty*TILE - offset_y

            canvas.create_rectangle(
                px+6, py+6,
                px+TILE-6, py+TILE-6,
                fill="#FF8A65",
                outline=""
            )

        # player
        px = player[0]*TILE
        py = player[1]*TILE - offset_y

        canvas.create_rectangle(
            px+2, py+2,
            px+TILE-2, py+TILE-2,
            fill="#FF7043"
        )

        # water
        water_y = water_level*TILE - offset_y

        canvas.create_rectangle(
            0, water_y,
            WIDTH*TILE, 500,
            fill="#2979FF"
        )

    def move():
        nonlocal velocity_y, velocity_x, camera_y
        nonlocal water_level, score, high_score, on_ground
        nonlocal max_height, trail
        nonlocal combo, combo_timer

        if not game_running:
            return

        prev_y = player[1]

        # horizontal movement (HOLD BASED)
        if keys["a"]:
            velocity_x -= move_speed

        if keys["d"]:
            velocity_x += move_speed

        # clamp speed
        max_speed = 0.9 + combo * 0.05
        velocity_x = max(-max_speed, min(max_speed, velocity_x))

        player[0] += velocity_x

        # 🔥 ADD TRAIL WHEN MOVING FAST
        if abs(velocity_x) > 0.3 or abs(velocity_y) > 1:
            trail.append((player[0], player[1]))

        # limit trail length
        if len(trail) > 15:
            trail.pop(0)

        if player[0] < 0:
            player[0] = 0
            velocity_x = 0

        if player[0] > WIDTH-1:
            player[0] = WIDTH-1
            velocity_x = 0

        # jumping (works while moving)
        if keys["space"] and on_ground:

            if abs(velocity_x) > 0.5:
                velocity_y = jump_strength * 1.3
            else:
                velocity_y = jump_strength

            on_ground = False

        # 🔥 BETTER GRAVITY
        velocity_y += gravity

        player[1] += velocity_y

        velocity_x *= friction

        # 🔥 COLLISION FIX (NO STICK / NO FALL THROUGH)
        on_ground = False

        for p in platforms:
            x, y, w, ptype = p
            if player[0] >= x - 0.2 and player[0] <= x + w:
                if prev_y <= y - 1 and player[1] >= y - 1:

                    player[1] = y - 1

                    if ptype == "bounce":
                        velocity_y = -3.5

                    elif ptype == "break":
                        velocity_y = 0

                    else:
                        velocity_y = 0

                    on_ground = True
                    break

        # camera (smooth follow up AND down)
        camera_y += (player[1] - camera_y) * 0.1

        # 🔥 TRUE INFINITE SYSTEM (based on highest platform, NOT camera)
        highest_y = min(p[1] for p in platforms)

        # always keep generating above
        while highest_y > player[1] - 50:
            highest_y -= 5  # exact spacing (we fix this too)

            width = random.randint(2, 4)
            x = random.randint(0, WIDTH - width)

            ptype = random.choice(["normal", "bounce"])
            platforms.append([x, highest_y, width, ptype])

        # cleanup old platforms
        platforms[:] = [p for p in platforms if p[1] < player[1] + 30]

        # water
        water_level -= water_speed

        # score
        # 🔥 ONLY INCREASE SCORE WHEN REACHING NEW HEIGHT
        if player[1] < max_height:
            max_height = player[1]

            combo += 1
            combo_timer = 30

            gained = int((HEIGHT - max_height) * (1 + combo * 0.2))
            score = gained

            score_label.config(text=f"Score: {score}  |  Combo: x{combo}")

        if score > high_score:
            high_score = score
            high_score_label.config(text=f"High Score: {high_score}")
            drain_data["_drain_climber_high_score"] = high_score
            save_data(drain_data)

        # death
        if player[1] > water_level:
            show_game_over()
            return

        if combo_timer > 0:
            combo_timer -= 1
        else:
            combo = 0

        draw()
        win.after(35, move)

    def show_game_over():
        nonlocal game_running

        game_running = False

        overlay = tk.Frame(inner, bg="black")
        overlay.place(relwidth=1, relheight=1)

        box = tk.Frame(overlay, bg="#dcdcdc", bd=2)
        box.place(relx=0.5, rely=0.5, anchor="center")

        tk.Label(
            box,
            text=f"GAME OVER\nScore: {score}\nHigh Score: {high_score}",
            font=("Courier", 14, "bold"),
            bg="#dcdcdc"
        ).pack(padx=20, pady=10)

        def play_again():
            overlay.destroy()
            restart()

        tk.Button(box, text="Play Again", command=play_again).pack(pady=10)

    def restart():
        nonlocal player, velocity_y, velocity_x, water_level, camera_y
        nonlocal score, game_running, max_height, trail

        player = [WIDTH//2, HEIGHT-4]
        velocity_y = 0
        velocity_x = 0
        trail = []
        water_level = HEIGHT
        camera_y = player[1]
        score = 0
        max_height = player[1]   # 🔥 ADD THIS

        score_label.config(text="Score: 0")

        generate_platforms()

        game_running = False
        start_countdown()

    def start_countdown():
        nonlocal game_running

        countdown = 3

        label = tk.Label(inner, text="", font=("Courier", 40, "bold"), bg="#dcdcdc")
        label.place(relx=0.5, rely=0.5, anchor="center")

        def tick():
            nonlocal countdown, game_running

            if countdown > 0:
                label.config(text=f"DRAIN CLIMBER\n{countdown}")
                countdown -= 1
                win.after(1000, tick)
            else:
                label.destroy()
                game_running = True
                move()

        tick()

    def key_down(event):
        if event.keysym in keys:
            keys[event.keysym] = True


    def key_up(event):
        if event.keysym in keys:
            keys[event.keysym] = False

    win.bind("<KeyPress>", key_down)
    win.bind("<KeyRelease>", key_up)
    win.focus_force()

    draw()
    start_countdown()

def open_minigame_menu():
    win = tk.Toplevel(app)
    win.title("Mini Games")
    win.geometry("300x250")

    outer, inner = mac_window(win, "Mini Games")
    outer.pack(fill="both", expand=True)

    tk.Label(
        inner,
        text="SELECT GAME",
        font=("Courier", 12, "bold"),
        bg="#dcdcdc"
    ).pack(pady=6)

    # 🎮 GAME LIST
    games = [
        ("Drain Navigator", open_drain_navigator),
        ("Drain Man", open_drain_man),
        ("Drain Climber", open_drain_climber),
    ]

    for name, func in games:
        tk.Button(
            inner,
            text=name,
            command=lambda f=func: (win.destroy(), f())
        ).pack(fill="x", padx=10, pady=6)

def open_links_window():
    win = tk.Toplevel(app)
    win.title("Helpful Links")
    win.geometry("320x300")

    outer, inner = mac_window(win, "Helpful Links")
    outer.pack(fill="both", expand=True)

    links = [
        ("Melbourne Radar", "https://www.bom.gov.au/products/IDR023.loop.shtml"),
        ("Lewis VR Tours", "https://tour.panoee.net/67b282e6ed02439d5b29889b/67b2869ec8fccb419f15cbba"),
        ("Panics Website", "https://www.uer.ca/urbanadventure/www.urbanadventure.org/members/drains/uacity/d_mreps.htm"),
        ("Predators Document", "https://api.tunneltoads.com/documents/Approach%20Doc.html"),
        ("Melbourne Waterways Map", "https://melbournewater.maps.arcgis.com/apps/webappviewer/index.html?id=c6c2ea5762f04ba1a76936e702a9ed28")
    ]

    for text, url in links:
        tk.Button(
            inner,
            text=text,
            command=lambda u=url: webbrowser.open(u)
        ).pack(fill="x", padx=6, pady=4)

def open_add_drain():
    win = tk.Toplevel(app)
    win.title("Add Drain")
    win.geometry("300x220")

    tk.Label(win, text="Name").pack()
    name_entry = tk.Entry(win)
    name_entry.pack(fill="x", padx=10)

    tk.Label(win, text="Latitude").pack()
    lat_entry = tk.Entry(win)
    lat_entry.pack(fill="x", padx=10)

    tk.Label(win, text="Longitude").pack()
    lon_entry = tk.Entry(win)
    lon_entry.pack(fill="x", padx=10)

    def save_drain():
        name = name_entry.get().strip()

        try:
            lat = float(lat_entry.get())
            lon = float(lon_entry.get())
        except:
            messagebox.showerror("Error", "Invalid coordinates")
            return

        if not name:
            messagebox.showerror("Error", "Enter a name")
            return

        # 🔥 SAVE
        drain_data[name] = drain_data.get(name, {})
        drain_data[name]["custom"] = True
        drain_data[name]["lat"] = lat
        drain_data[name]["lon"] = lon

        save_data(drain_data)

        messagebox.showinfo("Saved", "Drain added!")
        win.destroy()

    tk.Button(win, text="Save", command=save_drain).pack(pady=10)

# --- UI ---
app = tk.Tk()
app.geometry("1000x600")

def fade_in_music(target=0.5, step=0.01, delay=50):
    current = pygame.mixer.music.get_volume()

    if current < target:
        current += step
        pygame.mixer.music.set_volume(current)
        app.after(delay, lambda: fade_in_music(target, step, delay))

import random

PLAYLIST = [
    "By Your Side.mp3",
    "222  Unknowable.mp3",
    "G Jones - Maybe (Official Audio).mp3",
    "G Jones - Dancing On The Edge (Official Audio).mp3",
    "Get Hot - G Jones Remix.mp3",
    "G Jones - Which Way (Official Audio).mp3",
    "G Jones - Immortal Light (Official Audio).mp3",
    "Iridescent Leaves Floating Downstream.mp3",
    "G Jones - Remnant (Official Audio).mp3",
]

current_song = None

current_song_name = tk.StringVar(value="No song")

def play_random_song():
    global current_song

    next_song = random.choice(PLAYLIST)

    # avoid same song twice
    while next_song == current_song:
        next_song = random.choice(PLAYLIST)

    current_song = next_song
    current_song_name.set(os.path.basename(current_song))

    try:
        pygame.mixer.music.load(current_song)
        pygame.mixer.music.set_volume(0)
        pygame.mixer.music.play()
        fade_in_music()
    except Exception as e:
        print("Music error:", e)

def next_song():
    play_random_song()

def prev_song():
    play_random_song()  # simple version for now

def toggle_pause():
    if pygame.mixer.music.get_busy():
        pygame.mixer.music.pause()
    else:
        pygame.mixer.music.unpause()

def scroll_song():
    text = current_song_name.get()

    song_canvas.itemconfig(song_text, text=text)

    bbox = song_canvas.bbox(song_text)
    if not bbox:
        app.after(200, scroll_song)
        return

    text_width = bbox[2] - bbox[0]
    canvas_width = song_canvas.winfo_width()

    x = song_canvas.coords(song_text)[0]

    # always scroll
    if x < -(text_width + 50):
        x = canvas_width

    song_canvas.coords(song_text, x - 2, 10)

    app.after(30, scroll_song)

def show_meow_overlay():
    overlay = tk.Label(
        app,
        text="MEOW",
        font=("Courier", 160, "bold"),  # 🔥 BIGGER
        fg="black",
        bg="white"
    )

    overlay.place(relx=0.5, rely=0.5, anchor="center")

    # 🔥 FLASH EFFECT
    def flash(count=0):
        if count > 6:  # number of flashes
            overlay.destroy()
            return

        if count % 2 == 0:
            overlay.config(bg="white", fg="black")
        else:
            overlay.config(bg="black", fg="white")

        app.after(80, flash, count + 1)

    flash()


def play_smiley_sound(event=None):
    if smiley_sound:
        try:
            smiley_sound.play()
        except:
            pass

    show_meow_overlay()


def start_music():
    global SONG_END, smiley_sound

    try:
        pygame.mixer.init()

        # 🔥 LOAD SMILEY SOUND HERE (AFTER INIT)
        try:
            smiley_sound = pygame.mixer.Sound(resource_path("coco meow.wav"))
        except:
            smiley_sound = None

        SONG_END = pygame.USEREVENT + 1
        pygame.mixer.music.set_endevent(SONG_END)

        play_random_song()

        check_music()

    except Exception as e:
        print("Music failed:", e)

# 🎵 MUSIC SETUP

# slide in
app.update_idletasks()
sw,sh=app.winfo_screenwidth(),app.winfo_screenheight()
start_y=sh; end_y=int(sh/2-300)
app.geometry(f"+{int(sw/2-500)}+{start_y}")
slide_in_up(app,start_y,end_y)

desktop = tk.Canvas(app, bg="#cfcfcf")
desktop.pack(fill="both", expand=True)

def redraw_bg(event):
    desktop.delete("all")  # clear old pattern
    add_dither(desktop, event.width, event.height)

desktop.bind("<Configure>", redraw_bg)

# title
title_container=tk.Frame(app,bg="black")
title_container.place(relx=0.5,y=30,anchor="center")
inner=tk.Frame(title_container,bg="white");inner.pack(padx=3,pady=3)
c=tk.Canvas(inner,width=300,height=32,bg="white",highlightthickness=0);c.pack()
for i in range(0,300,4): c.create_line(i,0,i,32,fill="#b5b5b5")
c.create_rectangle(2,2,298,30,outline="black",width=1)
c.create_rectangle(50,6,250,26,fill="white",outline="black")
c.create_text(150,16,text="DRAIN-BOT",font=("Courier",16,"bold"))

controls_outer,controls_inner=mac_window(app,"Control Panel")
controls_outer.place(relx=0.02, rely=0.08, relwidth=0.25, relheight=0.5)

# 🎮 MINI GAME BUTTON (TOP RIGHT OF APP)
minigame_btn = tk.Button(
    app,
    text="Mini Games!",
    command=open_minigame_menu
)

def flash_minigame_button(state=0):
    if state == 0:
        minigame_btn.config(bg="black", fg="white")
    else:
        minigame_btn.config(bg="white", fg="black")

    app.after(400, flash_minigame_button, 1 - state)

flash_minigame_button()

minigame_btn.place(relx=1.0, x=-120, y=10, anchor="ne")

# 🔥 HELPFUL LINKS BUTTON (TOP RIGHT OF CONTROL PANEL)
links_btn = tk.Button(
    controls_outer,
    text="Links",
    command=open_links_window
)

links_btn.place(relx=1.0, x=-10, y=40, anchor="ne")

# 🔥 VISITED COUNTER (NO TITLE BAR)
visited_outer = tk.Frame(app, bg="black", bd=1)
visited_outer.place(relx=0.02, rely=0.01, relwidth=0.12, relheight=0.06)

visited_inner = tk.Frame(visited_outer, bg="#dcdcdc")
visited_inner.pack(fill="both", expand=True, padx=1, pady=1)

visited_label = tk.Label(
    visited_inner,
    text="Visited: 0",
    bg="#dcdcdc",
    font=("Courier", 11, "bold")
)
visited_label.pack(expand=True)

# 🔥 TOP BAR (for volume)

# 🎚️ VOLUME (ABSOLUTE TOP RIGHT)
volume_var = tk.DoubleVar(value=0.5)

def update_volume(val):
    pygame.mixer.music.set_volume(float(val))

# 🔥 THIS IS THE KEY LINE

results_outer,results_inner=mac_window(app,"Results")
results_outer.place(relx=0.32, rely=0.08, relwidth=0.35, relheight=0.8)

search_outer,search_inner=mac_window(app,"Search")
search_outer.place(relx=0.7, rely=0.08, relwidth=0.25, relheight=0.8)

only_unvisited_var = tk.IntVar(value=0)

min_distance_var=tk.IntVar(value=5)
max_distance_var=tk.IntVar(value=30)

def update_range(val=None):
    if min_distance_var.get()>max_distance_var.get():
        min_distance_var.set(max_distance_var.get())

# MIN DISTANCE
tk.Label(controls_inner, text="Min km", bg="#dcdcdc").pack(anchor="w", padx=10)

tk.Scale(
    controls_inner,
    from_=0,
    to=120,
    orient="horizontal",
    variable=min_distance_var,
    command=update_range
).pack(anchor="w", padx=10)

# MAX DISTANCE
tk.Label(controls_inner, text="Max km", bg="#dcdcdc").pack(anchor="w", padx=10)

tk.Scale(
    controls_inner,
    from_=5,
    to=120,
    orient="horizontal",
    variable=max_distance_var,
    command=update_range
).pack(anchor="w", padx=10)


tk.Button(controls_inner,text="Run",command=run_picker_ui).pack(anchor="w", padx=10)
tk.Button(controls_inner,text="Random Drain",command=random_drain).pack(anchor="w", padx=10)
tk.Button(controls_inner, text="Build Route", command=build_route).pack(anchor="w", padx=10)
tk.Button(controls_inner, text="Add Drain", command=open_add_drain).pack(anchor="w", padx=10)

tk.Checkbutton(
    controls_inner,
    text="Only Unvisited",
    variable=only_unvisited_var
).pack(anchor="w", padx=10)

# search panel
search_var = tk.StringVar()

search_entry = tk.Entry(search_inner, textvariable=search_var)
search_entry.pack(fill="x", padx=4, pady=4)

frame = tk.Frame(search_inner, bg="#dcdcdc")
frame.pack(fill="both", expand=True)


def update_search(*args):
    for w in frame.winfo_children():
        w.destroy()

    q = search_var.get().lower()

    try:
        drains = drain_picker.load_kml(0, 9999)
    except:
        drains = []

    for name, d in drain_data.items():

        if not isinstance(d, dict):
            continue

        if d.get("custom"):
            lat = d["lat"]
            lon = d["lon"]

            dist = distance_km(BASE_LAT, BASE_LON, lat, lon)

            drains.append((name, lat, lon, dist))

    for d in drains:
        name = d[0]

        if q in name.lower():

            if only_unvisited_var.get() == 1:
                if drain_data.get(name, {}).get("visited") == 1:
                    continue
            try:
                drive_time = drain_picker.estimate_drive_time(d[3])
            except:
                drive_time = 0

            tk.Button(
                frame,
                text=f"{d[0]} ({d[3]:.1f} km) ({drive_time} min drive)",
                command=lambda n=d[0]: open_drain_menu(n)
            ).pack(fill="x", padx=4, pady=2)


search_var.trace_add("write", update_search)


# 🔥 CLEAN + NO-LAG FIX (focus-based instead of global click)
def on_search_focus_out(event=None):
    search_var.set("")

    for w in frame.winfo_children():
        w.destroy()

    # 🔥 fully remove focus from entry
    search_entry.selection_clear()
    app.focus_set()


# 🔥 ONLY trigger when search box loses focus
search_entry.bind("<FocusOut>", on_search_focus_out)

# 🔥 glitch function (must be ABOVE smiley section)
import random

def glitch_smiley():
    if 'border' not in globals():
        return

    # 🔥 more frequent glitches
    if random.random() < 0.2:

        # 🔥 stronger movement
        glitch_x = random.randint(-12, 12)
        glitch_y = random.randint(-8, 8)

        # 🔥 occasional BIG glitch
        if random.random() < 0.2:
            glitch_x = random.randint(-25, 25)
            glitch_y = random.randint(-15, 15)

        border.place(relx=0.02 + (glitch_x / 1000), rely=smiley_y + (glitch_y / 1000), anchor="sw")

        # 🔥 random duration (less robotic)
        duration = random.choice([30, 50, 80, 120])

        app.after(duration, lambda: border.place(relx=0.02, rely=smiley_y, anchor="sw"))

        # 🔥 double glitch sometimes (extra chaos)
        if random.random() < 0.15:
            app.after(20, lambda: border.place(
                relx=0.02 + (random.randint(-20, 20) / 1000),
                rely=smiley_y + (random.randint(-15, 15) / 1000),
                anchor="sw"
            ))

    # 🔥 faster updates
    app.after(60, glitch_smiley)


# 🔥 animation variables (global)
smiley_y = 0.90
direction = -1

def update_smiley_size(event=None):
        if not PIL_AVAILABLE:
            return

        w = app.winfo_width()

        size = int(w * 0.15)
        size = max(120, size)

        img = Image.open(resource_path("smiley.png")).convert("RGBA")

        small = img.resize((60, 60), Image.NEAREST)
        big = small.resize((size, size), Image.NEAREST)

        tk_img = ImageTk.PhotoImage(big)

        lbl.config(image=tk_img)
        lbl.image = tk_img


# 🔥 smiley
if PIL_AVAILABLE:
    img = Image.open(resource_path("smiley.png")).convert("RGBA")
    tk_img = None

    border = tk.Frame(app, bg="black")
    inner = tk.Frame(border, bg="#dcdcdc")
    inner.pack(padx=1, pady=1)

    lbl = tk.Label(inner, bg="#dcdcdc")
    lbl.pack()

    lbl.bind("<Button-1>", play_smiley_sound)

    update_smiley_size()

    # initial position
    border.place(relx=0.02, rely=0.90, anchor="sw")

    # 🗨 speech bubble (created once)
    bubble = tk.Canvas(
    app,
    width=180,
    height=60,
    bg="#cfcfcf",          # EXACT same as your desktop background
    highlightthickness=0,
    bd=0
)

    bubble.create_rectangle(2, 2, 178, 52, fill="white", outline="black", width=1)
    bubble.create_polygon(
    85, 2,   # top left
    95, 2,   # top right
    90, -8,  # point (above bubble)
    fill="white",
    outline="black"
)

    bubble.create_text(
        90, 30,
        text="don't forget ur torch!",
        font=("Courier", 9, "bold"),
        fill="black"
    )

    # 🔥 animation
    def animate_smiley():
        global smiley_y, direction

        smiley_y += direction * 0.002

        if smiley_y < 0.88:
            direction = 1
        elif smiley_y > 0.92:
            direction = -1

        border.place(relx=0.02, rely=smiley_y, anchor="sw")
        bubble.place(relx=0.15, rely=smiley_y - 0.004, anchor="sw")

        app.after(70, animate_smiley)

    # start animations
    animate_smiley()
    glitch_smiley()

# 🎵 MUSIC CONTROL BAR
music_outer, music_inner = mac_window(app, "Music")
music_outer.place(relx=0.5, rely=1.0, y=-45, anchor="s", width=300, height=120)

# song name
song_canvas = tk.Canvas(
    music_inner,
    height=20,
    bg="#dcdcdc",
    highlightthickness=0
)
song_canvas.pack(fill="x", padx=5)

song_text = song_canvas.create_text(
    0, 10,
    text="",
    anchor="w",
    font=("Courier", 9, "bold")
)

# buttons row
btn_row = tk.Frame(music_inner, bg="#dcdcdc")
btn_row.pack()

# 🔊 VOLUME CONTROLS (NOW IN MUSIC PANEL)
volume_frame = tk.Frame(music_inner, bg="#dcdcdc")
volume_frame.pack(pady=4)

tk.Scale(
    volume_frame,
    from_=0,
    to=1,
    resolution=0.01,
    orient="horizontal",
    variable=volume_var,
    command=update_volume,
    length=120
).pack(side="left", padx=5)

tk.Button(btn_row, text="⏮", command=prev_song, width=4).pack(side="left", padx=4)
tk.Button(btn_row, text="⏯", command=toggle_pause, width=4).pack(side="left", padx=4)
tk.Button(btn_row, text="⏭", command=next_song, width=4).pack(side="left", padx=4)

# 🔻 footer credit
credit = tk.Label(
    app,
    text="CREATED BY WITCH",
    font=("Courier", 10, "bold"),
    bg="#cfcfcf",
    fg="#000"
)

credit.place(relx=0.5, rely=1.0, y=-10, anchor="s")

def check_music():
    for event in pygame.event.get():
        if SONG_END and event.type == SONG_END:
            play_random_song()

    app.after(100, check_music)

if SONG_END:
    check_music()

app.after(1000, start_music)

app.bind("<Configure>", update_smiley_size)

app.after(1000, scroll_song)

update_visited_counter()

app.mainloop()