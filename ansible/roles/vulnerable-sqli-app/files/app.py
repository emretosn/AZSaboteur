"""
AZSaboteur — SQL Injection Credential Dump

A login form backed by SQLite.  The query is built with Python string
formatting — intentionally vulnerable to classic SQL injection.

Exploit examples:
    Username: ' OR 1=1 --
    Password: anything

    Username: ' UNION SELECT 1,key_name,key_value,'x' FROM secrets --
    Password: anything
"""

import os
import sqlite3

from flask import Flask, render_template_string, request

app = Flask(__name__)

DB_PATH = os.environ.get("DB_PATH", "/opt/azsaboteur/app.db")

LOGIN_PAGE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>CorpPortal — Employee Login</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
               background: #eef1f5; display: flex; flex-direction: column;
               justify-content: center; align-items: center; min-height: 100vh;
               padding: 40px 16px; }
        .card { background: #fff; padding: 40px 36px; border-radius: 10px;
                box-shadow: 0 4px 20px rgba(0,0,0,0.08); width: 380px; }
        h1 { font-size: 1.4rem; text-align: center; margin-bottom: 24px; }
        label { font-weight: 600; display: block; margin-bottom: 6px; font-size: 0.9rem; }
        input[type="text"], input[type="password"] {
            width: 100%; padding: 10px 12px; font-size: 1rem;
            border: 1px solid #ccc; border-radius: 4px; margin-bottom: 16px; }
        button { width: 100%; padding: 12px; font-size: 1rem; background: #0066ff;
                 color: #fff; border: none; border-radius: 4px; cursor: pointer; }
        button:hover { background: #0052cc; }
        .msg { margin-top: 16px; padding: 10px 14px; border-radius: 4px;
               font-size: 0.9rem; }
        .msg-ok  { background: #d4edda; color: #155724; }
        .msg-err { background: #f8d7da; color: #721c24; }
        .results { margin-top: 24px; width: auto; max-width: 90vw; }
        .results table { border-collapse: collapse; font-size: 0.85rem; }
        .results th, .results td { padding: 8px 12px; border: 1px solid #ddd;
                                   text-align: left; white-space: nowrap; }
        .results th { background: #f5f5f5; }
        footer { margin-top: 20px; text-align: center; color: #aaa; font-size: 0.75rem; }
    </style>
</head>
<body>
    <div class="card">
        <h1>Contoso Portal Login</h1>
        <form action="/login" method="post">
            <label for="username">Username</label>
            <input type="text" id="username" name="username" required>
            <label for="password">Password</label>
            <input type="password" id="password" name="password" required>
            <button type="submit">Sign In</button>
        </form>
        {% if message %}
            <div class="msg {{ msg_class }}">{{ message }}</div>
        {% endif %}
        <footer>&copy; 2025 CorpPortal — Internal Use Only</footer>
    </div>
    {% if rows %}
    <div class="results">
        <table>
            <tr>{% for col in columns %}<th>{{ col }}</th>{% endfor %}</tr>
            {% for row in rows %}
            <tr>{% for cell in row %}<td>{{ cell }}</td>{% endfor %}</tr>
            {% endfor %}
        </table>
    </div>
    {% endif %}
</body>
</html>
"""


def query_db(username, password):
    """Execute a deliberately unsafe SQL query."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # VULNERABLE: string formatting instead of parameterised query
    sql = (
        f"SELECT * FROM users WHERE username='{username}' "
        f"AND password='{password}'"
    )

    try:
        cur.execute(sql)
        rows = cur.fetchall()
        columns = [desc[0] for desc in cur.description] if cur.description else []
    except Exception as exc:
        conn.close()
        raise exc

    conn.close()
    return columns, rows


@app.route("/")
def index():
    return render_template_string(LOGIN_PAGE, message=None, msg_class="",
                                  rows=None, columns=None)


@app.route("/login", methods=["POST"])
def login():
    username = request.form.get("username", "")
    password = request.form.get("password", "")

    try:
        columns, rows = query_db(username, password)
    except Exception as exc:
        return render_template_string(
            LOGIN_PAGE,
            message=f"Database error: {exc}",
            msg_class="msg-err",
            rows=None,
            columns=None,
        )

    if rows:
        return render_template_string(
            LOGIN_PAGE,
            message="Login successful — welcome back!",
            msg_class="msg-ok",
            rows=rows,
            columns=columns,
        )

    return render_template_string(
        LOGIN_PAGE,
        message="Invalid credentials. Please try again.",
        msg_class="msg-err",
        rows=None,
        columns=None,
    )


@app.route("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
