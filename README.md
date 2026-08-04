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

## About the creator

Created by Dinesh Manickan.

I created this tool after buying a team for a football auction. I needed one place to record every player sale, maintain my favourite-player list, and set a maximum amount I was willing to bid for each player. It also helped me track my remaining points and every other team's purse in real time. With that information, I could judge when to bid high for a priority player, when to bid low, and when another team was likely to compete for a player they wanted.

## Use it and improve it

This project was created for a small, niche idea, but if you end up here and it helps with your own auction, feel free to use it and customize it for your needs. You are also welcome to share an idea or feature request so it can be considered for a future update.

## Vibe Coding Project
