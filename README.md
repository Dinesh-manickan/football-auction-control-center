# Football Auction Control Center

Run locally:

```powershell
cd C:\Football
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```

Open http://127.0.0.1:5000. The SQLite database is created automatically. Add players from **Players**, then use **Live Auction** to record results.

The application starts with a small fictional demo dataset so you can try the workflow immediately. The **Players** page can import four-column player-list PDFs. Re-uploading the same list is safe: existing player IDs are skipped.
