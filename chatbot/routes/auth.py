"""Login/logout admin panel + decorator @admin_login_required yang dipakai
di semua route /admin/* lainnya."""
import functools

from flask import flash, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash

from chatbot import state


def admin_login_required(view):
    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("admin_logged_in"):
            return redirect(url_for("admin_login", next=request.path))
        return view(*args, **kwargs)

    return wrapped


def register(app):
    @app.route("/admin/login", methods=["GET", "POST"])
    def admin_login():
        if request.method == "POST":
            username = (request.form.get("username") or "").strip()
            password = request.form.get("password") or ""
            config = state.load_admin_config()
            if username == config["username"] and check_password_hash(config["password_hash"], password):
                session["admin_logged_in"] = True
                session["admin_username"] = username
                next_url = request.args.get("next") or url_for("admin_dashboard")
                return redirect(next_url)
            flash("Username atau password salah.", "error")
        return render_template("admin/login.html")

    @app.route("/admin/logout")
    def admin_logout():
        session.clear()
        return redirect(url_for("admin_login"))
