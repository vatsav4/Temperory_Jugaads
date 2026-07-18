# Temperory_Jugaads

Small Flask app for manually logging Andon/loss-log entries when the automatic
SQL feed into the Power BI "Andon Analytics" dashboard fails.

## Background

`Loss_Log_ShortCut.xlsx` is a one-row export of the SQL table that normally
feeds the dashboard. Its columns map to the dashboard as follows:

- `loss_date_time` → dashboard **End**
- `loss_duration` (seconds) → dashboard **Total Loss** (`loss_duration / 60`, minutes)
- **Start** is not stored — the dashboard computes it as `End - loss_duration`
- `typename` → **Station**
- `loss_comments` → **Reason**
- `loss_lossID_id` → **Loss_Description**, one of 8 fixed loss types (see
  `LOSS_ID_CHOICES` in `app.py`)
- `shop_id_id` → **Line_Name**; fixed at `3` for this page (`SHOP_ID` in
  `app.py`), so it isn't collected on the form

## Database setup

This app connects to the same MSSQL Server previously used by the
`loss_logger` app, via `pyodbc` + a SQL Server login:

- `SQL_SERVER = "172.25.250.70"`
- `SQL_DATABASE = "industry4_157"`
- `SQL_TABLE = "dbo.loss_table"`
- `SHOP_ID = 3`

Credentials are read from environment variables and must not be
committed to the repo:

```bash
export SQL_USERNAME=your_sql_login
export SQL_PASSWORD=your_sql_password
```

Requires the "ODBC Driver 17 for SQL Server" to be installed on the machine
running the app.

On startup the app runs `CREATE TABLE IF NOT EXISTS` (via `OBJECT_ID`) against
`SQL_TABLE`, so if the table already exists with the same name, its existing
schema is left as-is.

## Running

```bash
pip install -r requirements.txt
python app.py
```

Then open http://127.0.0.1:5051 in a browser (see below for why not 5000).

## Using the page

Single page (`/`), built for quick production-floor entry:

**Loss Entries** (top card) — pick a date (defaults to today) to see all rows
in `loss_table` for that day, in the same Start/End/Total Loss/... layout as
the dashboard.

**Add New Entry** (bottom card) — the only fields the person entering data
has to think about:

| Field | How it's entered | Stored as |
|---|---|---|
| Station | Dropdown, 1–12 | `typename = "Station-<n>"` |
| Class Name | Dropdown: Process Call / Quality Call / Material Call / Equipment Call / Others | `classname`, and copied into `loss_plctext` |
| Loss Type | Row of tap/click pills (8 fixed types) | `loss_lossID_id` |
| Date | Date picker | — |
| Loss Start / Loss End | Native time pickers; "Use Current Date & Time" fills Date + End with now | `loss_date_time` (End) and `loss_duration` (computed) |
| Reason | Free text, **required** | `loss_comments` |
| VC Number | Free text, **required** | `vc_model` |

If Loss End's clock time is earlier than Loss Start's, it's treated as
crossing midnight into the next day rather than a validation error.

Everything else is filled in automatically, with no field shown for it:

- `messageno` = 210, `loss_plcclass` = 64, `loss_plctype` = 1009,
  `revision` = 0, `action_flag` = 1, `loss_assignid_id` = 15 — fixed
  constants in `app.py`.
- `counter` = `MAX(counter)` currently in `loss_table`, plus 1.
- `log_date_time` = the moment the entry is saved.
- `shop_id_id` = 3.
- `loss_autofields_id` = `NULL`.

After saving you're taken back to the entries list for that entry's date, so
you can immediately confirm it landed correctly.
