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

Single page (`/`):

- **Entries table**: pick a date (defaults to today) to see all rows in
  `loss_table` for that day, in the same Start/End/Total Loss/... layout as
  the dashboard.
- **+ Add New Entry** (expandable section below the table): Station, Loss
  Type (tap one of the 8 cards), Loss Start / Loss End (with one-tap "Now"
  buttons — duration is computed live), and Reason. `log_date_time` is set
  automatically to the moment you hit Save; `shop_id_id` is set to `3`
  automatically.
- **Additional SQL fields**: the rest of `loss_table`'s columns
  (`messageno`, `classname`, `loss_plctext`, `loss_plcclass`, `loss_plctype`,
  `revision`, `counter`, `action_flag`, `loss_assignid_id`,
  `loss_autofields_id`, `vc_model`) are exposed as plain inputs at the
  bottom of the form — fill in whatever you know for that event; anything
  left blank is stored as `NULL`. After saving you're taken back to the
  list for that entry's date so you can confirm it landed correctly.
