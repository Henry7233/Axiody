"""Preview only the admin and client settings pages.

Run ``python app2.py`` and open http://127.0.0.1:5001.
Uses existing templates and static assets without initializing the main app or
its database. Profile and preference edits stay in browser storage; password
changes are unavailable in this preview.
"""

from pathlib import Path
import secrets

from flask import Flask, redirect, render_template, render_template_string, session, url_for


PROJECT_DIR = Path(__file__).resolve().parent
app = Flask(
    __name__,
    template_folder=str(PROJECT_DIR / "app" / "templates"),
    static_folder=str(PROJECT_DIR / "app" / "static"),
)
app.config.update(
    SECRET_KEY=secrets.token_hex(32),
    SESSION_COOKIE_NAME="axiody_settings_preview",
    TEMPLATES_AUTO_RELOAD=True,
)


@app.get("/", endpoint="auth.dashboard")
def index():
    return render_template_string("""
        <!DOCTYPE html>
        <html lang="en">
        <head>
          <meta charset="UTF-8">
          <meta name="viewport" content="width=device-width, initial-scale=1">
          <title>Settings Preview | AXIODY</title>
          <link rel="stylesheet" href="{{ url_for('static', filename='css/style.css') }}">
        </head>
        <body>
          <main class="site-content">
            <h1>Settings preview</h1>
            <p>Choose a sample account. Use Home to return here and switch roles.</p>
            <ul>
              <li><a href="{{ url_for('admin_settings') }}">Admin settings</a></li>
              <li><a href="{{ url_for('client_settings') }}">Client settings</a></li>
            </ul>
            <p>Profile and preferences are saved in this browser only.
               Password changes are unavailable in this preview.</p>
          </main>
        </body>
        </html>
    """)


def render_settings(role):
    # Separate sample identities keep each role's browser preferences isolated.
    session.update(
        user_id=f"app2-preview-{role}",
        user_name=f"Demo {role.title()}",
        user_email=f"{role}@example.com",
        role=role,
    )
    return render_template(
        f"{role}/{role}_settings.html",
        account_update_url="",
        notifications_url=url_for("auth.dashboard"),
    )


@app.get("/admin/settings")
def admin_settings():
    return render_settings("admin")


@app.get("/client/settings")
def client_settings():
    return render_settings("client")


# The shared layout resolves this endpoint even in the settings-only preview.
@app.get("/submit", endpoint="client.upload")
def preview_home():
    return redirect(url_for("auth.dashboard"))


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5001, debug=True, use_reloader=False)
