from datetime import datetime
from pathlib import Path
import sqlite3
import re
from math import ceil

import pdfplumber
from flask import Flask, flash, g, redirect, render_template, request, url_for

BASE = Path(__file__).resolve().parent
app = Flask(__name__)
app.config.update(DATABASE=BASE / "auction.db", SECRET_KEY="change-this-before-sharing")

MY_TEAM_NAME = "Demo United"
TEAM_SETUP = [
    (MY_TEAM_NAME, "demo-shield.svg"),
    ("Harbor City FC", "demo-shield.svg"),
    ("Northside Rovers", "demo-shield.svg"),
    ("Riverdale Athletic", "demo-shield.svg"),
    ("Summit FC", "demo-shield.svg"),
    ("Metro United", "demo-shield.svg"),
    ("Lakeside Wanderers", "demo-shield.svg"),
    ("Eastgate FC", "demo-shield.svg"),
    ("Cedar Town", "demo-shield.svg"),
    ("Valley Rangers", "demo-shield.svg"),
]
DEMO_PLAYERS = [
    ("DEMO-001", "Alex Carter", "Goalkeeper"), ("DEMO-002", "Jordan Lee", "Defender"),
    ("DEMO-003", "Sam Rivera", "Defender"), ("DEMO-004", "Casey Morgan", "Defender"),
    ("DEMO-005", "Taylor Brooks", "Midfielder"), ("DEMO-006", "Riley Stone", "Midfielder"),
    ("DEMO-007", "Avery Quinn", "Midfielder"), ("DEMO-008", "Cameron Park", "Midfielder"),
    ("DEMO-009", "Jamie Ellis", "Forward"), ("DEMO-010", "Drew Kim", "Forward"),
    ("DEMO-011", "Morgan Shaw", "Goalkeeper"), ("DEMO-012", "Peyton Hall", "Defender"),
    ("DEMO-013", "Rowan Bell", "Defender"), ("DEMO-014", "Skyler Reed", "Midfielder"),
    ("DEMO-015", "Emery Cole", "Midfielder"), ("DEMO-016", "Reese Lane", "Forward"),
    ("DEMO-017", "Blake Young", "Defender"), ("DEMO-018", "Arden Fox", "Forward"),
    ("DEMO-019", "Logan West", "Midfielder"), ("DEMO-020", "Dakota Green", "Defender"),
]
PAGE_SIZE = 20
FORMATION_SLOTS = [
    ('gk', 'Goalkeeper', 'GK'),
    ('df1', 'Left Defender', 'DF'), ('df2', 'Centre Defender', 'DF'), ('df3', 'Right Defender', 'DF'),
    ('mid1', 'Left Midfielder', 'MID'), ('mid2', 'Centre Midfielder', 'MID'), ('mid3', 'Centre Midfielder', 'MID'), ('mid4', 'Right Midfielder', 'MID'),
    ('st', 'Striker', 'ST'),
    ('sub1', 'Substitute 1', 'SUB'), ('sub2', 'Substitute 2', 'SUB'), ('sub3', 'Substitute 3', 'SUB'), ('sub4', 'Substitute 4', 'SUB'),
]

def db():
    if "db" not in g:
        g.db = sqlite3.connect(app.config["DATABASE"])
        g.db.row_factory = sqlite3.Row
    return g.db

@app.teardown_appcontext
def close_db(_error=None):
    conn = g.pop("db", None)
    if conn: conn.close()

def init_db():
    conn = sqlite3.connect(app.config["DATABASE"])
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS teams (
      id INTEGER PRIMARY KEY, name TEXT UNIQUE NOT NULL, logo_file TEXT, starting_purse INTEGER NOT NULL DEFAULT 10000);
    CREATE TABLE IF NOT EXISTS players (
      id INTEGER PRIMARY KEY, player_code TEXT UNIQUE NOT NULL, name TEXT NOT NULL, role TEXT NOT NULL,
      address TEXT, status TEXT NOT NULL DEFAULT 'Available' CHECK(status IN ('Available','Sold','Unsold')),
      team_id INTEGER REFERENCES teams(id), sold_price INTEGER, updated_at TEXT);
    CREATE TABLE IF NOT EXISTS favourites (
      player_id INTEGER PRIMARY KEY REFERENCES players(id), priority TEXT NOT NULL DEFAULT 'Medium',
      expected_price INTEGER, maximum_price INTEGER, notes TEXT);
    CREATE TABLE IF NOT EXISTS auction_records (
      id INTEGER PRIMARY KEY, player_id INTEGER NOT NULL REFERENCES players(id), team_id INTEGER REFERENCES teams(id),
      price INTEGER, status TEXT NOT NULL, created_at TEXT NOT NULL, corrected_at TEXT);
    CREATE TABLE IF NOT EXISTS manual_team_players (
      id INTEGER PRIMARY KEY, name TEXT NOT NULL, role TEXT NOT NULL, notes TEXT, created_at TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS formation_slots (
      slot_code TEXT PRIMARY KEY, label TEXT NOT NULL, slot_type TEXT NOT NULL,
      auction_player_id INTEGER REFERENCES players(id), manual_player_id INTEGER REFERENCES manual_team_players(id));
    """)
    columns = {row[1] for row in conn.execute('PRAGMA table_info(players)')}
    if 'address' not in columns:
        conn.execute('ALTER TABLE players ADD COLUMN address TEXT')
    team_columns = {row[1] for row in conn.execute('PRAGMA table_info(teams)')}
    if 'logo_file' not in team_columns:
        conn.execute('ALTER TABLE teams ADD COLUMN logo_file TEXT')
    # Fixed team IDs preserve all linked auction records while placeholder names are upgraded.
    for team_id, (name, logo_file) in enumerate(TEAM_SETUP, start=1):
        conn.execute('INSERT OR IGNORE INTO teams(id,name,logo_file) VALUES (?,?,?)', (team_id, name, logo_file))
        conn.execute('UPDATE teams SET name=?, logo_file=? WHERE id=?', (name, logo_file, team_id))
    for slot_code, label, slot_type in FORMATION_SLOTS:
        conn.execute('INSERT OR IGNORE INTO formation_slots(slot_code,label,slot_type) VALUES (?,?,?)', (slot_code, label, slot_type))
    seed_demo_data(conn)
    conn.commit(); conn.close()

def seed_demo_data(conn):
    """Create a small fictional dataset on a fresh install so the app can be explored immediately."""
    if conn.execute('SELECT COUNT(*) FROM players').fetchone()[0]:
        return
    now = datetime.now().isoformat(timespec='seconds')
    conn.executemany('INSERT INTO players(player_code,name,role,address,updated_at) VALUES (?,?,?,?,?)',
                     [(code, name, role, 'Demo City', now) for code, name, role in DEMO_PLAYERS])
    for code, priority, expected, maximum, notes in [
        ('DEMO-001', 'High', 900, 1200, 'Reliable goalkeeper'),
        ('DEMO-005', 'High', 1100, 1500, 'Creative midfield option'),
        ('DEMO-009', 'Medium', 1000, 1350, 'Goal-scoring forward'),
    ]:
        player_id = conn.execute('SELECT id FROM players WHERE player_code=?', (code,)).fetchone()[0]
        conn.execute('INSERT INTO favourites(player_id,priority,expected_price,maximum_price,notes) VALUES (?,?,?,?,?)',
                     (player_id, priority, expected, maximum, notes))
    for code, team_id, price in [('DEMO-002', 1, 800), ('DEMO-005', 1, 1200), ('DEMO-010', 2, 950), ('DEMO-013', 3, 700)]:
        player_id = conn.execute('SELECT id FROM players WHERE player_code=?', (code,)).fetchone()[0]
        conn.execute("UPDATE players SET status='Sold',team_id=?,sold_price=?,updated_at=? WHERE id=?", (team_id, price, now, player_id))
        conn.execute("INSERT INTO auction_records(player_id,team_id,price,status,created_at) VALUES (?,?,?,'Sold',?)", (player_id, team_id, price, now))

def import_players_from_pdf(pdf_path):
    """Return (imported, skipped, found) after reading a four-column player-list PDF."""
    rows = []
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            for row in page.extract_table() or []:
                if len(row) < 4 or not row[0] or not re.fullmatch(r'\d+', row[0].strip()):
                    continue
                number, name, address, role = (value.strip().replace('\n', ' ') if value else '' for value in row[:4])
                if name and role:
                    rows.append((f'PDF-{int(number):03}', name, role, address))
    conn = db(); imported = skipped = 0
    now = datetime.now().isoformat(timespec='seconds')
    for code, name, role, address in rows:
        try:
            conn.execute('INSERT INTO players(player_code,name,role,address,updated_at) VALUES (?,?,?,?,?)', (code, name, role, address, now))
            imported += 1
        except sqlite3.IntegrityError:
            skipped += 1
    conn.commit()
    return imported, skipped, len(rows)

def requested_page(parameter='page'):
    try:
        return max(1, int(request.args.get(parameter, 1)))
    except (TypeError, ValueError):
        return 1

def paginate(items, page, per_page=PAGE_SIZE):
    """Paginate a small in-memory result list and return its navigation metadata."""
    total = len(items)
    pages = max(1, ceil(total / per_page))
    page = min(page, pages)
    start = (page - 1) * per_page
    return items[start:start + per_page], {
        'page': page, 'pages': pages, 'total': total,
        'previous': page - 1 if page > 1 else None,
        'next': page + 1 if page < pages else None,
    }

def team_stats():
    return db().execute("""
      SELECT t.*, COALESCE(SUM(CASE WHEN p.status='Sold' THEN p.sold_price END),0) AS spend,
      COUNT(CASE WHEN p.status='Sold' THEN 1 END) AS bought,
      t.starting_purse-COALESCE(SUM(CASE WHEN p.status='Sold' THEN p.sold_price END),0) AS purse
      FROM teams t LEFT JOIN players p ON p.team_id=t.id GROUP BY t.id ORDER BY t.id
    """).fetchall()

def dashboard_data():
    conn = db()
    counts = conn.execute("""SELECT COUNT(*) total, SUM(status='Sold') sold, SUM(status='Unsold') unsold,
      SUM(status='Available') remaining, MAX(sold_price) highest, MIN(sold_price) lowest, AVG(sold_price) average,
      COALESCE(SUM(sold_price),0) total_spend FROM players""").fetchone()
    teams = team_stats(); mine = next((x for x in teams if x['name']==MY_TEAM_NAME), teams[0])
    fav_available = conn.execute("""SELECT COUNT(*) FROM favourites f JOIN players p ON f.player_id=p.id
      WHERE p.status='Available'""").fetchone()[0]
    recent = conn.execute("""SELECT ar.*, p.player_code, p.name player_name, t.name team_name
      FROM auction_records ar JOIN players p ON p.id=ar.player_id LEFT JOIN teams t ON t.id=ar.team_id
      WHERE ar.corrected_at IS NULL ORDER BY ar.id DESC LIMIT 10""").fetchall()
    return counts, teams, mine, fav_available, recent

@app.route('/')
def dashboard():
    summary, teams, mine, fav_available, recent = dashboard_data()
    recent, pager = paginate(list(recent), requested_page('activity_page'), 10)
    return render_template('dashboard.html', data=(summary, teams, mine, fav_available, recent), pager=pager)

@app.route('/auction', methods=['GET', 'POST'])
def auction():
    conn = db()
    teams = team_stats()
    my_team = next((team for team in teams if team['name'] == MY_TEAM_NAME), teams[0])
    favourites = conn.execute("""SELECT p.player_code, p.name, p.role, p.status, f.priority,
      f.expected_price, f.maximum_price, f.notes FROM favourites f JOIN players p ON p.id=f.player_id
      ORDER BY CASE f.priority WHEN 'High' THEN 1 WHEN 'Medium' THEN 2 ELSE 3 END, p.name""").fetchall()
    query = request.args.get('q', '').strip()
    player = None
    if query:
        # Accept a numeric suffix such as "1" or "001" as well as a full player code.
        numeric_id = int(query) if query.isdigit() else None
        player = conn.execute("""SELECT p.*, f.priority FROM players p LEFT JOIN favourites f ON f.player_id=p.id
          WHERE lower(p.player_code)=lower(?)
             OR (? IS NOT NULL AND p.player_code GLOB '*-' || printf('%03d', ?))
             OR lower(p.name) LIKE lower(?)
          ORDER BY CASE WHEN lower(p.player_code)=lower(?) THEN 0
                        WHEN ? IS NOT NULL AND p.player_code GLOB '*-' || printf('%03d', ?) THEN 1 ELSE 2 END, p.name
          LIMIT 1""", (query, numeric_id, numeric_id, f'%{query}%', query, numeric_id, numeric_id)).fetchone()
    if request.method == 'POST':
        player = conn.execute('SELECT * FROM players WHERE id=?', (request.form['player_id'],)).fetchone()
        action = request.form['action']
        if player['status'] != 'Available':
            flash('Only available players can be recorded. Use the latest-sale correction panel for changes.', 'error')
            return redirect(url_for('auction', q=player['player_code']))
        now = datetime.now().isoformat(timespec='seconds')
        if action == 'unsold':
            conn.execute("UPDATE players SET status='Unsold', updated_at=? WHERE id=?", (now, player['id']))
            conn.execute("INSERT INTO auction_records(player_id,status,created_at) VALUES (?, 'Unsold', ?)", (player['id'], now))
            conn.commit(); flash(f"{player['name']} marked unsold.", 'success')
            return redirect(url_for('auction'))
        try: price = int(request.form['price'])
        except (ValueError, TypeError): price = 0
        team_id = request.form.get('team_id', type=int)
        stats = next((t for t in teams if t['id'] == team_id), None)
        if not stats or price <= 0: flash('Choose a team and enter a positive winning price.', 'error')
        elif stats['bought'] >= 13: flash(f"{stats['name']} already has the maximum 13 players.", 'error')
        elif price > stats['purse']: flash(f"{stats['name']} has only {stats['purse']:,} points remaining.", 'error')
        else:
            conn.execute("UPDATE players SET status='Sold', team_id=?, sold_price=?, updated_at=? WHERE id=?", (team_id, price, now, player['id']))
            conn.execute("INSERT INTO auction_records(player_id,team_id,price,status,created_at) VALUES (?,?,?,'Sold',?)", (player['id'], team_id, price, now))
            conn.commit(); flash(f"Saved: {player['name']} to {stats['name']} for {price:,} points.", 'success')
            return redirect(url_for('auction'))
    return render_template('auction.html', player=player, query=query, teams=teams, my_team=my_team, favourites=favourites)

@app.route('/players', methods=['GET', 'POST'])
def players():
    conn = db()
    if request.method == 'POST':
        uploaded = request.files.get('player_pdf')
        if uploaded and uploaded.filename:
            if not uploaded.filename.lower().endswith('.pdf'):
                flash('Please choose a PDF file.', 'error')
            else:
                import_dir = BASE / 'uploads'; import_dir.mkdir(exist_ok=True)
                path = import_dir / 'player-list.pdf'
                uploaded.save(path)
                try:
                    imported, skipped, found = import_players_from_pdf(path)
                    if found:
                        flash(f'PDF imported: {imported} players added, {skipped} already existed.', 'success')
                    else:
                        flash('No player rows were found in that PDF. Use a four-column player-list table.', 'error')
                except Exception:
                    flash('The PDF could not be read. Please use a text-based player-list PDF.', 'error')
            return redirect(url_for('players'))
        code, name, role = (request.form[k].strip() for k in ('player_code','name','role'))
        try:
            conn.execute('INSERT INTO players(player_code,name,role,updated_at) VALUES (?,?,?,?)', (code,name,role,datetime.now().isoformat(timespec='seconds')))
            conn.commit(); flash('Player added.', 'success')
        except sqlite3.IntegrityError: flash('That Player ID already exists.', 'error')
        return redirect(url_for('players'))
    search = request.args.get('q','').strip()
    role_filter = request.args.get('role', '').strip()
    status_filter = request.args.get('status', '').strip()
    roles = conn.execute('SELECT DISTINCT role FROM players WHERE role <> "" ORDER BY role').fetchall()
    rows = conn.execute("""SELECT p.*, f.priority, f.maximum_price FROM players p LEFT JOIN favourites f ON f.player_id=p.id
      WHERE (p.player_code LIKE ? OR p.name LIKE ?)
        AND (? = '' OR p.role = ?)
        AND (? = '' OR p.status = ?)
      ORDER BY p.player_code""", (f'%{search}%', f'%{search}%', role_filter, role_filter, status_filter, status_filter)).fetchall()
    rows, pager = paginate(list(rows), requested_page())
    return render_template('players.html', players=rows, search=search, roles=roles, role_filter=role_filter, status_filter=status_filter, pager=pager)

@app.route('/favourites/<int:player_id>', methods=['GET', 'POST'])
def favourite(player_id):
    conn=db(); player=conn.execute('SELECT * FROM players WHERE id=?',(player_id,)).fetchone()
    if not player: return redirect(url_for('players'))
    if request.method=='POST':
        conn.execute("""INSERT INTO favourites(player_id,priority,expected_price,maximum_price,notes) VALUES (?,?,?,?,?)
        ON CONFLICT(player_id) DO UPDATE SET priority=excluded.priority, expected_price=excluded.expected_price,
        maximum_price=excluded.maximum_price, notes=excluded.notes""", (player_id,request.form['priority'],request.form.get('expected_price') or None,request.form.get('maximum_price') or None,request.form['notes']))
        conn.commit(); flash('Strategy saved.', 'success'); return redirect(url_for('favourites'))
    fav=conn.execute('SELECT * FROM favourites WHERE player_id=?',(player_id,)).fetchone()
    return render_template('favourite_form.html', player=player, fav=fav)

@app.route('/favourites')
def favourites():
    rows=db().execute("SELECT p.*,f.* FROM favourites f JOIN players p ON p.id=f.player_id ORDER BY CASE f.priority WHEN 'High' THEN 1 WHEN 'Medium' THEN 2 ELSE 3 END,p.name").fetchall()
    rows, pager = paginate(list(rows), requested_page())
    return render_template('favourites.html', favourites=rows, pager=pager)

def my_team_data():
    conn = db()
    my_team = conn.execute('SELECT * FROM teams WHERE name=?', (MY_TEAM_NAME,)).fetchone()
    bought = conn.execute("SELECT * FROM players WHERE team_id=? AND status='Sold' ORDER BY role,name", (my_team['id'],)).fetchall()
    manual = conn.execute('SELECT * FROM manual_team_players ORDER BY role,name').fetchall()
    favourites = conn.execute("""SELECT p.*, f.priority, f.expected_price, f.maximum_price, f.notes FROM favourites f
      JOIN players p ON p.id=f.player_id ORDER BY CASE f.priority WHEN 'High' THEN 1 WHEN 'Medium' THEN 2 ELSE 3 END,p.name""").fetchall()
    slots = conn.execute('SELECT * FROM formation_slots ORDER BY CASE slot_code WHEN "st" THEN 1 WHEN "mid1" THEN 2 WHEN "mid2" THEN 3 WHEN "mid3" THEN 4 WHEN "mid4" THEN 5 WHEN "df1" THEN 6 WHEN "df2" THEN 7 WHEN "df3" THEN 8 WHEN "gk" THEN 9 ELSE 10 END, slot_code').fetchall()
    candidates = []
    for player in bought:
        candidates.append({'ref': f"auction:{player['id']}", 'name': player['name'], 'role': player['role'], 'kind': 'Auction player'})
    for player in manual:
        candidates.append({'ref': f"manual:{player['id']}", 'name': player['name'], 'role': player['role'], 'kind': 'Manual player'})
    candidate_map = {candidate['ref']: candidate for candidate in candidates}
    prepared_slots = []
    for slot in slots:
        selected_ref = f"auction:{slot['auction_player_id']}" if slot['auction_player_id'] else (f"manual:{slot['manual_player_id']}" if slot['manual_player_id'] else '')
        prepared_slots.append({**dict(slot), 'selected_ref': selected_ref, 'selected': candidate_map.get(selected_ref)})
    return my_team, bought, manual, favourites, candidates, prepared_slots

@app.route('/my-team', methods=['GET', 'POST'])
def my_team():
    conn = db()
    if request.method == 'POST':
        action = request.form.get('action')
        if action == 'add_manual':
            name, role = request.form.get('name', '').strip(), request.form.get('role', '').strip()
            if not name or not role:
                flash('Enter a player name and role.', 'error')
            else:
                conn.execute('INSERT INTO manual_team_players(name,role,notes,created_at) VALUES (?,?,?,?)', (name, role, request.form.get('notes', '').strip(), datetime.now().isoformat(timespec='seconds')))
                conn.commit(); flash(f'{name} added as a manual team player.', 'success')
            return redirect(url_for('my_team'))
        if action == 'assign':
            slot_code, player_ref = request.form.get('slot_code'), request.form.get('player_ref', '')
            valid_slots = {slot[0] for slot in FORMATION_SLOTS}
            if slot_code not in valid_slots:
                flash('Invalid formation position.', 'error'); return redirect(url_for('my_team'))
            auction_id = manual_id = None
            if player_ref:
                try:
                    kind, raw_id = player_ref.split(':', 1); player_id = int(raw_id)
                    if kind == 'auction':
                        mine = conn.execute("SELECT 1 FROM players p JOIN teams t ON t.id=p.team_id WHERE p.id=? AND p.status='Sold' AND t.name=?", (player_id, MY_TEAM_NAME)).fetchone()
                        auction_id = player_id if mine else None
                    elif kind == 'manual':
                        manual_id = player_id if conn.execute('SELECT 1 FROM manual_team_players WHERE id=?', (player_id,)).fetchone() else None
                except (ValueError, AttributeError):
                    pass
                if auction_id is None and manual_id is None:
                    flash('That player is not available for your formation.', 'error'); return redirect(url_for('my_team'))
                duplicate = conn.execute('SELECT label FROM formation_slots WHERE slot_code<>? AND (auction_player_id=? OR manual_player_id=?)', (slot_code, auction_id, manual_id)).fetchone()
                if duplicate:
                    flash(f"That player is already assigned to {duplicate['label']}.", 'error'); return redirect(url_for('my_team'))
            conn.execute('UPDATE formation_slots SET auction_player_id=?, manual_player_id=? WHERE slot_code=?', (auction_id, manual_id, slot_code))
            conn.commit(); flash('Formation updated.', 'success')
    return render_template('my_team.html', data=my_team_data())

@app.route('/teams/<int:team_id>')
def team(team_id):
    stats=next((t for t in team_stats() if t['id']==team_id), None)
    if not stats: return redirect(url_for('dashboard'))
    roster=db().execute("SELECT * FROM players WHERE team_id=? AND status='Sold' ORDER BY role,name",(team_id,)).fetchall()
    roster, pager = paginate(list(roster), requested_page())
    return render_template('team.html', team=stats, roster=roster, pager=pager)

@app.route('/reports')
def reports():
    summary, teams, mine, fav_available, recent = dashboard_data()
    teams, pager = paginate(list(teams), requested_page(), 5)
    rosters = {t['id']: db().execute("SELECT * FROM players WHERE team_id=? AND status='Sold' ORDER BY name", (t['id'],)).fetchall() for t in teams}
    return render_template('reports.html', data=(summary, teams, mine, fav_available, recent), rosters=rosters, pager=pager)

@app.route('/correct-latest', methods=['POST'])
def correct_latest():
    conn=db(); rec=conn.execute("SELECT * FROM auction_records WHERE corrected_at IS NULL ORDER BY id DESC LIMIT 1").fetchone()
    if not rec: flash('There is no transaction to correct.', 'error'); return redirect(url_for('dashboard'))
    conn.execute("UPDATE auction_records SET corrected_at=? WHERE id=?", (datetime.now().isoformat(timespec='seconds'),rec['id']))
    conn.execute("UPDATE players SET status='Available',team_id=NULL,sold_price=NULL,updated_at=? WHERE id=?", (datetime.now().isoformat(timespec='seconds'),rec['player_id']))
    conn.commit(); flash('Latest transaction reversed; the player is available again.', 'success'); return redirect(url_for('auction'))

if __name__ == '__main__':
    init_db()
    app.run(debug=True)
