"""CRUD paket sewa kombinasi (mis. "Paket Lengkap: Jas + Celana + Sepatu")."""
from flask import flash, redirect, render_template, request, url_for

from chatbot import state
from chatbot.routes.auth import admin_login_required


def register(app):
    @app.route("/admin/paket", methods=["GET", "POST"])
    @admin_login_required
    def admin_paket():
        if request.method == "POST":
            kb = state.KB
            action = request.form.get("action")

            if action == "tambah":
                nama = (request.form.get("nama_paket") or "").strip()
                harga = request.form.get("harga_sewa_per_hari") or "0"
                catatan = (request.form.get("catatan") or "").strip()
                if not nama:
                    flash("Nama paket wajib diisi.", "error")
                else:
                    paket_baru = {"nama_paket": nama, "harga_sewa_per_hari": int(float(harga))}
                    if catatan:
                        paket_baru["catatan"] = catatan
                    kb["paket_sewa"].append(paket_baru)
                    state.save_kb(kb)
                    flash(f"Paket '{nama}' berhasil ditambahkan.", "success")

            elif action == "simpan":
                idx = int(request.form.get("idx"))
                if 0 <= idx < len(kb["paket_sewa"]):
                    kb["paket_sewa"][idx]["nama_paket"] = (request.form.get("nama_paket") or "").strip()
                    kb["paket_sewa"][idx]["harga_sewa_per_hari"] = int(float(request.form.get("harga_sewa_per_hari") or "0"))
                    catatan = (request.form.get("catatan") or "").strip()
                    if catatan:
                        kb["paket_sewa"][idx]["catatan"] = catatan
                    elif "catatan" in kb["paket_sewa"][idx]:
                        del kb["paket_sewa"][idx]["catatan"]
                    state.save_kb(kb)
                    flash("Paket berhasil diperbarui.", "success")

            elif action == "hapus":
                idx = int(request.form.get("idx"))
                if 0 <= idx < len(kb["paket_sewa"]):
                    nama = kb["paket_sewa"][idx]["nama_paket"]
                    del kb["paket_sewa"][idx]
                    state.save_kb(kb)
                    flash(f"Paket '{nama}' dihapus.", "success")

            return redirect(url_for("admin_paket"))

        return render_template("admin/paket.html", paket=state.KB["paket_sewa"])
