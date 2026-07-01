import os
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
from datetime import datetime, date

load_dotenv()
DATABASE_URL = os.getenv('DATABASE_URL')

class DatabaseConnection:
    def __init__(self, conn):
        self.conn = conn

    def execute(self, query, params=None):
        cur = self.conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        if params:
            cur.execute(query, params)
        else:
            cur.execute(query)
        return cur

    def close(self):
        self.conn.close()

    def commit(self):
        self.conn.commit()

def get_db():
    conn = psycopg2.connect(DATABASE_URL, sslmode='require')
    return DatabaseConnection(conn)

def init_db():
    conn = psycopg2.connect(DATABASE_URL, sslmode='require')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS members (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT,
            phone TEXT,
            plan TEXT,
            joining_date DATE,
            expiry_date DATE,
            price REAL DEFAULT 0,
            amount_paid REAL DEFAULT 0,
            balance_amount REAL DEFAULT 0,
            balance_due_date DATE,
            status TEXT DEFAULT 'active',
            bill_number TEXT,
            trainer TEXT,
            notes TEXT,
            payment_mode TEXT,
            paid_date DATE,
            online_amount REAL DEFAULT 0,
            cash_amount REAL DEFAULT 0,
            created_at TIMESTAMP DEFAULT NOW()
        )
    ''')
    for col in ['bill_number', 'trainer', 'notes', 'payment_mode', 'paid_date', 'online_amount', 'cash_amount']:
        try:
            cursor.execute(f'ALTER TABLE members ADD COLUMN IF NOT EXISTS {col} TEXT')
        except:
            pass
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS membership_history (
            id SERIAL PRIMARY KEY,
            member_id INTEGER NOT NULL,
            plan TEXT NOT NULL,
            start_date DATE NOT NULL,
            expiry_date DATE NOT NULL,
            price REAL DEFAULT 0,
            amount_paid REAL DEFAULT 0,
            balance_amount REAL DEFAULT 0,
            balance_due_date DATE,
            payment_mode TEXT,
            paid_date DATE,
            online_amount REAL DEFAULT 0,
            cash_amount REAL DEFAULT 0,
            renewed_at TIMESTAMP DEFAULT NOW(),
            FOREIGN KEY (member_id) REFERENCES members(id) ON DELETE CASCADE
        )
    ''')
    for col in ['payment_mode', 'paid_date', 'online_amount', 'cash_amount']:
        try:
            cursor.execute(f'ALTER TABLE membership_history ADD COLUMN IF NOT EXISTS {col} TEXT')
        except:
            pass
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS attendance (
            id SERIAL PRIMARY KEY,
            member_id INTEGER NOT NULL,
            date DATE NOT NULL,
            check_in_time TIME NOT NULL,
            FOREIGN KEY (member_id) REFERENCES members(id) ON DELETE CASCADE
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS payments (
            id SERIAL PRIMARY KEY,
            member_id INTEGER NOT NULL,
            amount REAL NOT NULL,
            payment_date DATE NOT NULL,
            payment_mode TEXT DEFAULT 'Cash',
            plan TEXT,
            notes TEXT,
            created_at TIMESTAMP DEFAULT NOW(),
            FOREIGN KEY (member_id) REFERENCES members(id) ON DELETE CASCADE
        )
    ''')
    try:
        cursor.execute('ALTER TABLE payments ADD COLUMN IF NOT EXISTS plan TEXT')
    except:
        pass
    cursor.execute(
        "INSERT INTO payments (member_id, amount, payment_date, payment_mode, plan) "
        "SELECT m.id, m.amount_paid, COALESCE(m.paid_date::DATE, m.joining_date::DATE, CURRENT_DATE), COALESCE(m.payment_mode, 'Cash'), m.plan "
        "FROM members m LEFT JOIN payments p ON m.id = p.member_id "
        "WHERE p.id IS NULL AND m.amount_paid > 0"
    )
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    ''')
    conn.commit()
    conn.close()
