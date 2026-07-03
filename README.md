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

`Loss_Description` and `Line_Name` come from lookup tables joined in by the
report and aren't present as plain values in the exported row, so this app
captures them as free-text fields alongside everything else.

## Running

```bash
pip install -r requirements.txt
python app.py
```

Then open http://127.0.0.1:5000 in a browser.

- **New Entry**: enter the End time, loss duration (minutes), Station, Loss
  Description, Reason, Line Name, and Shift Working. Start time is computed
  automatically as End − duration and shown live on the form.
- **View Entries**: lists everything saved so far in the same
  Start/End/Total Loss/... layout as the dashboard, for verification before
  the data is pushed into the real SQL table.

Data is stored locally in `loss_log.db` (SQLite), created automatically on
first run.
