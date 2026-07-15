import os
from datetime import datetime, time, timedelta

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

# Remaining columns on dbo.loss_table that don't have an obvious
# manual-entry value. Exposed directly on the form so the person entering
# data can type in the real values, instead of the app guessing defaults.
EXTRA_INT_FIELDS = [
    "messageno",
    "loss_plcclass",
    "loss_plctype",
    "revision",
    "counter",
    "action_flag",
    "loss_assignid_id",
]
EXTRA_TEXT_FIELDS = [
    "classname",
    "loss_plctext",
    "loss_autofields_id",
    "vc_model",
]
FIELD_LABELS = {
    "messageno": "Message No.",
    "loss_plcclass": "PLC Class",
    "loss_plctype": "PLC Type",
    "revision": "Revision",
    "counter": "Counter",
    "action_flag": "Action Flag",
    "loss_assignid_id": "Assign ID",
    "classname": "Class Name",
    "loss_plctext": "PLC Text",
    "loss_autofields_id": "Auto Fields ID",
    "vc_model": "VC Model",
}

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


def _parse_time_of_day(raw, label):
    digits = raw.strip().replace(":", "").replace(" ", "")
    if not digits.isdigit() or len(digits) not in (3, 4):
        raise ValueError(f"{label} must be a time like 0754 or 754.")
    digits = digits.zfill(4)
    hh, mm = int(digits[:2]), int(digits[2:])
    if not (0 <= hh <= 23 and 0 <= mm <= 59):
        raise ValueError(f"{label} is not a valid 24-hour time.")
    return time(hh, mm)


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
               loss_lossID_id, loss_comments
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
                "start": start_time.strftime("%m/%d/%Y %I:%M:%S %p"),
                "end": end_time.strftime("%m/%d/%Y %I:%M:%S %p"),
                "total_loss": round(row.loss_duration / 60, 2),
                "typename": row.typename,
                "loss_description": LOSS_ID_CHOICES.get(
                    row.loss_lossID_id, row.loss_lossID_id
                ),
                "loss_comments": row.loss_comments,
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
            typename = request.form["typename"].strip()
            loss_id_raw = request.form.get("loss_id", "")
            loss_comments = request.form.get("loss_comments", "").strip()

            if not typename:
                raise ValueError("Station is required.")
            if not loss_id_raw:
                raise ValueError("Please select a loss type.")
            loss_id = int(loss_id_raw)
            if loss_id not in LOSS_ID_CHOICES:
                raise ValueError("Invalid loss type selected.")

            try:
                entry_date = datetime.strptime(
                    request.form["entry_date"], "%Y-%m-%d"
                ).date()
            except ValueError:
                raise ValueError("Date is required.")

            start_clock = _parse_time_of_day(request.form["start_time"], "Loss Start")
            end_clock = _parse_time_of_day(request.form["end_time"], "Loss End")
            start_time = datetime.combine(entry_date, start_clock)
            end_time = datetime.combine(entry_date, end_clock)
            if end_time <= start_time:
                # Loss End clock-time is earlier than Start - treat it as
                # having rolled past midnight rather than an error.
                end_time += timedelta(days=1)
            loss_duration_seconds = round((end_time - start_time).total_seconds())

            extra_values = {}
            for field in EXTRA_INT_FIELDS:
                raw = request.form.get(field, "").strip()
                if raw:
                    try:
                        extra_values[field] = int(raw)
                    except ValueError:
                        raise ValueError(f"{field} must be a whole number.")
                else:
                    extra_values[field] = None
            for field in EXTRA_TEXT_FIELDS:
                raw = request.form.get(field, "").strip()
                extra_values[field] = raw or None

            columns = [
                "loss_date_time", "log_date_time", "typename", "loss_duration",
                "loss_comments", "loss_lossID_id", "shop_id_id",
            ] + EXTRA_INT_FIELDS + EXTRA_TEXT_FIELDS
            values = (
                end_time, datetime.now(), typename, loss_duration_seconds,
                loss_comments, loss_id, SHOP_ID,
            ) + tuple(extra_values[f] for f in EXTRA_INT_FIELDS) + tuple(
                extra_values[f] for f in EXTRA_TEXT_FIELDS
            )
            placeholders = ", ".join(["?"] * len(columns))

            db = get_db()
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
        loss_id_choices=LOSS_ID_CHOICES,
        selected_date=date_str,
        entries=entries,
        extra_int_fields=EXTRA_INT_FIELDS,
        extra_text_fields=EXTRA_TEXT_FIELDS,
        field_labels=FIELD_LABELS,
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
