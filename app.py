from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import sqlite3
from datetime import datetime, date, timedelta
import os

app = Flask(__name__, static_folder="static")
CORS(app)

DB_NAME = "budget_sip.db"


def get_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            amount REAL NOT NULL,
            category TEXT,
            note TEXT,
            payment_mode TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS sips (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scheme_name TEXT NOT NULL,
            platform TEXT,
            amount REAL NOT NULL,
            sip_day INTEGER NOT NULL,
            start_date TEXT NOT NULL,
            frequency TEXT NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 1
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS stocks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            platform TEXT,
            units REAL NOT NULL,
            buy_price REAL NOT NULL,
            total_invested REAL NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value REAL
        )
    """)

    conn.commit()
    conn.close()


def calculate_next_due_date(sip, today=None):
    if today is None:
        today = date.today()

    sip_day = sip["sip_day"]
    start_date = datetime.strptime(sip["start_date"], "%Y-%m-%d").date()

    year = today.year
    month = today.month

    try:
        candidate = date(year, month, sip_day)
    except ValueError:
        if month == 12:
            candidate = date(year, month, 31)
        else:
            next_month_first = date(year, month + 1, 1)
            candidate = next_month_first - timedelta(days=1)

    if candidate < today or candidate < start_date:
        if month == 12:
            year += 1
            month = 1
        else:
            month += 1
        try:
            candidate = date(year, month, sip_day)
        except ValueError:
            if month == 12:
                candidate = date(year, month, 31)
            else:
                next_month_first = date(year, month + 1, 1)
                candidate = next_month_first - timedelta(days=1)

    return candidate.isoformat()


@app.route("/api/expenses", methods=["POST"])
def add_expense():
    data = request.get_json()
    amount = data.get("amount")
    date_str = data.get("date") or date.today().isoformat()
    category = data.get("category", "")
    note = data.get("note", "")
    payment_mode = data.get("payment_mode", "")

    if amount is None:
        return jsonify({"error": "amount is required"}), 400

    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO expenses (date, amount, category, note, payment_mode)
        VALUES (?, ?, ?, ?, ?)
    """, (date_str, amount, category, note, payment_mode))
    conn.commit()
    expense_id = cur.lastrowid
    conn.close()

    return jsonify({"id": expense_id, "message": "expense added"}), 201


@app.route("/api/expenses", methods=["GET"])
def list_expenses():
    from_date = request.args.get("from")
    to_date = request.args.get("to")

    conn = get_db()
    cur = conn.cursor()

    if from_date and to_date:
        cur.execute("""
            SELECT * FROM expenses
            WHERE date BETWEEN ? AND ?
            ORDER BY date DESC, id DESC
        """, (from_date, to_date))
    else:
        cur.execute("""
            SELECT * FROM expenses
            ORDER BY date DESC, id DESC
            LIMIT 100
        """)

    rows = cur.fetchall()
    conn.close()

    expenses = [dict(row) for row in rows]
    return jsonify(expenses)


@app.route("/api/expenses/<int:expense_id>", methods=["PUT"])
def update_expense(expense_id):
    data = request.get_json()
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        UPDATE expenses
        SET date = ?, amount = ?, category = ?, note = ?, payment_mode = ?
        WHERE id = ?
    """, (
        data.get("date"),
        data.get("amount"),
        data.get("category", ""),
        data.get("note", ""),
        data.get("payment_mode", ""),
        expense_id
    ))
    conn.commit()
    conn.close()
    return jsonify({"message": "expense updated"})


@app.route("/api/expenses/<int:expense_id>", methods=["DELETE"])
def delete_expense(expense_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM expenses WHERE id = ?", (expense_id,))
    conn.commit()
    conn.close()
    return jsonify({"message": "expense deleted"})


@app.route("/api/sips", methods=["POST"])
def add_sip():
    data = request.get_json()
    scheme_name = data.get("scheme_name")
    amount = data.get("amount")
    sip_day = data.get("sip_day")
    start_date = data.get("start_date")
    platform = data.get("platform", "Groww")
    frequency = data.get("frequency", "monthly")

    if not scheme_name or amount is None or sip_day is None or not start_date:
        return jsonify({"error": "scheme_name, amount, sip_day, start_date are required"}), 400

    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO sips (scheme_name, platform, amount, sip_day, start_date, frequency, is_active)
        VALUES (?, ?, ?, ?, ?, ?, 1)
    """, (scheme_name, platform, amount, sip_day, start_date, frequency))
    conn.commit()
    sip_id = cur.lastrowid
    conn.close()

    return jsonify({"id": sip_id, "message": "sip added"}), 201


@app.route("/api/sips", methods=["GET"])
def list_sips():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM sips WHERE is_active = 1")
    rows = cur.fetchall()
    conn.close()

    sips = []
    for row in rows:
        sip_dict = dict(row)
        sip_dict["next_due_date"] = calculate_next_due_date(sip_dict)
        sips.append(sip_dict)

    return jsonify(sips)


@app.route("/api/sips/<int:sip_id>", methods=["PUT"])
def update_sip(sip_id):
    data = request.get_json()
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        UPDATE sips
        SET scheme_name = ?, platform = ?, amount = ?, sip_day = ?, start_date = ?, frequency = ?
        WHERE id = ?
    """, (
        data.get("scheme_name"),
        data.get("platform", "Groww"),
        data.get("amount"),
        data.get("sip_day"),
        data.get("start_date"),
        data.get("frequency", "monthly"),
        sip_id
    ))
    conn.commit()
    conn.close()
    return jsonify({"message": "sip updated"})


@app.route("/api/sips/<int:sip_id>", methods=["DELETE"])
def delete_sip(sip_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM sips WHERE id = ?", (sip_id,))
    conn.commit()
    conn.close()
    return jsonify({"message": "sip deleted"})


@app.route("/api/stocks", methods=["POST"])
def add_stock():
    data = request.get_json()
    symbol = data.get("symbol")
    platform = data.get("platform", "Groww")
    units = data.get("units")
    buy_price = data.get("buy_price")

    if not symbol or units is None or buy_price is None:
        return jsonify({"error": "symbol, units, buy_price are required"}), 400

    total_invested = float(units) * float(buy_price)

    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO stocks (symbol, platform, units, buy_price, total_invested)
        VALUES (?, ?, ?, ?, ?)
    """, (symbol.upper(), platform, units, buy_price, total_invested))
    conn.commit()
    stock_id = cur.lastrowid
    conn.close()

    return jsonify({"id": stock_id, "message": "stock added"}), 201


@app.route("/api/stocks", methods=["GET"])
def list_stocks():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM stocks")
    rows = cur.fetchall()
    conn.close()

    stocks = [dict(row) for row in rows]
    return jsonify(stocks)


@app.route("/api/stocks/<int:stock_id>", methods=["PUT"])
def update_stock(stock_id):
    data = request.get_json()
    units = data.get("units")
    buy_price = data.get("buy_price")
    total_invested = float(units) * float(buy_price)

    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        UPDATE stocks
        SET symbol = ?, platform = ?, units = ?, buy_price = ?, total_invested = ?
        WHERE id = ?
    """, (
        data.get("symbol").upper(),
        data.get("platform", "Groww"),
        units,
        buy_price,
        total_invested,
        stock_id
    ))
    conn.commit()
    conn.close()
    return jsonify({"message": "stock updated"})


@app.route("/api/stocks/<int:stock_id>", methods=["DELETE"])
def delete_stock(stock_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM stocks WHERE id = ?", (stock_id,))
    conn.commit()
    conn.close()
    return jsonify({"message": "stock deleted"})


def get_month_bounds(today=None):
    if today is None:
        today = date.today()
    month_start = today.replace(day=1)
    if month_start.month != 12:
        month_end = month_start.replace(month=month_start.month + 1, day=1) - timedelta(days=1)
    else:
        month_end = month_start.replace(month=12, day=31)
    return month_start, month_end


def get_month_expense_total(today=None):
    month_start, month_end = get_month_bounds(today)
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        SELECT COALESCE(SUM(amount), 0) as total
        FROM expenses
        WHERE date BETWEEN ? AND ?
    """, (month_start.isoformat(), month_end.isoformat()))
    row = cur.fetchone()
    conn.close()
    return row["total"] if row else 0


def get_budget_value():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT value FROM settings WHERE key = 'monthly_budget'")
    row = cur.fetchone()
    conn.close()
    return row["value"] if row else 0.0


@app.route("/api/budget", methods=["GET", "POST"])
def budget():
    if request.method == "POST":
        data = request.get_json()
        value = float(data.get("budget", 0))
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO settings (key, value) VALUES ('monthly_budget', ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """, (value,))
        conn.commit()
        conn.close()
        return jsonify({"message": "budget updated"})

    budget_value = get_budget_value()
    month_total = get_month_expense_total()
    remaining = budget_value - month_total
    return jsonify({
        "budget": budget_value,
        "month_expense_total": month_total,
        "remaining": remaining
    })


@app.route("/api/summary", methods=["GET"])
def summary():
    today = date.today()
    month_total = get_month_expense_total(today)

    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        SELECT COALESCE(SUM(total_invested), 0) as total
        FROM stocks
    """)
    row2 = cur.fetchone()
    total_stock_invested = row2["total"] if row2 else 0

    cur.execute("""
        SELECT COALESCE(SUM(amount), 0) as total
        FROM sips
        WHERE is_active = 1
    """)
    row3 = cur.fetchone()
    total_sip_invested = row3["total"] if row3 else 0
    conn.close()

    budget_value = get_budget_value()
    remaining = budget_value - month_total

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM sips WHERE is_active = 1")
    rows = cur.fetchall()
    conn.close()

    upcoming = []
    window_end = today + timedelta(days=7)
    for row in rows:
        sip_dict = dict(row)
        nd = date.fromisoformat(calculate_next_due_date(sip_dict))
        if today <= nd <= window_end:
            sip_dict["next_due_date"] = nd.isoformat()
            upcoming.append(sip_dict)

    return jsonify({
        "month_expense_total": month_total,
        "total_stock_invested": total_stock_invested,
        "total_sip_invested": total_sip_invested,
        "budget": budget_value,
        "remaining": remaining,
        "upcoming_sips_next_7_days": upcoming
    })


@app.route("/")
def index():
    return send_from_directory("static", "index.html")


if __name__ == "__main__":
    if not os.path.exists("static"):
        os.makedirs("static")
    init_db()
    app.run(debug=True)
