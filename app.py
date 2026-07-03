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
        counter INT NULL,
        action_flag INT NULL,
        loss_assignid_id INT NULL,
        loss_lossID_id INT NOT NULL,        -- Loss ID (see LOSS_ID_CHOICES)
        shop_id_id INT NOT NULL,
        loss_autofields_id INT NULL,
        vc_model NVARCHAR(100) NULL,
        created_at DATETIME NOT NULL
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


@app.route("/", methods=["GET", "POST"])
def index():
    error = None
    if request.method == "POST":
        try:
            end_time_raw = request.form["end_time"]
            duration_minutes = float(request.form["duration_minutes"])
            typename = request.form["typename"].strip()
            loss_id = int(request.form["loss_id"])
            loss_comments = request.form.get("loss_comments", "").strip()

            if not typename:
                raise ValueError("Station is required.")
            if duration_minutes <= 0:
                raise ValueError("Loss duration must be greater than 0.")
            if loss_id not in LOSS_ID_CHOICES:
                raise ValueError("Invalid Loss ID selected.")

            try:
                end_time = datetime.strptime(end_time_raw, "%Y-%m-%dT%H:%M:%S")
            except ValueError:
                end_time = datetime.strptime(end_time_raw, "%Y-%m-%dT%H:%M")
            loss_duration_seconds = round(duration_minutes * 60)
            start_time = end_time - timedelta(seconds=loss_duration_seconds)

            db = get_db()
            db.execute(
                f"""
                INSERT INTO {SQL_TABLE} (
                    loss_date_time, log_date_time, typename, loss_duration,
                    loss_comments, loss_lossID_id, shop_id_id,
                    created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    end_time,
                    start_time,
                    typename,
                    loss_duration_seconds,
                    loss_comments,
                    loss_id,
                    SHOP_ID,
                    datetime.now(),
                ),
            )
            db.commit()
            return redirect(url_for("entries"))
        except (KeyError, ValueError) as exc:
            error = str(exc) or "Please fill in all required fields correctly."

    return render_template(
        "index.html", error=error, loss_id_choices=LOSS_ID_CHOICES
    )


@app.route("/entries")
def entries():
    date_str = request.args.get("date", "").strip()
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

    return render_template("entries.html", entries=computed, selected_date=date_str)


if __name__ == "__main__":
    init_db()
    app.run(debug=True)
else:
    init_db()
