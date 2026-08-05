"""CRUD intents/FAQ custom -- daftar Q&A yang keyword pemicunya bisa
ditambah langsung dari admin panel tanpa perlu edit kode."""
from flask import flash, redirect, render_template, request, url_for

from chatbot import state
from chatbot.routes.auth import admin_login_required


def register(app):
    @app.route("/admin/intents")
    @admin_login_required
    def admin_intents_list():
        q = (request.args.get("q") or "").strip().lower()
        items = state.INTENTS
        if q:
            items = [
                i for i in items
                if q in i["intent"].lower()
                or q in i["jawaban_default"].lower()
                or any(q in c.lower() for c in i["contoh_pertanyaan"])
            ]
        return render_template("admin/intents_list.html", intents=items, q=q, total=len(state.INTENTS))

    @app.route("/admin/intents/baru", methods=["GET", "POST"])
    @admin_login_required
    def admin_intents_baru():
        if request.method == "POST":
            nama = (request.form.get("intent") or "").strip().lower().replace(" ", "_")
            contoh = [c.strip() for c in (request.form.get("contoh_pertanyaan") or "").split("\n") if c.strip()]
            keywords = [k.strip() for k in (request.form.get("keywords") or "").split(",") if k.strip()]
            jawaban = (request.form.get("jawaban_default") or "").strip()

            if not nama or not contoh or not jawaban:
                flash("Nama intent, minimal 1 contoh pertanyaan, dan jawaban wajib diisi.", "error")
            elif nama in state.INTENTS_BY_TAG:
                flash(f"Intent '{nama}' sudah ada.", "error")
            else:
                intents = state.INTENTS
                intents.append({
                    "intent": nama,
                    "contoh_pertanyaan": contoh,
                    "context_set": f"custom.{nama}",
                    "jawaban_default": jawaban,
                    "keywords": keywords,
                })
                state.save_intents(intents)
                flash(f"FAQ/intent '{nama}' berhasil ditambahkan.", "success")
                return redirect(url_for("admin_intents_list"))

        return render_template("admin/intents_form.html", mode="baru", intent=None)

    @app.route("/admin/intents/<nama>/edit", methods=["GET", "POST"])
    @admin_login_required
    def admin_intents_edit(nama):
        intent = state.INTENTS_BY_TAG.get(nama)
        if not intent:
            flash("Intent tidak ditemukan.", "error")
            return redirect(url_for("admin_intents_list"))

        if request.method == "POST":
            contoh = [c.strip() for c in (request.form.get("contoh_pertanyaan") or "").split("\n") if c.strip()]
            keywords = [k.strip() for k in (request.form.get("keywords") or "").split(",") if k.strip()]
            jawaban = (request.form.get("jawaban_default") or "").strip()

            if not contoh or not jawaban:
                flash("Minimal 1 contoh pertanyaan dan jawaban wajib diisi.", "error")
            else:
                intents = state.INTENTS
                for i in intents:
                    if i["intent"] == nama:
                        i["contoh_pertanyaan"] = contoh
                        i["jawaban_default"] = jawaban
                        i["keywords"] = keywords
                        break
                state.save_intents(intents)
                flash(f"Intent '{nama}' berhasil diperbarui.", "success")
                return redirect(url_for("admin_intents_list"))

        return render_template("admin/intents_form.html", mode="edit", intent=intent)

    @app.route("/admin/intents/<nama>/hapus", methods=["POST"])
    @admin_login_required
    def admin_intents_hapus(nama):
        if nama == "tidak_dikenali":
            flash("Intent 'tidak_dikenali' adalah fallback wajib, tidak bisa dihapus.", "error")
            return redirect(url_for("admin_intents_list"))
        intents = [i for i in state.INTENTS if i["intent"] != nama]
        state.save_intents(intents)
        flash(f"Intent '{nama}' dihapus.", "success")
        return redirect(url_for("admin_intents_list"))
