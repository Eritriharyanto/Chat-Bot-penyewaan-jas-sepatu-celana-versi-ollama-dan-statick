"""Ganti password akun admin panel."""
from flask import flash, redirect, render_template, request, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from chatbot import state
from chatbot.routes.auth import admin_login_required


def register(app):
    @app.route("/admin/pengaturan", methods=["GET", "POST"])
    @admin_login_required
    def admin_pengaturan():
        if request.method == "POST":
            config = state.load_admin_config()
            password_lama = request.form.get("password_lama") or ""
            password_baru = request.form.get("password_baru") or ""
            password_ulang = request.form.get("password_ulang") or ""

            if not check_password_hash(config["password_hash"], password_lama):
                flash("Password lama salah.", "error")
            elif len(password_baru) < 8:
                flash("Password baru minimal 8 karakter.", "error")
            elif password_baru != password_ulang:
                flash("Konfirmasi password baru tidak cocok.", "error")
            else:
                config["password_hash"] = generate_password_hash(password_baru)
                state.save_admin_config(config)
                flash("Password berhasil diganti.", "success")
                return redirect(url_for("admin_pengaturan"))

        return render_template("admin/pengaturan.html", username=state.ADMIN_CONFIG["username"])
