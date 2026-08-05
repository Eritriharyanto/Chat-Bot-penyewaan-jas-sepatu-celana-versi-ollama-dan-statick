"""Bangun system prompt untuk LLM dari knowledge_base.json + intents.json,
dan bangun daftar FAQ ringkas untuk landing page."""
from chatbot.config import FAQ_TAGS
from chatbot.services.formatting import rp


def summarize_stock(detail: dict) -> str:
    """Ringkas info stok (yang aslinya dirinci per warna x per ukuran, bisa
    ratusan angka buat 1 produk) jadi 1 kalimat singkat yang tetap bisa
    dijawab model. Ini WAJIB ada di system prompt — sebelumnya info stok
    sama sekali gak dikirim ke model sama sekali, jadi pertanyaan "stok
    masih berapa" gak ada dasarnya buat dijawab.

    Ditulis defensif buat 2 skenario:
    - Kalau stoknya seragam semua warna & ukuran (kondisi saat ini) -> 1 angka simpel.
    - Kalau nanti datanya diubah jadi gak seragam / ada yang habis -> kasih rentang
      dan tandain warna yang stoknya 0, biar tetap akurat bukan nebak.
    """
    all_stok = []
    habis = []
    for v in detail["varian_warna"]:
        stok_map = v.get("stok_per_ukuran", {})
        if not stok_map:
            continue
        all_stok.extend(stok_map.values())
        if all(s == 0 for s in stok_map.values()):
            habis.append(v["warna"])

    if not all_stok:
        return ""

    if len(set(all_stok)) == 1:
        line = f" Stok: rata-rata {all_stok[0]} pcs tiap kombinasi warna & ukuran."
    else:
        line = f" Stok: bervariasi {min(all_stok)}-{max(all_stok)} pcs tergantung warna & ukuran."

    if habis:
        line += f" Sedang habis: {', '.join(habis)}."

    return line


def summarize_kb(kb: dict) -> str:
    info = kb["informasi_toko"]
    produk = kb["produk"]
    paket = kb["paket_sewa"]

    lines = []
    lines.append(f"Nama usaha: {info['nama_usaha']}")
    lines.append(f"Deskripsi: {info['deskripsi']}")
    lines.append(f"Jam operasional: {info['jam_operasional']}")
    lines.append(f"Kontak admin: {info['kontak']}")
    lines.append(f"Alamat: {info['alamat']}")
    lines.append(f"Metode pembayaran: {', '.join(info['metode_pembayaran'])}")
    lines.append(f"Syarat sewa: {'; '.join(info['syarat_sewa'])}")

    denda = info["kebijakan_denda"]
    lines.append(
        f"Denda keterlambatan: {rp(denda['denda_per_hari'])}/hari, toleransi {denda['toleransi_jam']} jam. "
        f"Barang rusak: {denda['denda_barang_rusak']}. Barang hilang: {denda['denda_barang_hilang']}."
    )

    durasi = info["durasi_sewa"]
    lines.append(
        f"Durasi sewa: minimal {durasi['minimal_hari']} hari, maksimal {durasi['maksimal_hari']} hari. "
        f"{durasi['keterangan']}"
    )

    batal = info["kebijakan_pembatalan"]
    lines.append(
        f"Pembatalan/reschedule: DP dikembalikan={'ya' if batal['dp_dikembalikan'] else 'tidak'}, "
        f"boleh reschedule={'ya' if batal['boleh_reschedule'] else 'tidak'}. {batal['keterangan']}"
    )

    antar = info["layanan_antar"]
    lines.append(
        f"Layanan antar: {'tersedia' if antar['tersedia'] else 'tidak tersedia'}, area {antar['area']}, "
        f"biaya {antar['biaya']}. {antar['keterangan']}"
    )

    promo = info["promo"]
    lines.append(f"Promo: {'sedang aktif' if promo['aktif'] else 'belum ada promo aktif'}. {promo['keterangan']}")

    lines.append("\nDaftar produk:")
    for nama, detail in produk.items():
        varian_names = [v["warna"] for v in detail["varian_warna"]]
        motif_list = [v[len("Motif "):] for v in varian_names if v.startswith("Motif ")]
        warna_polos = [v for v in varian_names if not v.startswith("Motif ")]
        harga = detail["varian_warna"][0]["harga_sewa_per_hari"]
        ukuran = ", ".join(str(u) for u in detail["ukuran_tersedia"])
        detail_line = f"- {nama.capitalize()}: {detail['deskripsi']}. Harga {rp(harga)}/hari. Ukuran: {ukuran}."
        if warna_polos:
            detail_line += f" Warna polos: {', '.join(warna_polos)}."
        if motif_list:
            detail_line += f" Motif/corak tersedia: {', '.join(motif_list)}."
        detail_line += summarize_stock(detail)
        lines.append(detail_line)

    if "size_chart" in produk.get("jas", {}):
        lines.append("\nSize chart jas (ukuran: lingkar dada cm / berat badan kg):")
        for row in produk["jas"]["size_chart"]:
            lines.append(f"- {row['ukuran']}: {row['lingkar_dada_cm']} cm / {row['berat_badan_kg']} kg")

    lines.append("\nPaket sewa:")
    for p in paket:
        catatan = f" ({p['catatan']})" if "catatan" in p else ""
        lines.append(f"- {p['nama_paket']}: {rp(p['harga_sewa_per_hari'])}/hari{catatan}")

    return "\n".join(lines)


def _truncate_for_style(text: str, max_chars: int) -> str:
    """Potong teks contoh jawaban di batas kata terdekat, bukan di tengah kata."""
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars].rsplit(" ", 1)[0]
    return cut + "..."


def style_examples(intents: list) -> str:
    """Ambil 1 contoh Q&A per intent dari intents.json sebagai referensi gaya bahasa.

    Contoh dari intent "tidak_dikenali" SENGAJA disertakan (bukan di-skip) supaya
    model juga punya referensi gaya bahasa untuk menolak/mengarahkan pertanyaan
    yang di luar topik toko, bukan cuma referensi buat jawab pertanyaan produk.

    PENTING soal panjang: jawaban_default di intents.json itu ditulis panjang &
    lengkap (kadang 3-4 kalimat) karena aslinya didesain buat dipakai LANGSUNG
    sebagai balasan jadi, bukan cuma buat referensi gaya. Tapi di sini fungsinya
    beda — cuma dipakai model buat "nyontek" nada bicara (santai, ramah, gak
    formal), isi lengkapnya gak perlu, karena isi jawaban yang sebenarnya nanti
    disusun sendiri sama model dari DATA TOKO.

    Kalau semua 27 contoh dikirim penuh, itu ~3400 token sendiri (~70% dari
    total system prompt) — buat model 1.5b di laptop pas-pasan, itu bikin
    prefill lambat banget dan bisa kena timeout. Makanya tiap contoh dipotong
    ke ±100 karakter pertama, cukup buat nangkep nada bicaranya doang.
    """
    lines = []
    for intent in intents:
        contoh = intent["contoh_pertanyaan"][0]
        jawab = _truncate_for_style(intent["jawaban_default"], 100)
        lines.append(f"Q: {contoh}\nA: {jawab}")
    return "\n\n".join(lines)


def build_system_prompt(kb: dict, intents: list) -> str:
    kb_summary = summarize_kb(kb)
    examples = style_examples(intents)
    return f"""Kamu adalah asisten chatbot untuk usaha "{kb['informasi_toko']['nama_usaha']}", jasa sewa jas & formal wear.

ATURAN:
- Jawab HANYA berdasarkan DATA TOKO di bawah ini. Jangan mengarang info yang tidak ada di data.
- Kamu HANYA boleh membahas hal seputar sewa jas/celana/sepatu/dasi/vest di toko ini (produk, ukuran, warna, harga, cara sewa, syarat, pembayaran, denda, reschedule, pembatalan, layanan antar, promo, jam & lokasi toko).
- Kalau pertanyaan di luar topik itu (obrolan umum, minta pendapat pribadi, coding, resep masakan, berita, curhat, dsb), atau infonya tidak ada di data toko, JANGAN mencoba menjawab pakai pengetahuan umum kamu. Tolak dengan sopan, singkat, dan arahkan balik ke topik toko atau ke kontak admin — contoh gayanya ada di contoh Q&A intent "tidak_dikenali" di bawah.
- Jangan berpura-pura tahu jawabannya kalau memang tidak ada di data toko.
- FOKUS jawab PERSIS apa yang ditanya user. Jangan tiba-tiba nyerocos info produk lain yang gak ditanya (mis. kalau user nanya soal denda, jawab soal denda aja, jangan malah cerita soal warna sepatu atau ukuran jas).
- Kalau user MENGOREKSI atau MENGKLARIFIKASI pertanyaan sebelumnya (mis. "bukan itu maksudnya", "maksud saya bukan rusak tapi hilang beneran"), JANGAN mengulang jawaban sebelumnya persis sama. Baca ulang koreksinya, lalu jawab ulang sesuai maksud barunya.
- JANGAN mengulang kalimat atau poin yang sama dua kali dalam satu jawaban. Sekali cukup.
- Gaya bahasa: santai, akrab, ramah seperti admin online shop, boleh pakai emoji secukupnya (jangan berlebihan).
- Jawaban singkat dan jelas, tidak bertele-tele.
- JANGAN pakai simbol markdown yang butuh di-render (jangan pakai **tebal**, *miring*, heading pakai #), soalnya tampilan chat tidak me-render markdown jadi simbol itu bakal tampil apa adanya dan bikin berantakan.
- TAPI kalau jawabannya berisi beberapa poin/data (misal: daftar ukuran, syarat sewa, langkah-langkah, rincian harga, dll), WAJIB dipecah per baris pakai enter (baris baru), satu poin satu baris, dan boleh kasih tanda "-" di depan tiap poin sebagai bullet biasa (ini teks biasa, bukan markdown, jadi aman). Jangan digabung jadi satu paragraf panjang menerus.
- Contoh format yang benar buat jawaban ukuran:
Soal ukuran jas, stoknya lengkap kok, dari XS sampai 5XL. Kira-kira patokannya:
- XS: lingkar dada ±84-88cm, berat 40-50kg
- S: lingkar dada ±88-92cm, berat 50-60kg
- M: lingkar dada ±92-96cm, berat 60-70kg
- L: lingkar dada ±96-100cm, berat 70-80kg
- XL: lingkar dada ±100-104cm, berat 80-90kg
Kalau masih ragu ukurannya, bisa konsultasi ke admin ya.

=== DATA TOKO ===
{kb_summary}

=== CONTOH GAYA JAWAB (referensi nada bicara, jangan disalin persis) ===
{examples}
"""


def build_domain_keywords(kb: dict) -> set:
    words = set(kb["produk"].keys())
    for produk in kb["produk"].values():
        for varian in produk["varian_warna"]:
            for w in varian["warna"].lower().replace("(", " ").replace(")", " ").split():
                if len(w) > 2:
                    words.add(w)
    for p in kb["paket_sewa"]:
        for w in p["nama_paket"].lower().split():
            if len(w) > 2:
                words.add(w)
    words.update([
        "sewa", "nyewa", "rental", "pesan", "booking", "dp", "bayar", "pembayaran",
        "harga", "biaya", "murah", "mahal", "budget", "ukuran", "size", "warna", "stok",
        "stock", "ready", "alamat", "lokasi", "jam", "buka", "tutup", "operasional",
        "antar", "kirim", "ambil", "denda", "telat", "terlambat", "rusak", "hilang",
        "reschedule", "jadwal", "batal", "cancel", "promo", "diskon", "syarat", "ktp",
        "sim", "jaminan", "durasi", "toko", "admin", "kontak", "wa", "whatsapp", "acara",
        "wisuda", "nikah", "nikahan", "kondangan", "lamaran", "formal", "fitting", "coba",
        "tukar", "ganti", "paket", "satuan", "lengkap", "vest", "rompi", "dasi",
        "transfer", "bank", "tunai", "cash",
    ])
    return words


def build_faq(intents: list) -> list:
    by_tag = {i["intent"]: i for i in intents}
    faq = []
    for tag in FAQ_TAGS:
        intent = by_tag.get(tag)
        if intent:
            faq.append({"q": intent["contoh_pertanyaan"][0], "a": intent["jawaban_default"]})
    return faq
