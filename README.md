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
`loss_logger` app, via `pyodbc` + a SQL Server login. Before running it,
edit these constants at the top of `app.py`:

- `SQL_DATABASE` — currently `"SampleDatabase"` (placeholder)
- `SQL_TABLE` — currently `"dbo.SampleLossLogTable"` (placeholder)

The server (`SQL_SERVER = "172.25.250.70"`) and `SHOP_ID = 3` are already
set. Credentials are read from environment variables and must not be
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

Then open http://127.0.0.1:5000 in a browser.

- **New Entry**: enter the End time, loss duration (minutes), Station, Loss
  ID (dropdown of the 8 fixed loss types), Reason, and Shift Working. Start
  time is computed automatically as End − duration and shown live on the
  form; `shop_id_id` is set to `3` automatically.
- **View Entries**: lists the most recent 200 rows from the table in the
  same Start/End/Total Loss/... layout as the dashboard, for verification.
