import os
from datetime import datetime, timedelta

import pyodbc
from flask import Flask, g, redirect, render_template, request, url_for

app = Flask(__name__)

# --- SQL Server connection -------------------------------------------------
# Same server used previously by the loss_logger app.
SQL_SERVER = "172.25.250.70"
SQL_DATABASE = "industry4_157"
SQL_TABLE = "dbo.loss_table"

SQL_USERNAME = os.environ.get("SQL_USERNAME", "REPLACE_USERNAME")
SQL_PASSWORD = os.environ.get("SQL_PASSWORD", "REPLACE_PASSWORD")

ODBC_DRIVER = "ODBC Driver 17 for SQL Server"

# shop_id_id is fixed for this page (this form only serves one shop/line).
SHOP_ID = 3

# Stations 1-12, stored as "Station-<n>".
STATION_CHOICES = list(range(1, 13))

# The 8 loss types (loss_lossID_id -> display text), from the lookup table.
LOSS_ID_CHOICES = {
    1: "Breakdown/ Facility Constraint",
    3: "Short / Stoppages",
    4: "Late Start/ Early Stoppage of Production",
    5: "Defects/ Repair/ Rework",
    6: "Model Change/ Tool Change",
    7: "Due to Operator",
    8: "New Product Introduction",
    32: "Material Supply",
}

CLASSNAME_CHOICES = [
    "Process Call",
    "Quality Call",
    "Material Call",
    "Equipment Call",
    "Others",
]

# Fixed values for legacy/PLC-sourced columns that production entry doesn't
# need to think about.
FIXED_MESSAGE_NO = 210
FIXED_PLC_CLASS = 64
FIXED_PLC_TYPE = 1009
FIXED_REVISION = 0
FIXED_ACTION_FLAG = 1
FIXED_ASSIGN_ID = 15

CREATE_TABLE_SQL = f"""
IF OBJECT_ID(N'{SQL_TABLE}', N'U') IS NULL
BEGIN
    CREATE TABLE {SQL_TABLE} (
        id INT IDENTITY(1,1) PRIMARY KEY,
        loss_date_time DATETIME NOT NULL,   -- End
        messageno INT NULL,
        log_date_time DATETIME NULL,
        typename NVARCHAR(100) NOT NULL,    -- Station
        classname NVARCHAR(100) NULL,
        loss_duration INT NOT NULL,         -- seconds; Total Loss (min) = loss_duration / 60
        loss_comments NVARCHAR(255) NULL,   -- Reason
        loss_plctext NVARCHAR(255) NULL,
        loss_plcclass INT NULL,
        loss_plctype INT NULL,
        revision INT NULL,
        counter BIGINT NULL,
        action_flag INT NULL,
        loss_assignid_id INT NULL,
        loss_lossID_id INT NOT NULL,        -- Loss ID (see LOSS_ID_CHOICES)
        shop_id_id INT NOT NULL,
        loss_autofields_id NVARCHAR(50) NULL,
        vc_model NVARCHAR(100) NULL
    )
END
"""


def connect_db():
    conn_str = (
        f"DRIVER={{{ODBC_DRIVER}}};"
        f"SERVER={SQL_SERVER};"
        f"DATABASE={SQL_DATABASE};"
        f"UID={SQL_USERNAME};"
        f"PWD={SQL_PASSWORD};"
        f"TrustServerCertificate=yes;"
    )
    return pyodbc.connect(conn_str)


def get_db():
    if "db" not in g:
        g.db = connect_db()
    return g.db


@app.teardown_appcontext
def close_db(exception=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    conn = connect_db()
    conn.execute(CREATE_TABLE_SQL)
    conn.commit()
    conn.close()


def next_counter(db):
    row = db.execute(f"SELECT MAX(counter) FROM {SQL_TABLE}").fetchone()
    last = row[0] if row else None
    return (last or 0) + 1


def fetch_entries_for_date(date_str):
    try:
        selected_date = datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError:
        selected_date = datetime.now()
    date_str = selected_date.strftime("%Y-%m-%d")

    range_start = selected_date.replace(hour=0, minute=0, second=0, microsecond=0)
    range_end = range_start + timedelta(days=1)

    db = get_db()
    rows = db.execute(
        f"""
        SELECT loss_date_time, loss_duration, typename,
               loss_lossID_id, loss_comments, classname, vc_model
        FROM {SQL_TABLE}
        WHERE loss_date_time >= ? AND loss_date_time < ?
        ORDER BY loss_date_time DESC
        """,
        (range_start, range_end),
    ).fetchall()

    computed = []
    for row in rows:
        end_time = row.loss_date_time
        start_time = end_time - timedelta(seconds=row.loss_duration)
        computed.append(
            {
                "start": start_time.strftime("%m/%d/%Y %I:%M %p"),
                "end": end_time.strftime("%m/%d/%Y %I:%M %p"),
                "total_loss": round(row.loss_duration / 60, 2),
                "typename": row.typename,
                "loss_description": LOSS_ID_CHOICES.get(
                    row.loss_lossID_id, row.loss_lossID_id
                ),
                "loss_comments": row.loss_comments,
                "classname": row.classname,
                "vc_model": row.vc_model,
            }
        )
    return date_str, computed


@app.route("/", methods=["GET", "POST"])
def index():
    error = None
    saved = request.args.get("saved") == "1"
    date_str = request.args.get("date", "").strip()

    if request.method == "POST":
        try:
            station_raw = request.form.get("station", "")
            if not station_raw:
                raise ValueError("Please select a Station.")
            station_no = int(station_raw)
            if station_no not in STATION_CHOICES:
                raise ValueError("Invalid Station selected.")
            typename = f"Station-{station_no}"

            classname = request.form.get("classname", "")
            if classname not in CLASSNAME_CHOICES:
                raise ValueError("Please select a Class Name.")

            loss_id_raw = request.form.get("loss_id", "")
            if not loss_id_raw:
                raise ValueError("Please select a Loss Type.")
            loss_id = int(loss_id_raw)
            if loss_id not in LOSS_ID_CHOICES:
                raise ValueError("Invalid Loss Type selected.")

            loss_comments = request.form.get("loss_comments", "").strip()
            if not loss_comments:
                raise ValueError("Reason is required.")

            vc_model = request.form.get("vc_model", "").strip()
            if not vc_model:
                raise ValueError("VC Number is required.")

            entry_date = request.form.get("entry_date", "")
            start_raw = request.form.get("start_time", "")
            end_raw = request.form.get("end_time", "")
            try:
                start_time = datetime.strptime(
                    f"{entry_date} {start_raw}", "%Y-%m-%d %H:%M"
                )
                end_time = datetime.strptime(
                    f"{entry_date} {end_raw}", "%Y-%m-%d %H:%M"
                )
            except ValueError:
                raise ValueError("Please provide a valid Date, Loss Start and Loss End.")

            if end_time <= start_time:
                # End clock-time earlier than Start - treat as crossing
                # midnight into the next day rather than an error.
                end_time += timedelta(days=1)
            loss_duration_seconds = round((end_time - start_time).total_seconds())

            db = get_db()
            counter = next_counter(db)

            columns = [
                "loss_date_time", "log_date_time", "typename", "classname",
                "loss_duration", "loss_comments", "loss_plctext",
                "loss_plcclass", "loss_plctype", "revision", "counter",
                "action_flag", "loss_assignid_id", "loss_lossID_id",
                "shop_id_id", "loss_autofields_id", "vc_model",
                "messageno",
            ]
            values = (
                end_time, datetime.now(), typename, classname,
                loss_duration_seconds, loss_comments, classname,
                FIXED_PLC_CLASS, FIXED_PLC_TYPE, FIXED_REVISION, counter,
                FIXED_ACTION_FLAG, FIXED_ASSIGN_ID, loss_id,
                SHOP_ID, None, vc_model,
                FIXED_MESSAGE_NO,
            )
            placeholders = ", ".join(["?"] * len(columns))

            db.execute(
                f"INSERT INTO {SQL_TABLE} ({', '.join(columns)}) VALUES ({placeholders})",
                values,
            )
            db.commit()
            return redirect(
                url_for("index", date=end_time.strftime("%Y-%m-%d"), saved=1)
            )
        except (KeyError, ValueError) as exc:
            error = str(exc) or "Please fill in all required fields correctly."

    date_str, entries = fetch_entries_for_date(date_str)

    return render_template(
        "index.html",
        error=error,
        saved=saved,
        station_choices=STATION_CHOICES,
        classname_choices=CLASSNAME_CHOICES,
        loss_id_choices=LOSS_ID_CHOICES,
        selected_date=date_str,
        entries=entries,
    )


if __name__ == "__main__":
    init_db()
    # Default port changed from Flask's usual 5000: on Windows, 5000 (and
    # other common ports) can fall inside a Hyper-V/WSL2 excluded port
    # range, causing "WinError 10013: forbidden by its access permissions"
    # when the dev server tries to bind. Override with FLASK_RUN_PORT if
    # this one is also blocked.
    port = int(os.environ.get("FLASK_RUN_PORT", 5051))
    app.run(host="127.0.0.1", port=port, debug=True)
else:
    init_db()
