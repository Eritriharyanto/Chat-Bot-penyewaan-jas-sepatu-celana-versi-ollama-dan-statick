"""Route publik (bukan admin): landing page toko, gerbang identitas visitor
(nama + nomor telepon), dan endpoint API chat yang dipanggil widget
chatbot di frontend."""
from flask import Response, jsonify, render_template, request, session, stream_with_context, url_for

from chatbot import config, db, state
from chatbot.services.formatting import build_maps_link, build_wa_link
from chatbot.services.intent_matching import (
    detect_chat_action,
    is_off_topic,
    match_custom_intent,
    match_sensitive_intent,
    match_static_intent,
    match_static_intent_tag,
    try_greeting_answer,
)
from chatbot.services.ollama_client import stream_ollama_response
from chatbot.services.product_lookup import (
    try_combo_price_answer,
    try_event_color_suggestion,
    try_general_stok_or_harga_answer,
    try_product_attribute_answer,
    try_stock_lookup_answer,
)
from chatbot.services.size_matching import mentions_ukuran, try_size_answer, validate_size_mentions
from chatbot.services.visitors import VisitorValidationError, register_visitor


def _stream_text(text: str, visitor_id: int, headers: dict | None = None, chat_action: str = "") -> Response:
    """Bungkus 1 string jawaban statis jadi Response streaming, format yang
    sama seperti balasan LLM (biar frontend gak perlu bedain sumbernya).
    Sekalian dicatat ke riwayat chat visitor yang bersangkutan."""
    db.log_message(visitor_id, "assistant", text, chat_action)

    def generate():
        yield text

    return Response(stream_with_context(generate()), mimetype="text/plain", headers=headers)


def register(app):
    @app.route("/")
    def index():
        info = state.KB["informasi_toko"]
        return render_template(
            "index.html",
            default_model=config.DEFAULT_MODEL,
            shop_name=info["nama_usaha"],
            info=info,
            produk=state.KB["produk"],
            paket=state.KB["paket_sewa"],
            warna_hex=config.WARNA_HEX,
            faq=state.FAQ,
            wa_link=build_wa_link(info["kontak"], f"Halo {info['nama_usaha']}, saya mau konfirmasi pembayaran."),
            maps_link=build_maps_link(info["alamat"]),
            qris_img=url_for("static", filename="assets/qris.jpeg"),
        )

    @app.route("/api/visitor", methods=["POST"])
    def api_visitor_register():
        """Dipanggil dari gerbang identitas sebelum chat dibuka: user wajib
        isi nama & nomor telepon dulu. Kalau nomornya sudah pernah chat
        sebelumnya, riwayatnya otomatis nyambung (lihat db.upsert_visitor)."""
        data = request.get_json(force=True) or {}
        try:
            visitor = register_visitor(data.get("nama", ""), data.get("nomor_telepon", ""))
        except VisitorValidationError as e:
            return jsonify({"error": e.message}), 400

        session["visitor_id"] = visitor["id"]
        session["visitor_nama"] = visitor["nama"]
        return jsonify({"ok": True, "nama": visitor["nama"], "nomor_telepon": visitor["nomor_telepon"]})

    @app.route("/api/visitor/me")
    def api_visitor_me():
        """Dicek widget chat tiap kali halaman dibuka: kalau browser ini
        (lewat cookie session) sudah pernah isi identitas sebelumnya, gerbang
        gak perlu ditampilkan lagi."""
        visitor_id = session.get("visitor_id")
        if not visitor_id:
            return jsonify({"registered": False})
        visitor = db.find_visitor_by_id(visitor_id)
        if not visitor:
            session.pop("visitor_id", None)
            return jsonify({"registered": False})
        return jsonify({"registered": True, "nama": visitor["nama"], "nomor_telepon": visitor["nomor_telepon"]})

    @app.route("/api/chat", methods=["POST"])
    def api_chat():
        visitor_id = session.get("visitor_id")
        if not visitor_id or not db.find_visitor_by_id(visitor_id):
            return jsonify({"error": "Silakan isi nama & nomor telepon dulu sebelum chat."}), 401

        data = request.get_json(force=True)
        user_message = (data.get("message") or "").strip()
        history = data.get("history") or []  # [{role, content}, ...] tanpa system prompt
        model = data.get("model") or config.DEFAULT_MODEL
        temperature = float(data.get("temperature", config.DEFAULT_TEMPERATURE))

        if not user_message:
            return jsonify({"error": "Pesan kosong."}), 400

        db.touch_visitor(visitor_id)
        db.log_message(visitor_id, "user", user_message)

        # Rantai "guard" statis di bawah ini dicek berurutan dari yang paling
        # spesifik/murah ke yang paling umum -- begitu satu guard nemu
        # jawaban pasti, langsung di-return tanpa perlu panggil LLM sama
        # sekali (lebih cepat & lebih akurat daripada nunggu LLM ngarang).
        if is_off_topic(user_message) and state.TIDAK_DIKENALI_INTENT:
            return _stream_text(state.TIDAK_DIKENALI_INTENT["jawaban_default"], visitor_id)

        greeting_reply = try_greeting_answer(user_message)
        if greeting_reply:
            return _stream_text(greeting_reply, visitor_id)

        size_reply = try_size_answer(user_message)
        if size_reply:
            return _stream_text(size_reply, visitor_id)

        sensitive_reply = match_sensitive_intent(user_message)
        if sensitive_reply:
            return _stream_text(sensitive_reply, visitor_id)

        static_reply = match_static_intent(user_message)
        if static_reply:
            matched_tag = match_static_intent_tag(user_message)
            chat_action = detect_chat_action(user_message, matched_tag)
            return _stream_text(static_reply, visitor_id, headers={"X-Chat-Action": chat_action}, chat_action=chat_action)

        custom_reply = match_custom_intent(user_message)
        if custom_reply:
            return _stream_text(custom_reply, visitor_id)

        event_color_reply = try_event_color_suggestion(user_message)
        if event_color_reply:
            return _stream_text(event_color_reply, visitor_id)

        stock_reply = try_stock_lookup_answer(user_message)
        if stock_reply:
            return _stream_text(stock_reply, visitor_id)

        combo_price_reply = try_combo_price_answer(user_message)
        if combo_price_reply:
            return _stream_text(combo_price_reply, visitor_id)

        attribute_reply = try_product_attribute_answer(user_message)
        if attribute_reply:
            return _stream_text(attribute_reply, visitor_id)

        general_reply = try_general_stok_or_harga_answer(user_message)
        if general_reply:
            return _stream_text(general_reply, visitor_id)

        # Guard terakhir sebelum ke LLM: kalau pesan SAMA SEKALI gak nyebut
        # kata kunci seputar topik toko (produk, sewa, harga, dll), tolak di
        # sini juga -- jangan diserahin ke LLM. Ini penting karena model
        # lokal kecil kadang tetap coba jawab pakai pengetahuan umum
        # (mis. "siapa itu jokowi") walau system prompt udah melarang.
        if not any(kw in user_message.lower() for kw in state.DOMAIN_KEYWORDS) and state.TIDAK_DIKENALI_INTENT:
            return _stream_text(state.TIDAK_DIKENALI_INTENT["jawaban_default"], visitor_id)

        # Gak ada guard statis yang cocok -> serahin ke LLM (Ollama).
        messages = [{"role": "system", "content": state.SYSTEM_PROMPT}] + history + [
            {"role": "user", "content": user_message}
        ]

        if mentions_ukuran(user_message):
            # Topiknya soal ukuran: tampung dulu SELURUH jawaban LLM (gak
            # di-stream mentah-mentah), baru divalidasi/dikoreksi angkanya
            # lewat validate_size_mentions() sebelum dikirim ke user.
            def generate_validated():
                full_text = "".join(stream_ollama_response(model, messages, temperature))
                corrected = validate_size_mentions(full_text)
                db.log_message(visitor_id, "assistant", corrected)
                yield corrected

            return Response(stream_with_context(generate_validated()), mimetype="text/plain")

        def generate():
            # Tampung tiap potongan token yang di-stream ke user SEKALIGUS
            # digabung jadi 1 teks utuh, biar begitu stream-nya kelar, teks
            # lengkapnya bisa langsung dicatat ke riwayat chat.
            full_text_parts = []
            for token in stream_ollama_response(model, messages, temperature):
                full_text_parts.append(token)
                yield token
            db.log_message(visitor_id, "assistant", "".join(full_text_parts))

        return Response(stream_with_context(generate()), mimetype="text/plain")
