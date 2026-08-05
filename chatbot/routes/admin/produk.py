"""CRUD kategori produk beserta varian warna, harga, dan stok per ukuran."""
from flask import flash, redirect, render_template, request, url_for

from chatbot import state
from chatbot.config import UKURAN_STANDAR, WARNA_HEX
from chatbot.routes.auth import admin_login_required
from chatbot.services.product_lookup import PRODUCT_LABELS


def register(app):
    @app.route("/admin/produk")
    @admin_login_required
    def admin_produk_list():
        return render_template(
            "admin/produk_list.html",
            produk=state.KB["produk"],
            label=PRODUCT_LABELS,
        )

    @app.route("/admin/produk/baru", methods=["GET", "POST"])
    @admin_login_required
    def admin_produk_baru():
        if request.method == "POST":
            kode = (request.form.get("kode") or "").strip().lower().replace(" ", "_")
            deskripsi = (request.form.get("deskripsi") or "").strip()
            if not kode:
                flash("Kode kategori produk wajib diisi.", "error")
            elif kode in state.KB["produk"]:
                flash(f"Kategori '{kode}' sudah ada.", "error")
            else:
                kb = state.KB
                kb["produk"][kode] = {
                    "deskripsi": deskripsi,
                    "ukuran_tersedia": list(UKURAN_STANDAR),
                    "varian_warna": [],
                }
                state.save_kb(kb)
                flash(f"Kategori produk '{kode}' berhasil dibuat. Sekarang tambahkan varian warnanya.", "success")
                return redirect(url_for("admin_produk_edit", kategori=kode))
        return render_template("admin/produk_baru.html")

    @app.route("/admin/produk/<kategori>", methods=["GET", "POST"])
    @admin_login_required
    def admin_produk_edit(kategori):
        if kategori not in state.KB["produk"]:
            flash("Kategori produk tidak ditemukan.", "error")
            return redirect(url_for("admin_produk_list"))

        if request.method == "POST":
            kb = state.KB
            produk = kb["produk"][kategori]
            action = request.form.get("action")

            if action == "simpan_deskripsi":
                produk["deskripsi"] = (request.form.get("deskripsi") or "").strip()
                state.save_kb(kb)
                flash("Deskripsi kategori berhasil disimpan.", "success")

            elif action == "tambah_varian":
                warna = (request.form.get("warna_baru") or "").strip()
                harga = request.form.get("harga_baru") or "0"
                if not warna:
                    flash("Nama warna wajib diisi.", "error")
                elif any(v["warna"].lower() == warna.lower() for v in produk["varian_warna"]):
                    flash(f"Varian warna '{warna}' sudah ada.", "error")
                else:
                    ukuran = produk.get("ukuran_tersedia") or list(UKURAN_STANDAR)
                    produk["varian_warna"].append({
                        "warna": warna,
                        "ukuran_tersedia": list(ukuran),
                        "harga_sewa_per_hari": int(float(harga)),
                        "stok_per_ukuran": {u: 0 for u in ukuran},
                    })
                    state.save_kb(kb)
                    flash(f"Varian warna '{warna}' berhasil ditambahkan.", "success")

            elif action == "hapus_varian":
                warna = request.form.get("warna")
                produk["varian_warna"] = [v for v in produk["varian_warna"] if v["warna"] != warna]
                state.save_kb(kb)
                flash(f"Varian warna '{warna}' dihapus.", "success")

            elif action == "simpan_varian":
                warna = request.form.get("warna")
                for v in produk["varian_warna"]:
                    if v["warna"] == warna:
                        harga = request.form.get("harga") or "0"
                        v["harga_sewa_per_hari"] = int(float(harga))
                        stok_baru = {}
                        for ukuran in v.get("ukuran_tersedia", []):
                            nilai = request.form.get(f"stok_{ukuran}") or "0"
                            stok_baru[ukuran] = int(float(nilai))
                        v["stok_per_ukuran"] = stok_baru
                        break
                state.save_kb(kb)
                flash(f"Stok & harga varian '{warna}' berhasil diperbarui.", "success")

            return redirect(url_for("admin_produk_edit", kategori=kategori))

        return render_template(
            "admin/produk_edit.html",
            kategori=kategori,
            produk=state.KB["produk"][kategori],
            label=PRODUCT_LABELS.get(kategori, kategori),
            warna_hex=WARNA_HEX,
        )
