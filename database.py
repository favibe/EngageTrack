# database.py
import sqlite3
import json
import os
from datetime import datetime

DB_PATH = os.path.join('logs', 'sessions.db')

def init_db():
    """Create database tables if they don't exist."""
    os.makedirs('logs', exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Sessions table
    c.execute('''CREATE TABLE IF NOT EXISTS sessions
                 (session_id TEXT PRIMARY KEY,
                  admin_name TEXT,
                  session_name TEXT,
                  created_at TEXT,
                  ended_at TEXT,
                  status TEXT,
                  participants_json TEXT,
                  events_json TEXT,
                  transcriptions_json TEXT)''')
    
    conn.commit()
    conn.close()

def save_session(session_id, session_data, events, transcriptions):
    """Save session data to database."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    c.execute('''INSERT OR REPLACE INTO sessions VALUES (?,?,?,?,?,?,?,?,?)''',
              (session_id,
               session_data['admin_name'],
               session_data['session_name'],
               session_data['created_at'],
               datetime.now().isoformat(),
               session_data['status'],
               json.dumps(session_data['participants']),
               json.dumps(events),
               json.dumps(transcriptions)))
    
    conn.commit()
    conn.close()

def get_session(session_id):
    """Retrieve session data from database."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    c.execute('SELECT * FROM sessions WHERE session_id=?', (session_id,))
    row = c.fetchone()
    conn.close()
    
    if not row:
        return None
    
    return {
        'session_id': row[0],
        'admin_name': row[1],
        'session_name': row[2],
        'created_at': row[3],
        'ended_at': row[4],
        'status': row[5],
        'participants': json.loads(row[6]),
        'events': json.loads(row[7]),
        'transcriptions': json.loads(row[8])
    }

def get_all_sessions():
    """Get list of all sessions."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    c.execute('''SELECT session_id, admin_name, session_name, created_at, ended_at, status 
                 FROM sessions ORDER BY created_at DESC''')
    rows = c.fetchall()
    conn.close()
    
    return [{
        'session_id': r[0],
        'admin_name': r[1],
        'session_name': r[2],
        'created_at': r[3],
        'ended_at': r[4],
        'status': r[5]
    } for r in rows]