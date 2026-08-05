"""Edit informasi_toko: form ringkas untuk field yang sering diubah, plus
mode lanjutan (edit JSON mentah) untuk field yang jarang disentuh."""
import json

from flask import flash, redirect, render_template, request, url_for

from chatbot import state
from chatbot.routes.auth import admin_login_required


def register(app):
    @app.route("/admin/info-toko", methods=["GET", "POST"])
    @admin_login_required
    def admin_info_toko():
        if request.method == "POST":
            kb = state.KB
            info = kb["informasi_toko"]
            info["nama_usaha"] = (request.form.get("nama_usaha") or "").strip()
            info["deskripsi"] = (request.form.get("deskripsi") or "").strip()
            info["jam_operasional"] = (request.form.get("jam_operasional") or "").strip()
            info["kontak"] = (request.form.get("kontak") or "").strip()
            info["alamat"] = (request.form.get("alamat") or "").strip()
            metode = [m.strip() for m in (request.form.get("metode_pembayaran") or "").split(",") if m.strip()]
            if metode:
                info["metode_pembayaran"] = metode
            syarat = [s.strip() for s in (request.form.get("syarat_sewa") or "").split("\n") if s.strip()]
            if syarat:
                info["syarat_sewa"] = syarat

            info.setdefault("kebijakan_denda", {})
            info["kebijakan_denda"]["denda_per_hari"] = int(float(request.form.get("denda_per_hari") or "0"))

            info.setdefault("kebijakan_dp", {})
            info["kebijakan_dp"]["minimal_persen"] = int(float(request.form.get("dp_minimal_persen") or "0"))

            info.setdefault("promo", {})
            info["promo"]["aktif"] = request.form.get("promo_aktif") == "on"
            info["promo"]["keterangan"] = (request.form.get("promo_keterangan") or "").strip()

            state.save_kb(kb)
            flash("Info toko berhasil diperbarui.", "success")
            return redirect(url_for("admin_info_toko"))

        return render_template("admin/info_toko.html", info=state.KB["informasi_toko"])

    @app.route("/admin/info-toko/lanjutan", methods=["GET", "POST"])
    @admin_login_required
    def admin_info_toko_lanjutan():
        """Mode lanjutan: edit informasi_toko sebagai JSON mentah langsung.
        Buat field yang jarang berubah & tidak ada form khususnya (kebijakan
        pembatalan, layanan antar, dsb) supaya tetap bisa diedit tanpa perlu
        sentuh kode Python."""
        if request.method == "POST":
            raw = request.form.get("raw_json") or "{}"
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError as e:
                flash(f"JSON tidak valid: {e}", "error")
                return render_template("admin/info_toko_lanjutan.html", raw_json=raw)

            kb = state.KB
            kb["informasi_toko"] = parsed
            state.save_kb(kb)
            flash("Info toko (mode lanjutan) berhasil disimpan.", "success")
            return redirect(url_for("admin_info_toko"))

        raw_json = json.dumps(state.KB["informasi_toko"], ensure_ascii=False, indent=2)
        return render_template("admin/info_toko_lanjutan.html", raw_json=raw_json)
