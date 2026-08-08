import datetime
import os
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import requests

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "antisocial_super_secret_jwt_and_session_key_2026_red")
app.config['PERMANENT_SESSION_LIFETIME'] = datetime.timedelta(days=3650)

BACKEND_URL = os.environ.get("BACKEND_INTERNAL_URL", "http://backend:8000")

def get_auth_headers():
    token = session.get("access_token")
    if token:
        return {"Authorization": f"Bearer {token}"}
    return {}

@app.before_request
def check_session_validity():
    # Public endpoints that don't require an active session check
    exempt_routes = ['login', 'register', 'confirm_email', 'reset_password_page', 'forgot_password_page', 'static', 'index', 'view_post']
    if request.endpoint in exempt_routes or request.endpoint is None:
        return

    # If session claims user is logged in, verify backend token validity if needed or if token is present
    if session.get("access_token"):
        # For protected page routes, verify user session isn't expired
        if not request.path.startswith('/api/') and not request.path.startswith('/uploads/'):
            try:
                res = requests.get(f"{BACKEND_URL}/api/users/me", headers=get_auth_headers(), timeout=3)
                if res.status_code == 401:
                    session.clear()
                    flash("Your session has expired. Please log in again.", "warning")
                    return redirect(url_for("login"))
            except Exception:
                pass

@app.context_processor
def inject_user():
    role = session.get("role", "user")
    is_admin = session.get("is_admin", False) or (role == "admin")
    is_moderator = is_admin or (role == "moderator")

    # Fetch site settings for banner/page text display & custom accent color
    site_settings = {"banner_text": "", "page_text": "", "accent_color": "#dc2626"}
    try:
        s_res = requests.get(f"{BACKEND_URL}/api/admin/settings", timeout=2)
        if s_res.status_code == 200:
            site_settings = s_res.json()
    except Exception:
        pass

    return {
        "current_user": {
            "id": session.get("user_id"),
            "username": session.get("username"),
            "avatar_url": session.get("avatar_url"),
            "role": role,
            "is_admin": is_admin,
            "is_moderator": is_moderator
        } if session.get("access_token") else None,
        "site_settings": site_settings,
        "backend_url": os.environ.get("BACKEND_PUBLIC_URL", "http://localhost:8000")
    }

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    next_url = request.args.get("next") or request.form.get("next")
    if request.method == "POST":
        username_or_email = request.form.get("username_or_email")
        password = request.form.get("password")
        remember_me = request.form.get("remember_me")
        totp_code = request.form.get("totp_code")

        try:
            payload = {
                "username_or_email": username_or_email,
                "password": password,
                "remember_me": bool(remember_me)
            }
            if totp_code and totp_code.strip():
                payload["totp_code"] = totp_code.strip()

            res = requests.post(f"{BACKEND_URL}/api/auth/login", json=payload)
            if res.status_code == 200:
                data = res.json()
                if remember_me:
                    session.permanent = True
                else:
                    session.permanent = False
                session["access_token"] = data["access_token"]
                session["user_id"] = data["user_id"]
                session["username"] = data["username"]
                session["role"] = data.get("role", "user")
                session["is_admin"] = data.get("is_admin", False) or (session["role"] == "admin")

                # Fetch user profile to cache avatar_url in session
                try:
                    p_res = requests.get(f"{BACKEND_URL}/api/users/profile/{data['username']}", headers={"Authorization": f"Bearer {data['access_token']}"})
                    if p_res.status_code == 200:
                        session["avatar_url"] = p_res.json().get("profile", {}).get("avatar_url")
                except Exception:
                    pass

                flash("Successfully logged in!", "success")
                if next_url and next_url.startswith("/"):
                    return redirect(next_url)
                return redirect(url_for("feed"))

            else:
                detail = res.json().get("detail", "Login failed")
                flash(detail, "danger")
        except Exception as e:
            flash(f"Connection error to API: {str(e)}", "danger")

    return render_template("login.html", next_url=next_url)


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username")
        email = request.form.get("email")
        password = request.form.get("password")

        try:
            res = requests.post(f"{BACKEND_URL}/api/auth/register", json={
                "username": username,
                "email": email,
                "password": password
            })
            if res.status_code == 201:
                data = res.json()
                flash(data.get("message", "User registered successfully. Please check your email to verify your account."), "success")
                return redirect(url_for("login"))
            else:
                detail = res.json().get("detail", "Registration failed")
                flash(detail, "danger")
        except Exception as e:
            flash(f"Connection error to API: {str(e)}", "danger")

    return render_template("register.html")

@app.route("/confirm-email")
def confirm_email():
    token = request.args.get("token")
    if not token:
        flash("Missing confirmation token", "danger")
        return redirect(url_for("login"))

    try:
        res = requests.get(f"{BACKEND_URL}/api/auth/confirm", params={"token": token})
        if res.status_code == 200:
            flash("Your email has been confirmed! You can now log in.", "success")
        else:
            detail = res.json().get("detail", "Email confirmation failed")
            flash(detail, "danger")
    except Exception as e:
        flash(f"Error communicating with backend: {str(e)}", "danger")

    return redirect(url_for("login"))

@app.route("/reset-password", methods=["GET", "POST"])
def reset_password_page():
    token = request.args.get("token", "").strip()
    return render_template("reset_password.html", token=token)

@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("index"))

@app.route("/feed")
def feed():
    if not session.get("access_token"):
        return redirect(url_for("login"))
    return render_template("feed.html")

@app.route("/post/<int:post_id>")
def view_post(post_id):
    return render_template("post_detail.html", post_id=post_id)

@app.route("/profile/<username>")
def profile(username):
    if not session.get("access_token"):
        return redirect(url_for("login"))
    return render_template("profile.html", username=username)

@app.route("/settings")
def settings():
    if not session.get("access_token"):
        return redirect(url_for("login"))
    profile_data = {}
    try:
        res = requests.get(
            f"{BACKEND_URL}/api/users/profile/{session.get('username')}",
            headers={"Authorization": f"Bearer {session.get('access_token')}"}
        )
        if res.status_code == 200:
            profile_data = res.json().get("profile", {})
    except Exception:
        pass
    return render_template("settings.html", profile=profile_data)


@app.route("/friends")
def friends():
    if not session.get("access_token"):
        return redirect(url_for("login"))
    return render_template("friends.html")

@app.route("/groups")
def groups():
    if not session.get("access_token"):
        return redirect(url_for("login"))
    return render_template("groups.html")

@app.route("/groups/<int:group_id>")
def group_detail(group_id):
    if "access_token" not in session:
        flash("Please log in to access community groups.", "warning")
        return redirect(url_for("login"))
    return render_template("group_detail.html", group_id=group_id)

@app.route("/messages")
def messages_page():
    if "access_token" not in session:
        flash("Please log in to access your direct messages.", "warning")
        return redirect(url_for("login"))
    return render_template("messages.html")

@app.route("/admin")
def admin():
    if not session.get("access_token") or not session.get("is_admin"):
        flash("Admin privileges required.", "danger")
        return redirect(url_for("feed"))
    return render_template("admin.html")

@app.route("/api/<path:path>", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
def api_proxy(path):
    url = f"{BACKEND_URL}/api/{path}"
    headers = {}
    
    if "Authorization" in request.headers:
        headers["Authorization"] = request.headers["Authorization"]
    elif session.get("access_token"):
        headers["Authorization"] = f"Bearer {session.get('access_token')}"

    try:
        if request.files:
            files = []
            for key, file in request.files.items():
                if file and file.filename:
                    files.append((key, (file.filename, file.read(), file.content_type or "application/octet-stream")))
            data = request.form.to_dict()
            res = requests.request(
                method=request.method,
                url=url,
                headers=headers,
                params=request.args,
                data=data,
                files=files if files else None
            )
        elif request.is_json:
            res = requests.request(
                method=request.method,
                url=url,
                headers=headers,
                params=request.args,
                json=request.get_json(silent=True)
            )
        else:
            res = requests.request(
                method=request.method,
                url=url,
                headers=headers,
                params=request.args,
                data=request.get_data()
            )

        if res.status_code == 401:
            session.clear()

        content_type = res.headers.get("content-type", "")
        if "application/json" in content_type:
            json_data = res.json()
            if path == "users/profile/avatar" and res.status_code == 200:
                session["avatar_url"] = json_data.get("avatar_url")
            return jsonify(json_data), res.status_code
        else:
            return res.content, res.status_code, {"Content-Type": content_type}

    except Exception as e:
        return jsonify({"detail": f"Backend proxy error: {str(e)}"}), 502


@app.route("/uploads/<path:filename>")
def uploads_proxy(filename):
    url = f"{BACKEND_URL}/uploads/{filename}"
    try:
        res = requests.get(url, headers=get_auth_headers())
        content_type = res.headers.get("Content-Type", "application/octet-stream")
        return res.content, res.status_code, {"Content-Type": content_type}
    except Exception as e:
        return f"Media fetch error: {str(e)}", 502

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)

