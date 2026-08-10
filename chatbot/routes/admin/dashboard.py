"""Halaman utama /admin -- ringkasan angka (jumlah produk, kategori,
paket, intent, pengunjung, pesan) plus aktivitas chat terbaru buat
dashboard admin panel."""
from flask import render_template

from chatbot import db, state
from chatbot.routes.auth import admin_login_required


def register(app):
    @app.route("/admin")
    @admin_login_required
    def admin_dashboard():
        jumlah_produk = sum(len(p["varian_warna"]) for p in state.KB["produk"].values())
        jumlah_kategori = len(state.KB["produk"])
        jumlah_paket = len(state.KB["paket_sewa"])
        jumlah_intent = len(state.INTENTS)
        jumlah_intent_custom = sum(1 for i in state.INTENTS if i.get("keywords"))
        jumlah_visitor = db.count_visitors()
        jumlah_pesan = db.count_messages()
        aktivitas_terbaru = db.list_visitors()[:5]
        return render_template(
            "admin/dashboard.html",
            jumlah_produk=jumlah_produk,
            jumlah_kategori=jumlah_kategori,
            jumlah_paket=jumlah_paket,
            jumlah_intent=jumlah_intent,
            jumlah_intent_custom=jumlah_intent_custom,
            jumlah_visitor=jumlah_visitor,
            jumlah_pesan=jumlah_pesan,
            aktivitas_terbaru=aktivitas_terbaru,
            shop_name=state.KB["informasi_toko"]["nama_usaha"],
        )
