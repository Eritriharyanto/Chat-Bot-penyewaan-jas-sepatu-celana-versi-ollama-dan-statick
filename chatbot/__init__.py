"""
Package utama aplikasi chatbot sewa jas + admin panel.

Struktur:
    chatbot/
        config.py           konstanta & path (Ollama, file data, dsb)
        state.py            runtime state (KB, INTENTS, SYSTEM_PROMPT, ...)
        services/           logic bisnis murni (tidak menyentuh Flask request)
        routes/             endpoint Flask, dipecah per fitur

Pakai application factory (create_app) supaya gampang di-test dan gak ada
efek samping cuma dari nge-import package ini.
"""
import secrets

from flask import Flask
from werkzeug.security import generate_password_hash

from chatbot import config, db, state
from chatbot.services.formatting import rp


def create_app() -> Flask:
    app = Flask(
        __name__,
        template_folder=str(config.TEMPLATES_DIR),
        static_folder=str(config.STATIC_DIR),
    )
    app.jinja_env.filters["rupiah"] = rp

    config.DATA_DIR.mkdir(parents=True, exist_ok=True)

    if not config.ADMIN_CONFIG_PATH.exists():
        # Jaga-jaga kalau file config admin sampai hilang: bikin akun default
        # baru (admin / ubahsegera123) daripada bikin panel admin error total.
        state.save_admin_config({
            "username": "admin",
            "password_hash": generate_password_hash("ubahsegera123"),
            "secret_key": secrets.token_hex(32),
        })

    state.ADMIN_CONFIG = state.load_admin_config()
    app.secret_key = state.ADMIN_CONFIG["secret_key"]

    state.reload_runtime_state()
    db.init_db()

    @app.context_processor
    def inject_logo():
        """Bikin variabel `logo_filename` otomatis kebaca di SEMUA template
        (landing page, login, & seluruh halaman admin) tanpa perlu di-pass
        manual satu-satu di tiap render_template(). Dibaca langsung dari
        admin_config.json (bukan dari state.ADMIN_CONFIG yang cuma sekali
        dimuat pas start) supaya begitu admin ganti logo lewat halaman
        Pengaturan, logo baru langsung tampil tanpa perlu restart server."""
        return {"logo_filename": state.load_admin_config().get("logo_filename", "logo.jfif")}

    from chatbot.routes import register_routes
    register_routes(app)

    return app
