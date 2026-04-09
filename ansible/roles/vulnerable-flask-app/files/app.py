"""
AZSaboteur — SSRF to IMDS Token Theft

A "Link Preview" service that fetches any user-supplied URL server-side.
Intentionally vulnerable: no URL validation allows SSRF to the Azure
Instance Metadata Service (IMDS) at 169.254.169.254.
"""

from flask import Flask, render_template_string, request

import requests as http_requests

app = Flask(__name__)

INDEX_PAGE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>LinkPeek — Instant Link Previews</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
               background: #f0f2f5; color: #1a1a2e; }
        .container { max-width: 720px; margin: 60px auto; padding: 0 20px; }
        h1 { font-size: 2rem; margin-bottom: 8px; }
        .subtitle { color: #555; margin-bottom: 32px; }
        form { background: #fff; padding: 24px; border-radius: 8px;
               box-shadow: 0 2px 8px rgba(0,0,0,0.08); }
        label { font-weight: 600; display: block; margin-bottom: 8px; }
        input[type="text"] { width: 100%; padding: 10px 14px; font-size: 1rem;
                             border: 1px solid #ccc; border-radius: 4px; }
        button { margin-top: 14px; padding: 10px 28px; font-size: 1rem;
                 background: #0066ff; color: #fff; border: none; border-radius: 4px;
                 cursor: pointer; }
        button:hover { background: #0052cc; }
        .result { margin-top: 24px; background: #fff; padding: 20px;
                  border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.08);
                  white-space: pre-wrap; word-break: break-all;
                  max-height: 500px; overflow-y: auto; font-family: monospace;
                  font-size: 0.9rem; }
        .error { color: #cc0000; }
        footer { margin-top: 40px; text-align: center; color: #999; font-size: 0.85rem; }
    </style>
</head>
<body>
    <div class="container">
        <h1>&#128279; LinkPeek</h1>
        <p class="subtitle">Paste any URL and we'll fetch a preview for you.</p>
        <form action="/fetch" method="get">
            <label for="url">URL to preview</label>
            <input type="text" id="url" name="url" placeholder="https://example.com" required>
            <button type="submit">Fetch Preview</button>
        </form>
        {% if result is not none %}
        <div class="result">{{ result }}</div>
        {% endif %}
        {% if error %}
        <div class="result error">{{ error }}</div>
        {% endif %}
        <footer>&copy; 2025 LinkPeek Inc. &mdash; All rights reserved.</footer>
    </div>
</body>
</html>
"""


@app.route("/")
def index():
    return render_template_string(INDEX_PAGE, result=None, error=None)


@app.route("/fetch")
def fetch_url():
    """Fetch the user-supplied URL and return its body.

    VULNERABLE: No validation on the target URL — an attacker can reach
    internal services such as the Azure IMDS (169.254.169.254).
    The Metadata header is forwarded so IMDS requests succeed.
    """
    url = request.args.get("url", "")
    if not url:
        return render_template_string(INDEX_PAGE, result=None,
                                      error="Please provide a URL.")

    try:
        # Always include the Azure IMDS required header.
        # On a real host this is harmless for normal URLs but makes
        # IMDS exploitation possible in a single request.
        resp = http_requests.get(
            url,
            headers={"Metadata": "true"},
            timeout=5,
        )
        return render_template_string(INDEX_PAGE, result=resp.text, error=None)
    except Exception as exc:
        return render_template_string(INDEX_PAGE, result=None,
                                      error=f"Error fetching URL: {exc}")


@app.route("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
