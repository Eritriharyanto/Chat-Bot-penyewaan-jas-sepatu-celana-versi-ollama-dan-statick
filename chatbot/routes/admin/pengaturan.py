"""Ganti password akun admin panel & logo toko."""
import time

from flask import flash, redirect, render_template, request, url_for
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

from chatbot import config as app_config
from chatbot import state
from chatbot.routes.auth import admin_login_required

# Ekstensi gambar yang boleh dipakai sebagai logo.
LOGO_ALLOWED_EXT = {"png", "jpg", "jpeg", "jfif", "webp", "gif"}


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

    @app.route("/admin/pengaturan/logo", methods=["POST"])
    @admin_login_required
    def admin_pengaturan_logo():
        file = request.files.get("logo")
        if not file or not file.filename:
            flash("Pilih file logo dulu.", "error")
            return redirect(url_for("admin_pengaturan"))

        ext = file.filename.rsplit(".", 1)[-1].lower() if "." in file.filename else ""
        if ext not in LOGO_ALLOWED_EXT:
            flash("Format file tidak didukung. Gunakan PNG, JPG, JPEG, atau WEBP.", "error")
            return redirect(url_for("admin_pengaturan"))

        # Nama file dibikin unik pakai timestamp, biar browser gak nampilin
        # logo lama dari cache begitu logo diganti (nama file sama = cache lama kepake).
        filename = secure_filename(f"logo_{int(time.time())}.{ext}")
        dest_dir = app_config.STATIC_DIR / "assets"
        dest_dir.mkdir(parents=True, exist_ok=True)
        file.save(dest_dir / filename)

        config = state.load_admin_config()
        old_filename = config.get("logo_filename")
        config["logo_filename"] = filename
        state.save_admin_config(config)

        # Hapus file logo lama supaya folder assets gak numpuk file tiap
        # kali logo diganti (logo default bawaan "logo.jfif" gak dihapus).
        if old_filename and old_filename != "logo.jfif":
            old_path = dest_dir / old_filename
            if old_path.exists():
                old_path.unlink()

        flash("Logo berhasil diganti.", "success")
        return redirect(url_for("admin_pengaturan"))
