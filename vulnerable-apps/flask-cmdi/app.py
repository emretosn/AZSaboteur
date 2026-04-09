"""
AZSaboteur — Command Injection

A "Network Diagnostics" tool that pings a user-supplied host.
Intentionally vulnerable: the host parameter is interpolated directly
into a shell command via os.popen().

Exploit examples:
    ; env
    ; cat /opt/azsaboteur/flag.txt
    && whoami
    | id
"""

import os

from flask import Flask, render_template_string, request

app = Flask(__name__)

DIAG_PAGE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>NetCheck — Network Diagnostics</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
               background: #f4f6f9; color: #1a1a2e; }
        .container { max-width: 740px; margin: 60px auto; padding: 0 20px; }
        h1 { font-size: 2rem; margin-bottom: 4px; }
        .subtitle { color: #555; margin-bottom: 28px; }
        form { background: #fff; padding: 24px; border-radius: 8px;
               box-shadow: 0 2px 8px rgba(0,0,0,0.08); display: flex;
               gap: 12px; align-items: flex-end; }
        .field { flex: 1; }
        label { font-weight: 600; display: block; margin-bottom: 6px; }
        input[type="text"] { width: 100%; padding: 10px 14px; font-size: 1rem;
                             border: 1px solid #ccc; border-radius: 4px; }
        button { padding: 10px 28px; font-size: 1rem; background: #00875a;
                 color: #fff; border: none; border-radius: 4px; cursor: pointer;
                 white-space: nowrap; }
        button:hover { background: #006644; }
        .output { margin-top: 24px; background: #1e1e2e; color: #a9b1d6;
                  padding: 20px; border-radius: 8px; font-family: 'Fira Code',
                  'Courier New', monospace; font-size: 0.9rem;
                  white-space: pre-wrap; word-break: break-all;
                  max-height: 500px; overflow-y: auto; }
        footer { margin-top: 40px; text-align: center; color: #999; font-size: 0.85rem; }
    </style>
</head>
<body>
    <div class="container">
        <h1>&#128225; NetCheck</h1>
        <p class="subtitle">Quick network diagnostics — enter a hostname or IP to ping.</p>
        <form action="/ping" method="post">
            <div class="field">
                <label for="host">Hostname / IP</label>
                <input type="text" id="host" name="host" placeholder="e.g. 10.0.0.1" required>
            </div>
            <button type="submit">Ping</button>
        </form>
        {% if output is not none %}
        <div class="output">{{ output }}</div>
        {% endif %}
        <footer>&copy; 2025 NetCheck — Internal IT Tools</footer>
    </div>
</body>
</html>
"""


@app.route("/")
def index():
    return render_template_string(DIAG_PAGE, output=None)


@app.route("/ping", methods=["POST"])
def ping():
    """Run ping against the user-supplied host.

    VULNERABLE: direct string interpolation into a shell command.
    """
    host = request.form.get("host", "")
    if not host:
        return render_template_string(DIAG_PAGE, output="Please provide a host.")

    # VULNERABLE — command injection via unsanitised input
    cmd = f"ping -c 2 {host}"
    stream = os.popen(cmd)
    result = stream.read()

    return render_template_string(DIAG_PAGE, output=result)


@app.route("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
