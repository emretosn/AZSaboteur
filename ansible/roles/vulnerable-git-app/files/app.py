"""
AZSaboteur — Exposed .git Directory

A mundane corporate landing page.  The actual vulnerability is an exposed
.git directory served by a misconfigured nginx reverse-proxy (set up by
the Ansible role, not this app).  Players use tools like git-dumper to
reconstruct the repo history and find secrets in old commits.
"""

from flask import Flask, render_template_string

app = Flask(__name__)

BASE_STYLE = """
<style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
           background: #fff; color: #222; }
    nav { background: #0b1930; padding: 14px 32px; display: flex;
          align-items: center; gap: 28px; }
    nav .brand { color: #fff; font-weight: 700; font-size: 1.1rem;
                 text-decoration: none; }
    nav a { color: #cbd5e1; text-decoration: none; font-size: 0.9rem; }
    nav a:hover { color: #fff; }
    .hero { text-align: center; padding: 80px 20px 60px; background: #f1f5f9; }
    .hero h1 { font-size: 2.4rem; margin-bottom: 12px; }
    .hero p { color: #555; max-width: 560px; margin: 0 auto; line-height: 1.6; }
    .section { max-width: 720px; margin: 48px auto; padding: 0 20px; line-height: 1.7; }
    .section h2 { margin-bottom: 12px; }
    footer { text-align: center; padding: 32px; color: #999; font-size: 0.8rem;
             border-top: 1px solid #eee; margin-top: 60px; }
</style>
"""

NAV = """
<nav>
    <a class="brand" href="/">Initech Solutions</a>
    <a href="/">Home</a>
    <a href="/about">About</a>
    <a href="/contact">Contact</a>
</nav>
"""

INDEX_PAGE = (
    "<!DOCTYPE html><html lang='en'><head><meta charset='UTF-8'>"
    "<meta name='viewport' content='width=device-width, initial-scale=1.0'>"
    "<title>Initech Solutions</title>" + BASE_STYLE + "</head><body>"
    + NAV +
    """
    <div class="hero">
        <h1>Innovate. Transform. Deliver.</h1>
        <p>Initech Solutions helps enterprises modernise their cloud
        infrastructure with cutting-edge DevOps tooling and managed services.</p>
    </div>
    <div class="section">
        <h2>Our Services</h2>
        <ul>
            <li>Cloud migration &amp; architecture review</li>
            <li>CI/CD pipeline design</li>
            <li>24/7 managed Kubernetes clusters</li>
            <li>Security compliance audits</li>
        </ul>
    </div>
    <footer>&copy; 2025 Initech Solutions — All rights reserved.</footer>
    </body></html>
    """
)

ABOUT_PAGE = (
    "<!DOCTYPE html><html lang='en'><head><meta charset='UTF-8'>"
    "<meta name='viewport' content='width=device-width, initial-scale=1.0'>"
    "<title>About — Initech Solutions</title>" + BASE_STYLE + "</head><body>"
    + NAV +
    """
    <div class="section" style="margin-top: 48px;">
        <h2>About Us</h2>
        <p>Founded in 2018, Initech Solutions has grown from a small
        consultancy into a trusted partner for Fortune 500 companies
        across the globe.  Our team of 120+ engineers specialises in
        Azure, AWS, and hybrid-cloud architectures.</p>
        <p style="margin-top:12px;">We believe in open-source, automation-first
        practices, and continuous improvement.</p>
    </div>
    <footer>&copy; 2025 Initech Solutions — All rights reserved.</footer>
    </body></html>
    """
)

CONTACT_PAGE = (
    "<!DOCTYPE html><html lang='en'><head><meta charset='UTF-8'>"
    "<meta name='viewport' content='width=device-width, initial-scale=1.0'>"
    "<title>Contact — Initech Solutions</title>" + BASE_STYLE + "</head><body>"
    + NAV +
    """
    <div class="section" style="margin-top: 48px;">
        <h2>Contact</h2>
        <p><strong>Email:</strong> info@initech-solutions.io</p>
        <p><strong>Phone:</strong> +1 (555) 012-3456</p>
        <p><strong>Address:</strong> 742 Evergreen Terrace, Suite 400,
        Springfield, IL 62704</p>
    </div>
    <footer>&copy; 2025 Initech Solutions — All rights reserved.</footer>
    </body></html>
    """
)


@app.route("/")
def index():
    return render_template_string(INDEX_PAGE)


@app.route("/about")
def about():
    return render_template_string(ABOUT_PAGE)


@app.route("/contact")
def contact():
    return render_template_string(CONTACT_PAGE)


@app.route("/health")
def health():
    return {"status": "ok"}


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
