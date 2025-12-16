from flask import Flask, render_template, request, redirect, url_for
import sqlite3
from db import get_connection, init_db
import csv
import io
from datetime import datetime

app = Flask(__name__)

# Automatically initialize DB
init_db()

# Distance map for pace calculation
DISTANCES = {
    "5k": 3.1,
    "10k": 6.2,
    "half_marathon": 13.1,
    "marathon": 26.2,
    "50k": 31.07
}

MARATHON_SPLITS = {
    "5k": ("5K", 3.1),
    "10k": ("10K", 6.2),
    "15k": ("15K", 9.3),
    "20k": ("20K", 12.4),
    "half": ("Half", 13.1),
    "25k": ("25K", 15.5),
    "30k": ("30K", 18.6),
    "35k": ("35K", 21.7),
    "40k": ("40K", 24.9),
    "second_half": ("Second Half", 13.1)
}


def calculate_pace(time_str, miles):
    """
    Accepts HH:MM:SS or MM:SS
    """
    try:
        parts = list(map(int, time_str.split(":")))

        if len(parts) == 2:        # MM:SS
            h = 0
            m, s = parts
        elif len(parts) == 3:      # HH:MM:SS
            h, m, s = parts
        else:
            return "N/A"

        total_minutes = h * 60 + m + s / 60
        pace = total_minutes / miles

        pace_min = int(pace)
        pace_sec = int((pace - pace_min) * 60)

        return f"{pace_min}:{pace_sec:02d}/mi"

    except Exception:
        return "N/A"

def subtract_times(total_time, first_half_time):
    """
    Returns total_time - first_half_time
    Accepts HH:MM:SS or MM:SS
    """
    def to_seconds(t):
        parts = list(map(int, t.split(":")))
        if len(parts) == 2:
            h = 0
            m, s = parts
        else:
            h, m, s = parts
        return h * 3600 + m * 60 + s

    try:
        total_sec = to_seconds(total_time)
        first_sec = to_seconds(first_half_time)
        diff = total_sec - first_sec

        if diff <= 0:
            return None

        h = diff // 3600
        m = (diff % 3600) // 60
        s = diff % 60

        return f"{h}:{m:02d}:{s:02d}" if h > 0 else f"{m}:{s:02d}"
    except:
        return None


# ---------------------------
# Routes
# ---------------------------
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/races/add", methods=["GET", "POST"])
def add_race():
    if request.method == "POST":
        conn = get_connection()
        cur = conn.cursor()

        finish_time = request.form["finish_time"]
        race_type = request.form["race_type"]
        pace = calculate_pace(finish_time, DISTANCES.get(race_type, 0))

        cur.execute("""
            INSERT INTO races (date, event_name, location, race_type, finish_time, pace, age, weight)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            request.form["date"],
            request.form["event_name"],
            request.form["location"],
            race_type,
            finish_time,
            pace,
            request.form.get("age"),
            request.form.get("weight")
        ))

        race_id = cur.lastrowid

        half_time = None

        for key, (label, miles) in MARATHON_SPLITS.items():
            if key == "second_half":
                continue  # handled automatically

            split_time = request.form.get(f"split_{key}")
            if split_time:
                if key == "half":
                    half_time = split_time

                split_pace = calculate_pace(split_time, miles)
                cur.execute("""
                    INSERT INTO race_splits (race_id, label, distance_miles, split_time, pace)
                    VALUES (?, ?, ?, ?, ?)
                """, (race_id, label, miles, split_time, split_pace))

        # ✅ AUTO-INSERT SECOND HALF
        if half_time:
            second_half_time = subtract_times(finish_time, half_time)
            if second_half_time:
                second_half_pace = calculate_pace(second_half_time, 13.1)
                cur.execute("""
                    INSERT INTO race_splits (race_id, label, distance_miles, split_time, pace)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    race_id,
                    "Second Half",
                    13.1,
                    second_half_time,
                    second_half_pace
                ))


        conn.commit()
        conn.close()
        return redirect(url_for("list_races"))

    return render_template("race_form.html", splits=MARATHON_SPLITS)



@app.route("/races")
def list_races():
    conn = get_connection()
    cur = conn.cursor()

    query = "SELECT * FROM races WHERE 1=1"
    params = []

    event = request.args.get("event")
    location = request.args.get("location")
    year = request.args.get("year")
    race_type = request.args.get("race_type")

    if event:
        query += " AND event_name LIKE ?"
        params.append(f"%{event}%")

    if location:
        query += " AND location LIKE ?"
        params.append(f"%{location}%")

    if year:
        query += " AND substr(date, 1, 4) = ?"
        params.append(year)

    if race_type:
        query += " AND race_type = ?"
        params.append(race_type)

    query += " ORDER BY date DESC"

    races = cur.execute(query, params).fetchall()

    race_data = []
    for r in races:
        splits = cur.execute(
            "SELECT * FROM race_splits WHERE race_id=?",
            (r["id"],)
        ).fetchall()
        race_data.append((r, splits))

    conn.close()
    return render_template("race_list.html", race_data=race_data)

@app.route("/races/<int:race_id>/edit", methods=["GET", "POST"])
def edit_race(race_id):
    conn = get_connection()
    cur = conn.cursor()

    if request.method == "POST":
        cur.execute("""
            UPDATE races SET date=?, event_name=?, location=?, finish_time=?
            WHERE id=?
        """, (
            request.form["date"],
            request.form["event_name"],
            request.form["location"],
            request.form["finish_time"],
            race_id
        ))


        cur.execute("DELETE FROM race_splits WHERE race_id=?", (race_id,))

        half_time = None
        finish_time = request.form["finish_time"]

        for key, (label, miles) in MARATHON_SPLITS.items():
            if key == "second_half":
                continue

            split_time = request.form.get(f"split_{key}")
            if split_time:
                if key == "half":
                    half_time = split_time

                split_pace = calculate_pace(split_time, miles)
                cur.execute("""
                    INSERT INTO race_splits (race_id, label, distance_miles, split_time, pace)
                    VALUES (?, ?, ?, ?, ?)
                """, (race_id, label, miles, split_time, split_pace))

        # ✅ AUTO-RECALCULATE SECOND HALF
        if half_time:
            second_half_time = subtract_times(finish_time, half_time)
            if second_half_time:
                second_half_pace = calculate_pace(second_half_time, 13.1)
                cur.execute("""
                    INSERT INTO race_splits (race_id, label, distance_miles, split_time, pace)
                    VALUES (?, ?, ?, ?, ?)
                """, (
                    race_id,
                    "Second Half",
                    13.1,
                    second_half_time,
                    second_half_pace
                ))



        conn.commit()
        conn.close()
        return redirect(url_for("list_races"))

    race = cur.execute("SELECT * FROM races WHERE id=?", (race_id,)).fetchone()
    splits = cur.execute("SELECT * FROM race_splits WHERE race_id=?", (race_id,)).fetchall()

    split_map = {s["label"]: s["split_time"] for s in splits}

    return render_template("race_edit.html", race=race, splits=MARATHON_SPLITS, split_map=split_map)

@app.route("/races/<int:race_id>/delete")
def delete_race(race_id):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM races WHERE id=?", (race_id,))
    conn.commit()
    conn.close()
    return redirect(url_for("list_races"))

@app.route("/races/export/csv")
def export_races_csv():
    conn = get_connection()
    cur = conn.cursor()

    output = io.StringIO()
    writer = csv.writer(output)

    # CSV header
    writer.writerow([
        "Date", "Event", "Location", "Race Type",
        "Finish Time", "Overall Pace",
        "Split", "Split Time", "Split Pace"
    ])

    races = cur.execute("SELECT * FROM races ORDER BY date").fetchall()

    for race in races:
        splits = cur.execute(
            "SELECT * FROM race_splits WHERE race_id=?",
            (race["id"],)
        ).fetchall()

        if splits:
            for s in splits:
                writer.writerow([
                    race["date"],
                    race["event_name"],
                    race["location"],
                    race["race_type"],
                    race["finish_time"],
                    race["pace"],
                    s["label"],
                    s["split_time"],
                    s["pace"]
                ])
        else:
            # race without splits
            writer.writerow([
                race["date"],
                race["event_name"],
                race["location"],
                race["race_type"],
                race["finish_time"],
                race["pace"],
                "", "", ""
            ])

    conn.close()

    output.seek(0)
    return (
        output.getvalue(),
        200,
        {
            "Content-Type": "text/csv",
            "Content-Disposition": "attachment; filename=races.csv"
        }
    )


if __name__ == "__main__":
    app.run(debug=True)
