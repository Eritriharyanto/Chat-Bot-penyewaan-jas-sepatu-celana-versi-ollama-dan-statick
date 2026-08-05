"""Semua route /admin/* (panel admin buat CS/non-IT update data chatbot
tanpa coding), dipecah per submenu: dashboard, produk, paket, info toko,
intents/FAQ, dan pengaturan akun."""
from chatbot.routes.admin import dashboard, info_toko, intents, paket, pengaturan, produk


def register(app):
    dashboard.register(app)
    produk.register(app)
    paket.register(app)
    info_toko.register(app)
    intents.register(app)
    pengaturan.register(app)
