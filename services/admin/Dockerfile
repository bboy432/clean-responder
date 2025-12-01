import os
import sqlite3
from flask import Flask, jsonify, request, render_template

app = Flask(__name__)
DB_PATH = '/data/settings.db'

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS settings (branch TEXT PRIMARY KEY, twilio_sid TEXT, twilio_token TEXT, twilio_number TEXT, default_tech_phone TEXT)")
        # Create default entries for your 3 branches
        for branch in ['tuc', 'poc', 'rex']:
            conn.execute("INSERT OR IGNORE INTO settings (branch) VALUES (?)", (branch,))

# Initialize DB on startup
if not os.path.exists('/data'):
    os.makedirs('/data', exist_ok=True)
init_db()

@app.route('/')
def dashboard():
    """Renders the HTML dashboard."""
    return render_template('dashboard.html')

@app.route('/api/settings/<branch>', methods=['GET'])
def get_settings(branch):
    """API used by the Branch containers."""
    with get_db() as conn:
        row = conn.execute("SELECT * FROM settings WHERE branch=?", (branch,)).fetchone()
        if row:
            return jsonify(dict(row))
        return jsonify({}), 404

@app.route('/api/settings/<branch>', methods=['POST'])
def update_settings(branch):
    """API to update settings from the UI."""
    data = request.json
    with get_db() as conn:
        conn.execute("""
            UPDATE settings SET twilio_sid=?, twilio_token=?, twilio_number=?, default_tech_phone=? 
            WHERE branch=?
        """, (data.get('sid'), data.get('token'), data.get('number'), data.get('tech'), branch))
    return jsonify({"status": "updated"})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
