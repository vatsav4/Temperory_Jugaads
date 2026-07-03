import os
import sqlite3
from datetime import datetime, timedelta

from flask import Flask, g, redirect, render_template, request, url_for

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "loss_log.db")

app = Flask(__name__)

# Same columns as the Loss_Log_ShortCut.xlsx export of the SQL table, plus
# loss_description / line_name which are free-text stand-ins for the values
# that normally come from lookup tables joined in by the Power BI report.
SCHEMA = """
CREATE TABLE IF NOT EXISTS loss_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    loss_date_time TEXT NOT NULL,      -- End (from SQL table)
    messageno INTEGER,
    log_date_time TEXT,
    typename TEXT NOT NULL,            -- Station
    classname TEXT,
    loss_duration INTEGER NOT NULL,    -- seconds; Total Loss (min) = loss_duration / 60
    loss_comments TEXT,                -- Reason
    loss_plctext TEXT,
    loss_plcclass INTEGER,
    loss_plctype INTEGER,
    revision INTEGER,
    counter INTEGER,
    action_flag INTEGER,
    loss_assignid_id INTEGER,
    loss_lossID_id INTEGER,
    shop_id_id INTEGER,
    loss_autofields_id INTEGER,
    vc_model TEXT,
    loss_description TEXT,             -- Loss_Description
    line_name TEXT,                    -- Line_Name
    shift_working TEXT,                -- Yes/No
    created_at TEXT NOT NULL
);
"""


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute(SCHEMA)
    conn.commit()
    conn.close()


@app.route("/", methods=["GET", "POST"])
def index():
    error = None
    if request.method == "POST":
        try:
            end_time_raw = request.form["end_time"]
            duration_minutes = float(request.form["duration_minutes"])
            typename = request.form["typename"].strip()
            loss_description = request.form.get("loss_description", "").strip()
            loss_comments = request.form.get("loss_comments", "").strip()
            line_name = request.form.get("line_name", "").strip()
            shift_working = request.form.get("shift_working", "Yes")

            if not typename:
                raise ValueError("Station is required.")
            if duration_minutes <= 0:
                raise ValueError("Loss duration must be greater than 0.")

            try:
                end_time = datetime.strptime(end_time_raw, "%Y-%m-%dT%H:%M:%S")
            except ValueError:
                end_time = datetime.strptime(end_time_raw, "%Y-%m-%dT%H:%M")
            loss_duration_seconds = round(duration_minutes * 60)
            start_time = end_time - timedelta(seconds=loss_duration_seconds)

            db = get_db()
            db.execute(
                """
                INSERT INTO loss_log (
                    loss_date_time, log_date_time, typename, loss_duration,
                    loss_comments, loss_description, line_name, shift_working,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    end_time.isoformat(sep=" "),
                    start_time.isoformat(sep=" "),
                    typename,
                    loss_duration_seconds,
                    loss_comments,
                    loss_description,
                    line_name,
                    shift_working,
                    datetime.now().isoformat(sep=" "),
                ),
            )
            db.commit()
            return redirect(url_for("entries"))
        except (KeyError, ValueError) as exc:
            error = str(exc) or "Please fill in all required fields correctly."

    return render_template("index.html", error=error)


@app.route("/entries")
def entries():
    db = get_db()
    rows = db.execute(
        "SELECT * FROM loss_log ORDER BY loss_date_time DESC"
    ).fetchall()

    computed = []
    for row in rows:
        end_time = datetime.fromisoformat(row["loss_date_time"])
        start_time = end_time - timedelta(seconds=row["loss_duration"])
        computed.append(
            {
                "id": row["id"],
                "start": start_time.strftime("%m/%d/%Y %I:%M:%S %p"),
                "end": end_time.strftime("%m/%d/%Y %I:%M:%S %p"),
                "total_loss": round(row["loss_duration"] / 60, 2),
                "shift_working": row["shift_working"],
                "typename": row["typename"],
                "loss_description": row["loss_description"],
                "loss_comments": row["loss_comments"],
                "line_name": row["line_name"],
            }
        )

    return render_template("entries.html", entries=computed)


if __name__ == "__main__":
    init_db()
    app.run(debug=True)
else:
    init_db()
