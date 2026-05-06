from flask import Flask, render_template, request, redirect, url_for, g, abort
import sqlite3
from pathlib import Path
from datetime import date, datetime, timedelta
import uuid
import calendar

APP_DIR = Path(__file__).resolve().parent
DB_PATH = APP_DIR / 'scheduler.db'

app = Flask(__name__)
app.config['SECRET_KEY'] = 'simple-meeting-scheduler'

DEFAULT_NOTE = '안내: 저녁 6시 회식이 어려운 날짜는 안됨, 일찍 가거나 늦참만 가능한 날짜는 부분참여로 선택해 주세요.'


def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(error=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()


def init_db():
    db = sqlite3.connect(DB_PATH)
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS polls (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            token TEXT NOT NULL UNIQUE,
            title TEXT NOT NULL,
            note TEXT NOT NULL,
            start_date TEXT NOT NULL,
            end_date TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS responses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            poll_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            submitted_at TEXT NOT NULL,
            UNIQUE(poll_id, name),
            FOREIGN KEY (poll_id) REFERENCES polls(id)
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS unavailable_dates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            response_id INTEGER NOT NULL,
            selected_date TEXT NOT NULL,
            UNIQUE(response_id, selected_date),
            FOREIGN KEY (response_id) REFERENCES responses(id)
        )
        """
    )
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS partial_dates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            response_id INTEGER NOT NULL,
            selected_date TEXT NOT NULL,
            UNIQUE(response_id, selected_date),
            FOREIGN KEY (response_id) REFERENCES responses(id)
        )
        """
    )
    db.commit()
    db.close()


def daterange(start: date, end: date):
    cur = start
    while cur <= end:
        yield cur
        cur += timedelta(days=1)


def build_months(start: date, end: date, status_map=None):
    status_map = dict(status_map or {})
    months = []
    current = date(start.year, start.month, 1)
    while current <= end:
        cal = calendar.Calendar(firstweekday=6)
        weeks = []
        for week in cal.monthdatescalendar(current.year, current.month):
            row = []
            for d in week:
                in_range = start <= d <= end
                in_month = d.month == current.month
                row.append({
                    'date': d,
                    'iso': d.isoformat(),
                    'day': d.day,
                    'in_month': in_month,
                    'in_range': in_range,
                    'status': status_map.get(d.isoformat(), 'full'),
                })
            weeks.append(row)
        months.append({
            'year': current.year,
            'month': current.month,
            'label': f'{current.year}년 {current.month}월',
            'weeks': weeks,
        })
        if current.month == 12:
            current = date(current.year + 1, 1, 1)
        else:
            current = date(current.year, current.month + 1, 1)
    return months


def get_poll_by_token(token):
    db = get_db()
    poll = db.execute('SELECT * FROM polls WHERE token = ?', (token,)).fetchone()
    if not poll:
        abort(404)
    return poll


def get_status_map(db, response_id):
    status_map = {}
    for row in db.execute('SELECT selected_date FROM unavailable_dates WHERE response_id = ?', (response_id,)).fetchall():
        status_map[row['selected_date']] = 'unavailable'
    for row in db.execute('SELECT selected_date FROM partial_dates WHERE response_id = ?', (response_id,)).fetchall():
        status_map[row['selected_date']] = 'partial'
    return status_map


@app.route('/')
def home():
    today = date.today()
    default_start = max(today + timedelta(days=1), date(today.year, 5, 7))
    default_end = date(today.year, 6, 30)
    return render_template('home.html', default_start=default_start.isoformat(), default_end=default_end.isoformat(), default_note=DEFAULT_NOTE)


@app.route('/create', methods=['POST'])
def create_poll():
    title = (request.form.get('title') or '회식 날짜 조율').strip()
    note = (request.form.get('note') or DEFAULT_NOTE).strip()
    start_date = request.form.get('start_date')
    end_date = request.form.get('end_date')
    try:
        start = date.fromisoformat(start_date)
        end = date.fromisoformat(end_date)
    except Exception:
        return '날짜 형식이 올바르지 않습니다.', 400
    if start > end:
        return '시작일은 종료일보다 빠르거나 같아야 합니다.', 400

    token = uuid.uuid4().hex[:10]
    db = get_db()
    db.execute(
        'INSERT INTO polls (token, title, note, start_date, end_date, created_at) VALUES (?, ?, ?, ?, ?, ?)',
        (token, title, note, start.isoformat(), end.isoformat(), datetime.now().isoformat(timespec='seconds'))
    )
    db.commit()
    return redirect(url_for('created', token=token))


@app.route('/created/<token>')
def created(token):
    poll = get_poll_by_token(token)
    return render_template('created.html', poll=poll)


@app.route('/poll/<token>', methods=['GET', 'POST'])
def poll_view(token):
    poll = get_poll_by_token(token)
    start = date.fromisoformat(poll['start_date'])
    end = date.fromisoformat(poll['end_date'])
    db = get_db()

    if request.method == 'POST':
        name = (request.form.get('name') or '').strip()
        if not name:
            months = build_months(start, end)
            return render_template('poll.html', poll=poll, months=months, error='이름을 입력해 주세요.', existing_name='', status_map={})

        valid_dates = [d.isoformat() for d in daterange(start, end)]
        unavailable_dates = []
        partial_dates = []
        for iso in valid_dates:
            status = request.form.get(f'status_{iso}', 'full')
            if status == 'unavailable':
                unavailable_dates.append(iso)
            elif status == 'partial':
                partial_dates.append(iso)

        existing = db.execute('SELECT id FROM responses WHERE poll_id = ? AND name = ?', (poll['id'], name)).fetchone()
        now = datetime.now().isoformat(timespec='seconds')
        if existing:
            response_id = existing['id']
            db.execute('UPDATE responses SET submitted_at = ? WHERE id = ?', (now, response_id))
            db.execute('DELETE FROM unavailable_dates WHERE response_id = ?', (response_id,))
            db.execute('DELETE FROM partial_dates WHERE response_id = ?', (response_id,))
        else:
            cur = db.execute('INSERT INTO responses (poll_id, name, submitted_at) VALUES (?, ?, ?)', (poll['id'], name, now))
            response_id = cur.lastrowid

        for d in unavailable_dates:
            db.execute('INSERT OR IGNORE INTO unavailable_dates (response_id, selected_date) VALUES (?, ?)', (response_id, d))
        for d in partial_dates:
            db.execute('INSERT OR IGNORE INTO partial_dates (response_id, selected_date) VALUES (?, ?)', (response_id, d))
        db.commit()
        return redirect(url_for('thanks', token=token, name=name))

    existing_name = request.args.get('name', '').strip()
    status_map = {}
    if existing_name:
        existing = db.execute('SELECT id FROM responses WHERE poll_id = ? AND name = ?', (poll['id'], existing_name)).fetchone()
        if existing:
            status_map = get_status_map(db, existing['id'])
    months = build_months(start, end, status_map)
    return render_template('poll.html', poll=poll, months=months, error=None, existing_name=existing_name, status_map=status_map)


@app.route('/poll/<token>/thanks')
def thanks(token):
    poll = get_poll_by_token(token)
    name = request.args.get('name', '').strip()
    return render_template('thanks.html', poll=poll, name=name)


@app.route('/poll/<token>/summary')
def summary(token):
    poll = get_poll_by_token(token)
    start = date.fromisoformat(poll['start_date'])
    end = date.fromisoformat(poll['end_date'])
    db = get_db()
    participants = db.execute('SELECT COUNT(*) AS cnt FROM responses WHERE poll_id = ?', (poll['id'],)).fetchone()['cnt']
    unavail_rows = db.execute(
        """
        SELECT u.selected_date, COUNT(DISTINCT u.response_id) AS cnt
        FROM unavailable_dates u
        JOIN responses r ON r.id = u.response_id
        WHERE r.poll_id = ?
        GROUP BY u.selected_date
        """,
        (poll['id'],)
    ).fetchall()
    partial_rows = db.execute(
        """
        SELECT p.selected_date, COUNT(DISTINCT p.response_id) AS cnt
        FROM partial_dates p
        JOIN responses r ON r.id = p.response_id
        WHERE r.poll_id = ?
        GROUP BY p.selected_date
        """,
        (poll['id'],)
    ).fetchall()
    unavail_map = {row['selected_date']: row['cnt'] for row in unavail_rows}
    partial_map = {row['selected_date']: row['cnt'] for row in partial_rows}

    results = []
    best_score = -1
    for d in daterange(start, end):
        unavailable = unavail_map.get(d.isoformat(), 0)
        partial = partial_map.get(d.isoformat(), 0)
        full = max(participants - unavailable - partial, 0)
        weighted = full + (partial * 0.5)
        item = {
            'date': d,
            'weighted': weighted,
            'full': full,
            'partial': partial,
            'unavailable': unavailable,
            'participants': participants,
        }
        results.append(item)
        if weighted > best_score:
            best_score = weighted

    best_dates = [r for r in results if r['weighted'] == best_score] if participants > 0 else []
    responders = db.execute(
        'SELECT name, submitted_at FROM responses WHERE poll_id = ? ORDER BY submitted_at DESC, name COLLATE NOCASE',
        (poll['id'],)
    ).fetchall()
    return render_template('summary.html', poll=poll, participants=participants, best_dates=best_dates, results=results, responders=responders)


if __name__ == '__main__':
    init_db()
    app.run(debug=True)
