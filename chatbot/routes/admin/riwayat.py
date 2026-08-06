"""Rekap riwayat chat: daftar visitor (nama + nomor telepon) beserta jumlah
pesan, dan halaman detail transkrip percakapan per visitor."""
from flask import abort, render_template, request

from chatbot import db
from chatbot.routes.auth import admin_login_required


def register(app):
    @app.route("/admin/riwayat-chat")
    @admin_login_required
    def admin_riwayat_list():
        q = (request.args.get("q") or "").strip()
        visitors = db.list_visitors(q)
        return render_template(
            "admin/riwayat_list.html",
            visitors=visitors,
            q=q,
            total=db.count_visitors(),
        )

    @app.route("/admin/riwayat-chat/<int:visitor_id>")
    @admin_login_required
    def admin_riwayat_detail(visitor_id):
        visitor = db.find_visitor_by_id(visitor_id)
        if not visitor:
            abort(404)
        messages = db.get_messages_for_visitor(visitor_id)
        return render_template(
            "admin/riwayat_detail.html",
            visitor=visitor,
            messages=messages,
        )
