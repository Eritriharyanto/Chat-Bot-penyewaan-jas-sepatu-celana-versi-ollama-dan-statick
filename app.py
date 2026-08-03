import json
import re
from pathlib import Path

import requests
from flask import Flask, Response, jsonify, render_template, request, stream_with_context

OLLAMA_URL = "http://localhost:11434/api/chat"
DEFAULT_MODEL = "qwen2.5:1.5b"
NUM_CTX = 8192
DEFAULT_TEMPERATURE = 0.3
DEFAULT_REPEAT_PENALTY = 1.3
DEFAULT_MAX_TOKENS = 400

DATA_DIR = Path(__file__).parent
KB_PATH = DATA_DIR / "knowledge_base.json"
INTENTS_PATH = DATA_DIR / "intents.json"


def load_data():
    with open(KB_PATH, encoding="utf-8") as f:
        kb = json.load(f)
    with open(INTENTS_PATH, encoding="utf-8") as f:
        intents = json.load(f)["intents"]
    return kb, intents


def rp(n: int) -> str:
    return f"Rp{n:,}".replace(",", ".")


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
    if denda.get("tabel_kerusakan"):
        lines.append("Rincian biaya kerusakan per kategori:")
        for row in denda["tabel_kerusakan"]:
            lines.append(f"- {row['kategori']} ({row['contoh']}): {row['biaya']}")

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
    if antar.get("tabel_biaya"):
        lines.append("Rincian biaya antar per jarak:")
        for row in antar["tabel_biaya"]:
            biaya = row["biaya"]
            biaya_txt = rp(biaya) if isinstance(biaya, int) else biaya
            lines.append(f"- {row['jarak_km']}: {biaya_txt}")

    promo = info["promo"]
    lines.append(f"Promo: {'sedang aktif' if promo['aktif'] else 'belum ada promo aktif'}. {promo['keterangan']}")

    if "media_sosial" in info:
        sosmed = ", ".join(f"{k}: {v}" for k, v in info["media_sosial"].items())
        lines.append(f"Media sosial: {sosmed}")

    if "link_lokasi_maps" in info:
        lines.append(f"Link lokasi Google Maps: {info['link_lokasi_maps']}")

    if "link_whatsapp" in info:
        lines.append(f"Link chat WhatsApp admin: {info['link_whatsapp']}")

    if "rekening_pembayaran" in info:
        rek = info["rekening_pembayaran"]
        lines.append(
            f"Rekening transfer manual: Bank {rek['bank']} a.n. {rek['atas_nama']}, "
            f"no. rekening {rek['nomor_rekening']}. E-wallet yang bisa dipakai: {', '.join(rek['e_wallet'])}."
        )
        if rek.get("qris", {}).get("tersedia"):
            lines.append(f"QRIS/barcode pembayaran tersedia. {rek['qris'].get('keterangan', '')}")

    if "minimal_booking_sebelum_acara" in info:
        mb = info["minimal_booking_sebelum_acara"]
        lines.append(f"Minimal booking sebelum acara: H-{mb['hari']}. {mb['keterangan']}")

    if "kebijakan_ukuran_tidak_pas" in info:
        kut = info["kebijakan_ukuran_tidak_pas"]
        lines.append(
            f"Kebijakan kalau ukuran gak pas: boleh tukar={'ya' if kut['boleh_tukar'] else 'tidak'}. "
            f"Syarat: {kut['syarat']}. {kut['keterangan']}"
        )

    if "cara_reservasi" in info:
        lines.append("Cara reservasi/booking:")
        for i, step in enumerate(info["cara_reservasi"], start=1):
            lines.append(f"{i}. {step}")

    if "garansi_kebersihan" in info:
        lines.append(f"Garansi kebersihan barang: {info['garansi_kebersihan']}")

    if "rekomendasi_acara" in info:
        lines.append("\nRekomendasi jas per jenis acara:")
        for r in info["rekomendasi_acara"]:
            lines.append(f"- {r['acara']}: {r['rekomendasi']}")

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


KB, INTENTS = load_data()
SYSTEM_PROMPT = build_system_prompt(KB, INTENTS)
TIDAK_DIKENALI_INTENT = next((i for i in INTENTS if i["intent"] == "tidak_dikenali"), None)

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


DOMAIN_KEYWORDS = build_domain_keywords(KB)

OFF_TOPIC_PHRASES = [
    "nyanyi", "lagu", "film", "nonton", "series", "netflix",
    "catering", "kuliner", "resep masakan", "resep makanan", "masakin",
    "lowongan", "loker", "gaji", "melamar kerja",
    "pinjem duit", "pinjam duit", "pinjemin duit", "pinjol", "hutang", "utang",
    "kenalan", "kenlan", "pacar", "jodoh", "kencan",
    "robot beneran", "kamu manusia", "orang asli", "chatbot beneran",
    "jam tidur kamu", "chat wa ku gak dibales", "chat wa ku ga dibales",
    "gaun pengantin", "jasa mua", "make up artist",
    "scam", "penipu", "penipuan",
    "cuaca", "berita hari ini", "politik", "presiden",
    "python", "coding", "kode program",
    "tugas sekolah", "pr sekolah", "kuliah dimana",
    "resep dokter",
    "qwerty", "asdfgh", "sadfgh",
    "masak", "resep masak", "resepin",
    "puisi", "pantun", "cerita dong", "dongeng",
    "sejarah indonesia", "sejarah dunia",
    "musik apa", "lagu apa", "penyanyi",
    "diet", "olahraga apa",
    "terjemahin", "translate",
    "zodiak", "ramalan", "ramal",
    "matematika", "hitungan matematika",
]


_REPEATED_CHAR_RE = re.compile(r"(.)\1{5,}")  # mis. "aaaaaaaaaa", "wkwkwkwk" (via 2-char pattern di bawah)
_REPEATED_PAIR_RE = re.compile(r"(..)\1{3,}")  # mis. "wkwkwkwk", "haha haha" -> "hahaha"


def _looks_like_gibberish(token: str) -> bool:
    """Kata >=6 huruf tanpa vokal sama sekali biasanya bukan kata Indonesia
    yang valid (mis. 'bhjasdf'), beda sama singkatan angka+satuan macam
    '100kg'/'150rb' yang sengaja dikecualikan lewat cek isalpha().

    Juga tangkep spam huruf berulang (mis. 'aaaaaaaaaa', 'wkwkwkwkwk') yang
    lolos dari cek vokal karena tetap ada huruf hidupnya."""
    if not token.isalpha():
        return False
    if len(token) >= 6 and not re.search(r"[aeiou]", token):
        return True
    if len(token) >= 6 and (_REPEATED_CHAR_RE.search(token) or _REPEATED_PAIR_RE.search(token)):
        return True
    return False


def is_off_topic(message: str) -> bool:
    lower = message.lower()
    tokens = [t.strip(".,!?-") for t in lower.split()]
    tokens = [t for t in tokens if t]

    if not tokens:
        # pesan cuma tanda baca/spam karakter (mis. "?!!!?!", "....")
        return True

    if any(_looks_like_gibberish(t) for t in tokens):
        return True

    if any(phrase in lower for phrase in OFF_TOPIC_PHRASES):
        # kecuali kalau di kalimat yang sama juga ada kata kunci domain
        # yang jelas (mis. campur nanya soal sewa juga), biar aman diserahin ke LLM
        if any(kw in lower for kw in DOMAIN_KEYWORDS):
            return False
        return True

    return False


LOCATION_HOURS_KEYWORDS = [
    "alamat", "lokasi toko", "posisi toko", "dimana toko", "toko dimana",
    "tempatnya dimana", "tempatnya apa", "gmaps", "google maps", "map nya",
    "patokan", "rute ke toko", "arah ke toko", "dari stasiun", "kesininya",
    "cara kesana", "nyampe sana", "letak toko", "posisi tokonya",
    "jam buka", "jam tutup", "jam operasional", "buka jam", "tutup jam",
    "buka dari jam", "jam berapa buka", "buka sampai jam", "operasional toko",
    "buka setiap hari", "buka weekend", "buka hari libur", "buka tanggal merah",
    "masih terima tamu", "jam kerja toko", "buka full seharian",
]


def try_location_hours_answer(message: str) -> str | None:
    """Jawaban alamat/jam operasional disusun dinamis dari knowledge_base.json
    (bukan teks statis di intents.json), supaya alamat & link Google Maps-nya
    BENERAN ikut disebutkan -- sebelumnya jawaban statisnya cuma bilang
    "aku kirimin ya" tanpa pernah beneran nyisipin alamat/link-nya."""
    lower = message.lower()
    if not any(kw in lower for kw in LOCATION_HOURS_KEYWORDS):
        return None

    info = KB["informasi_toko"]
    text = f"Jam operasional toko: {info['jam_operasional']}.\n" f"Alamat: {info['alamat']}"
    if info.get("link_lokasi_maps"):
        text += f"\nLink Google Maps: {info['link_lokasi_maps']}"
    return text


def try_damage_loss_answer(message: str) -> str | None:
    """Jawaban dinamis soal barang rusak/hilang, disusun langsung dari
    kebijakan_denda di knowledge_base.json (termasuk tabel_kerusakan kalau
    ada). Dibuat dinamis -- bukan tag intents.json -- karena intents.json
    sekarang gak punya tag khusus buat ini lagi (dulu "denda_kerusakan_kehilangan"),
    tapi datanya sendiri di KB malah makin detail (ada rincian per kategori)."""
    lower = message.lower()
    keywords = [
        "hilang", "ilang", "kehilangan", "kehilangannya",
        "rusak", "kerusakan", "sobek", "kotor parah", "kebakar", "bolong",
    ]
    if not any(kw in lower for kw in keywords):
        return None

    denda = KB["informasi_toko"]["kebijakan_denda"]
    lines = [
        f"Kalau barang rusak: {denda['denda_barang_rusak']}.",
        f"Kalau barang hilang: {denda['denda_barang_hilang']}.",
    ]
    tabel = denda.get("tabel_kerusakan")
    if tabel:
        lines.append("\nRincian biaya kerusakan per kategori:")
        for row in tabel:
            lines.append(f"- {row['kategori']} ({row['contoh']}): {row['biaya']}")
    lines.append("\nBuat nominal pastinya tetap dikonfirmasi langsung sama admin ya pas cek barangnya.")
    return "\n".join(lines)


SENSITIVE_INTENT_KEYWORDS = [
    ("reschedule_pembatalan", [
        "reschedule", "resceduel", "reschedul", "geser tanggal", "ganti tanggal",
        "pindah tanggal", "geser jadwal", "tukar tanggal", "undur tanggal",
        "batal", "cancel", "gak jadi sewa", "ga jadi sewa", "dp hangus", "dp balik",
    ]),
    ("denda_keterlambatan", [
        "telat", "terlambat", "telatt", "kena denda", "denda per hari", "denda telat",
    ]),
    ("syarat_sewa", [
        "tanpa dp", "tanpa DP", "ga pake dp", "gak pake dp", "engga dp", "enggak dp",
        "gaperlu dp", "gak perlu dp", "boleh gak dp", "wajib dp", "dp nya wajib",
        "gak bisa dp", "ga bisa dp",
    ]),
    ("tanya_durasi_sewa", [
        "seminggu", "durasi sewa", "durasinya", "sewa paling lama", "paling lama sewa",
        "lebih dari 7 hari", "lebih dr 7 hari", "lebih dari seminggu", "durasi gak biasa",
        "gak biasa durasi", "minimal sewa", "maksimal sewa", "sewa berapa hari",
    ]),
]

INTENTS_BY_TAG = {i["intent"]: i for i in INTENTS}


def match_sensitive_intent(message: str) -> str | None:
    lower = message.lower()
    for tag, keywords in SENSITIVE_INTENT_KEYWORDS:
        if any(kw.lower() in lower for kw in keywords):
            intent = INTENTS_BY_TAG.get(tag)
            if intent:
                return intent["jawaban_default"]
    return None


GREETING_WORDS = [
    "halo", "hallo", "hai", "haii", "hi", "hey", "helo", "hello",
    "pagi", "siang", "sore", "malam", "met pagi", "met siang", "met sore", "met malam",
    "selamat pagi", "selamat siang", "selamat sore", "selamat malam",
    "assalamualaikum", "permisi", "min", "kak", "woy", "woi",
]


def try_greeting_answer(message: str) -> str | None:
    lower = message.lower().strip()
    tokens = [t.strip(".,!?-") for t in lower.split()]
    tokens = [t for t in tokens if t]
    if not tokens or len(tokens) > 5:
        return None
    if all(any(g == t or t in g or g in t for g in GREETING_WORDS) for t in tokens):
        sapaan_intent = INTENTS_BY_TAG.get("sapaan")
        if sapaan_intent:
            return sapaan_intent["jawaban_default"]
    return None


_CM_RE = re.compile(r"(\d{2,3})\s*cm")
_KG_RE = re.compile(r"(\d{2,3})\s*kg")
_BERAT_TANPA_SATUAN_RE = re.compile(r"berat(?:\s*badan)?\s*(\d{2,3})")


def _parse_range(s: str) -> tuple:
    lo, hi = s.split("-")
    return int(lo), int(hi)


def _match_sizes(size_chart: list, cm: int = None, kg: int = None) -> tuple:
    cm_matches, kg_matches = [], []
    for row in size_chart:
        lo_cm, hi_cm = _parse_range(row["lingkar_dada_cm"])
        lo_kg, hi_kg = _parse_range(row["berat_badan_kg"])
        if cm is not None and lo_cm <= cm <= hi_cm:
            cm_matches.append(row["ukuran"])
        if kg is not None and lo_kg <= kg <= hi_kg:
            kg_matches.append(row["ukuran"])
    return cm_matches, kg_matches


def try_size_answer(message: str) -> str | None:
    """Kalau pesan user nyebut angka cm dan/atau kg, jawab langsung pakai
    hasil pencocokan pasti ke size_chart jas. Return None kalau gak ada
    angka cm/kg yang kedetek di pesan (biar diserahin ke LLM seperti biasa)."""
    lower = message.lower()
    cm_num = _CM_RE.search(lower)
    kg_num = _KG_RE.search(lower) or _BERAT_TANPA_SATUAN_RE.search(lower)
    if not cm_num and not kg_num:
        return None

    size_chart = KB["produk"].get("jas", {}).get("size_chart", [])
    if not size_chart:
        return None

    cm = int(cm_num.group(1)) if cm_num else None
    kg = int(kg_num.group(1)) if kg_num else None
    cm_matches, kg_matches = _match_sizes(size_chart, cm=cm, kg=kg)

    if cm is not None and kg is not None:
        both = [s for s in cm_matches if s in kg_matches]
        if both:
            ukuran_txt = " atau ".join(both)
            return (
                f"Kalau lingkar dada {cm} cm dan berat {kg} kg, ukuran yang pas buat kamu itu {ukuran_txt} ya 👍 "
                f"Kalau masih ragu, boleh banget fitting langsung di toko biar makin yakin pasnya!"
            )
        if cm_matches and kg_matches:
            return (
                f"Dari lingkar dada {cm} cm sebenarnya masuk ukuran {'/'.join(cm_matches)}, tapi dari berat {kg} kg "
                f"lebih cocok ke ukuran {'/'.join(kg_matches)}. Beda dikit ini wajar karena bentuk badan tiap orang gak "
                f"selalu sama persis sama chart -- buat jas, biasanya lebih akurat patokan ke LINGKAR DADA-nya, tapi "
                f"paling aman tetap fitting langsung di toko ya biar pas beneran 😊"
            )

    if cm is not None and cm_matches:
        return f"Lingkar dada {cm} cm itu masuk ukuran {'/'.join(cm_matches)} ya."
    if kg is not None and kg_matches:
        return f"Berat {kg} kg itu masuk ukuran {'/'.join(kg_matches)} ya."

    if cm is not None or kg is not None:
        return (
            "Hmm, angkanya di luar rentang size chart kami nih 🙏 Boleh langsung chat admin ya biar dicariin "
            "solusi ukuran custom atau alternatifnya."
        )
    return None


_UKURAN_TRIGGER_WORDS = ["ukuran", "size", "cocok pake", "pas pake", "pas nya"]


def _mentions_ukuran(message: str) -> bool:
    """Dipakai buat mutusin apakah jawaban LLM ke pesan ini perlu di-buffer
    dulu dan divalidasi (lihat _validate_size_mentions), karena topiknya
    masih soal ukuran walau gak kena guard #1 di atas (mis. user nanya
    ukuran secara konsep, gak nyebut angka cm/kg eksplisit)."""
    lower = message.lower()
    return any(kw in lower for kw in _UKURAN_TRIGGER_WORDS)


_SIZE_LABELS_SORTED = sorted(
    (row["ukuran"] for row in KB["produk"].get("jas", {}).get("size_chart", [])),
    key=len,
    reverse=True,  # cek "XXXL" sebelum "XXL" sebelum "XL", biar gak ke-cut duluan
)
_SIZE_LABEL_RE = (
    re.compile("(" + "|".join(re.escape(s) for s in _SIZE_LABELS_SORTED) + ")", re.IGNORECASE)
    if _SIZE_LABELS_SORTED
    else None
)
_SIZE_CHART_BY_LABEL = {row["ukuran"]: row for row in KB["produk"].get("jas", {}).get("size_chart", [])}
_RANGE_UNIT_RE = re.compile(r"(\d{2,3})\s*-\s*(\d{2,3})\s*(kg|cm)", re.IGNORECASE)


def _validate_size_mentions(text: str) -> str:
    """Jaring pengaman terakhir: kalau jawaban LLM nyebut label ukuran (mis.
    "L") diikuti rentang angka cm/kg dalam beberapa kata setelahnya, angka
    itu dicocokkan ke size_chart asli. Kalau meleset (LLM ngarang angka
    mirip-mirip, kayak kasus nyata "L" dibilang "60-80 kg" padahal aslinya
    "70-80 kg"), angkanya diganti otomatis pakai angka yang benar dari data.
    Ini jaring pengaman, bukan pengganti guard #1 -- guard #1 tetap jalan
    duluan buat kasus yang paling sering terjadi (user nyebut cm/kg sendiri)."""
    if not _SIZE_LABEL_RE or not _SIZE_CHART_BY_LABEL:
        return text

    corrected = text
    for label_match in _SIZE_LABEL_RE.finditer(text):
        label = label_match.group(1).upper()
        row = _SIZE_CHART_BY_LABEL.get(label)
        if not row:
            continue
        window = text[label_match.end(): label_match.end() + 60]
        range_match = _RANGE_UNIT_RE.search(window)
        if not range_match:
            continue
        stated_lo, stated_hi, unit = range_match.group(1), range_match.group(2), range_match.group(3).lower()
        actual = row["lingkar_dada_cm"] if unit == "cm" else row["berat_badan_kg"]
        actual_lo, actual_hi = _parse_range(actual)
        if (stated_lo, stated_hi) != (str(actual_lo), str(actual_hi)):
            wrong_snippet = range_match.group(0)
            right_snippet = f"{actual_lo}-{actual_hi} {unit}"
            corrected = corrected.replace(wrong_snippet, right_snippet, 1)
    return corrected



STATIC_INTENT_KEYWORDS = [
    ("konfirmasi_bisa_sewa", [
        "disini bisa sewa", "bisa sewa disini", "sini bisa sewa", "sini nyewa",
        "bisa nyewa jas", "toko ini sewa", "toko ini nyewa", "toko ini nyewain",
        "disini nyewain", "disini sewain", "toko ini sewain", "disini ada jasa sewa",
        "bener toko sewa jas", "toko rental jas", "disini nyediain sewa",
        "disini bisa sewa jas", "disini sewa jas apa aja", "toko sewa jas beneran",
        "toko ini nyediain", "ini toko sewa", "emang buka sewa jas",
        "emang sewain jas",
    ]),
    ("cara_bayar", [
        "cara bayar", "metode bayar", "metode pembayaran", "bayar pakai apa",
        "bayar pake apa", "bisa transfer", "transfer bank", "bisa qris",
        "bayar qris", "qris", "bisa cash", "bayar cash", "bukti transfer",
        "bukti pembayaran", "cara pembayaran", "e-wallet", "ewallet",
        "bayar lewat", "bayar via", "bayar pake dua metode",
    ]),
    ("layanan_antar", [
        "layanan antar", "diantar", "dianter", "delivery", "ongkir",
        "ongkos kirim", "antar jemput", "opsi anter", "minta anter",
        "sistem antar", "jangkauan layanan antar", "diantar gak", "diantar ga",
    ]),
    ("promo_diskon", [
        "promo", "diskon", "potongan harga", "paket hemat", "ada event bulan",
        "promo aktif", "diskon buat pelajar", "diskon buat mahasiswa",
    ]),
    ("cara_sewa", [
        "cara sewa", "cara nyewa", "alur sewa", "alur pemesanan", "proses sewa",
        "langkah sewa", "step sewa", "tata cara sewa", "gimana cara sewa",
        "apa yang harus disiapin", "apa yang harus disipin", "proses dari plih",
        "proses dari pilih", "modal chat doang", "modal chat doag",
    ]),
    ("ucapan_terima_kasih", [
        "makasih", "makasi", "terima kasih", "terimakasih", "trims",
        "thanks", "thank you",
    ]),
    ("kontak_admin_langsung", [
    "nomor wa", "no wa", "nomor whatsapp", "kontak admin", "kontaknya",
    "nomer hp", "nomor hp", "nomor telepon", "no telepon", "telepon admin",
    "telpon admin", "hubungi admin", "cp admin", "contact person",
    "wa admin", "hp admin", "nomer wa", "minta kontak",
    ]),
    ("tanya_dp", [
        "dp nya berapa", "dp berapa", "dp minimal", "minimal dp", "uang muka",
        "dp nya wajib berapa", "dp bisa dicicil", "berapa dp", "dp booking",
        "pelunasan kapan", "dp nya masuk hitungan",
    ]),
    ("jaminan_alternatif", [
        "jaminan selain ktp", "jaminan pake sim", "jaminan pake paspor",
        "kartu pelajar buat jaminan", "ktm buat jaminan", "jaminan barang aja",
        "identitas yang diterima", "jaminan pake kk", "gapunya ktp jaminannya",
    ]),
    ("waktu_ambil_kembali", [
        "ambil h-1", "ambil h minus", "jam ambil barang", "jam kembalikan",
        "jam pengembalian", "ambil sehari sebelum", "kembaliin barang jam",
        "waktu pengambilan", "waktu pengembalian", "ambil barangnya jam berapa",
    ]),
    ("kebersihan_barang", [
        "barangnya bersih", "udah dicuci", "sudah dicuci", "disetrika",
        "bau gak", "higienis", "kondisi barang bersih", "barang bekas orang lain",
    ]),
    ("perpanjangan_sewa", [
        "perpanjang sewa", "extend sewa", "extend durasi", "nambah hari sewa",
        "perpanjangan sewa", "perpanjang durasi",
    ]),
    ("reservasi_h_minus", [
        "booking minimal h", "booking mendadak", "reservasi mendadak",
        "booking dadakan", "booking last minute", "kapan sebaiknya booking",
        "booking paling lambat",
    ]),
    ("sewa_luar_kota", [
        "kirim ke luar kota", "luar kota bisa", "luar pulau", "sewa jarak jauh",
        "kirim pake ekspedisi", "kirim pake jne", "sewa online luar kota",
        "beda kota bisa sewa",
    ]),
    ("cabang_toko", [
        "cabang lain", "ada cabang", "toko cabang", "cabang dimana",
        "cabang terdekat", "toko pusat apa cabang", "berapa cabang",
    ]),
    ("tips_pemakaian", [
        "cara pake dasi", "cara pasang dasi", "tips biar jas", "cara pasang vest",
        "cara ngiket dasi", "tips pemakaian", "kombinasi warna dasi",
        "cara pasang saputangan", "biar gak kusut",
    ]),
    ("produk_untuk_wanita", [
        "jas buat cewek", "jas buat wanita", "sewa jas wanita", "jas nya cuma buat cowok",
        "jas nya unisex", "size chart buat cewek", "jas potongan cewek",
    ]),
    ("nota_kwitansi", [
        "minta nota", "ada kwitansi", "bukti transaksi", "invoice sewa",
        "nota pembayaran", "bukti pembayaran buat", "nota atas nama perusahaan",
    ]),
    ("cara_pengembalian_kurir", [
        "dikembaliin lewat ojol", "kembalikan pake kurir", "kirim balik pake gosend",
        "balikin barang lewat paket", "kirim balik pake grab", "pengembalian via jne",
        "titip temen buat balikin",
    ]),
    ("testimoni_ulasan", [
        "ada testimoni", "review toko", "google review", "toko ini terpercaya",
        "toko ini legit", "rating toko",
    ]),
    ("konfirmasi_pesanan", [
        "pesenan aku udah", "konfirmasi pesenan", "status pesenan", "nomor booking",
        "kode pesenan", "pesenan udah masuk", "booking udah berhasil",
    ]),
    ("tanya_media_sosial", [
        "ada instagram", "ig toko", "ada di shopee", "ada di tokopedia",
        "pesen lewat marketplace", "sosmed toko", "ada akun tiktok",
        "ada linktree", "official di marketplace", "ada facebook",
    ]),
    ("tanya_walk_in", [
        "datang langsung", "dateng langsung", "walk in", "tanpa booking",
        "gak booking dulu", "gausah booking", "tanpa reservasi",
        "tanpa janjian", "dateng mendadak ke toko",
    ]),
    ("tanya_daftar_produk", [
        "nyediain produk apa aja", "produk yang bisa disewa", "list barang yang disewain",
        "sewain apa aja selain jas", "koleksi yang tersedia", "kategori barang yang bisa disewa",
        "semua item yang bisa disewa", "produk lengkapnya apa aja",
    ]),
    ("fitting_sebelum_booking", [
        "coba dulu sebelum booking", "fitting dulu sebelum bayar", "coba dulu sebelum bayar",
        "fitting gratis", "coba beberapa size dulu", "coba baju dulu sebelum",
        "tes pas dulu sebelum",
    ]),
    ("booking_atas_nama_orang_lain", [
        "booking buat orang lain", "diwakilin ambil barang", "booking buat adik",
        "sewa buat orang lain", "diambilkan sama saudara", "titip ambil ke temen",
        "booking sekaligus buat beberapa orang",
    ]),
    ("tanya_sewa_grup_diskon", [
        "sewa rombongan ada diskon", "sewa banyak orang ada potongan", "harga khusus buat sewa rombongan",
        "sewa grup ada diskon", "booking rame-rame lebih murah", "harga grup",
        "borong buat rombongan",
    ]),
    ("tanya_ukuran_anak", [
        "size buat anak kecil", "jas buat anak sd", "sewa jas buat anak umur",
        "size anak-anak tersedia", "jas buat badan anak kecil", "jas mini buat anak",
        "flower boy",
    ]),
    ("komplain_keluhan", [
        "komplain kemana", "cara komplain", "ngadu kemana", "cs khusus buat komplain",
        "kasih masukan soal pelayanan", "laporin kalo ada yang salah", "nomor khusus buat keluhan",
    ]),
    ("tanya_bedanya_paket_dan_satuan", [
        "bedanya sewa paket sama satuan", "mending sewa paket apa satuan", "paket lebih murah gak dari satuan",
        "sewa satuan itu maksudnya", "paket sama satuan itu beda", "mending ambil paket apa satuan",
    ]),
    ("tanya_katalog_foto", [
        "liat foto produknya", "ada katalog foto", "kirimin foto", "liat contoh produk dulu",
        "gambar-gambar koleksi", "ada preview produk",
    ]),
]


QRIS_KEYWORDS = [
    "qris", "barcode", "kode qr", "scan qr", "scan barcode", "kirim qris",
    "kirim barcode", "minta barcode", "minta qris", "gambar qris",
    "foto qris", "qr nya", "qr code",
]


def try_qris_answer(message: str) -> str | None:
    """Jawaban khusus kalau user nanya QRIS/barcode secara spesifik — beda
    dari pertanyaan "cara bayar" yang umum. Jawabannya nyisipin gambar
    barcode (markdown ![]()), yang dirender jadi <img> sama chat.js
    (fungsi linkify()), plus fallback transfer manual & kontak admin kalau
    barcode-nya susah discan.
    """
    lower = message.lower()
    if not any(kw in lower for kw in QRIS_KEYWORDS):
        return None

    info = KB["informasi_toko"]
    rek = info.get("rekening_pembayaran")
    link_wa = info.get("link_whatsapp", info["kontak"])
    if not rek:
        return None

    qris_img = rek.get("qris", {}).get("gambar", "/static/assets/qris-pembayaran.png")

    return (
        "Bisa banget bayar pakai barcode ya kak 😊 Tinggal scan QR di bawah ini "
        "lewat aplikasi e-wallet (" + "/".join(rek["e_wallet"]) + ") atau m-banking:\n"
        f"![Barcode pembayaran QRIS]({qris_img})\n"
        f"Kalau QR-nya susah discan, transfer manual juga bisa ke Bank {rek['bank']} "
        f"a.n. {rek['atas_nama']}, atau chat admin dulu ya: {link_wa}"
    )


def match_static_intent(message: str) -> str | None:
    lower = message.lower()
    for tag, keywords in STATIC_INTENT_KEYWORDS:
        if any(kw in lower for kw in keywords):
            intent = INTENTS_BY_TAG.get(tag)
            if intent:
                return intent["jawaban_default"]
    return None

PRODUCT_ALIASES = {
    "jas": ["jas"],
    "celana": ["celana"],
    "sepatu": ["sepatu", "pantofel"],
    "rompi": ["vest", "rompi"],
    "dasi": ["dasi"],
    "kemeja": ["kemeja"],
}
PRODUCT_LABELS = {
    "jas": "jas", "celana": "celana", "sepatu": "sepatu",
    "rompi": "vest/rompi", "dasi": "dasi", "kemeja": "kemeja",
}


def _detect_products_mentioned(lower: str) -> list:
    return [p for p, aliases in PRODUCT_ALIASES.items() if any(a in lower for a in aliases)]


# Kata ganti warna yang suka dipakai orang tapi beda dari nama resmi di data
# (mis. "item" = slang buat "hitam"). Cuma dipakai buat NORMALISASI teks
# sebelum dicocokkan ke nama warna asli, bukan buat langsung nebak.
_WARNA_SLANG = {"item": "hitam"}
# Kata pecahan dari nama warna yang terlalu umum/ambigu buat jadi penanda
# sendirian (mis. "muda" doang bisa berarti banyak hal di luar warna),
# jadi sengaja DIKECUALIKAN dari daftar kata kunci pencocokan warna.
_WARNA_WORD_STOPLIST = {"muda", "tulang", "polos", "elektrik"}


def _find_warna_varian(product: str, lower: str):
    """Cari varian warna yang paling cocok dari teks. Return dict varian
    (elemen dari varian_warna) atau None kalau gak ketemu yang cukup pasti."""
    detail = KB["produk"].get(product, {})
    varian_list = detail.get("varian_warna", [])

    # Kalau produknya cuma punya SATU varian warna (mis. sepatu -- cuma ada
    # pantofel hitam), gak ada ambiguitas sama sekali biarpun user gak
    # nyebut warna sama sekali di pesannya, jadi langsung dipakai warna
    # satu-satunya itu tanpa perlu match keyword dulu.
    if len(varian_list) == 1:
        return varian_list[0]

    normalized = lower
    for slang, resmi in _WARNA_SLANG.items():
        normalized = normalized.replace(slang, resmi)

    for varian in varian_list:
        warna_lower = varian["warna"].lower()
        full_clean = re.sub(r"[()]", "", warna_lower).strip()
        if full_clean in normalized:
            return varian
        for word in re.split(r"[ ()]+", warna_lower):
            if len(word) > 3 and word not in _WARNA_WORD_STOPLIST and word in normalized:
                return varian
    return None

def _find_ukuran_value(product: str, original_message: str):
    """Cari nilai ukuran yang disebut di pesan, dicocokkan ke ukuran_tersedia
    produk yang bersangkutan. Return string ukuran (mis. "XL", "32",
    "One Size") kalau ketemu pasti, None kalau enggak."""
    detail = KB["produk"].get(product, {})
    ukuran_list = [str(u) for u in detail.get("ukuran_tersedia", [])]
    if not ukuran_list:
        return None
    if ukuran_list == ["One Size"]:
        return "One Size"

    if all(u.isdigit() for u in ukuran_list):
        pattern = re.compile(r"\b(" + "|".join(sorted(ukuran_list, key=len, reverse=True)) + r")\b")
        m = pattern.search(original_message)
        return m.group(1) if m else None

    # ukuran huruf (XS, S, M, L, XL, ...) -> dicocokkan case-insensitive
    # tapi tetap pakai word boundary biar "L" gak asal nabrak huruf di
    # tengah kata lain.
    pattern = re.compile(
        r"\b(" + "|".join(re.escape(s) for s in sorted(ukuran_list, key=len, reverse=True)) + r")\b",
        re.IGNORECASE,
    )
    m = pattern.search(original_message)
    return m.group(1).upper() if m else None


WARNA_INTENT_BY_PRODUCT = {
    "jas": "tanya_warna_jas",
    "celana": "tanya_warna_celana",
    "sepatu": "tanya_warna_sepatu",
    "dasi": "tanya_warna_dasi",
    "rompi": "tanya_warna_vest",
    "kemeja": "tanya_warna_kemeja",
}
UKURAN_INTENT_BY_PRODUCT = {
    "jas": "tanya_ukuran_jas",
    "celana": "tanya_ukuran_celana",
    "sepatu": "tanya_ukuran_sepatu",
    "dasi": "tanya_ukuran_dasi",
    "rompi": "tanya_ukuran_vest",
    "kemeja": "tanya_ukuran_kemeja",
}
WARNA_TRIGGER_WORDS = ["warna", "warnanya", "warnaya", "wrna", "wana", "corak", "motif"]


OCCASION_KEYWORDS = {
    "wisuda": ["wisuda", "graduation", "yudisium"],
    "nikahan": ["nikahan", "kondangan", "kondangn", "resepsi", "kawinan"],
    "lamaran": ["lamaran", "tunangan", "seserahan"],
    "interview_kerja": [
        "interview", "wawancara kerja", "wawancara", "meeting kantor",
        "presentasi kerja", "acara kantor", "kerja kantor",
    ],
}
COLOR_SUGGESTION_TRIGGER_WORDS = [
    "warna", "cocok", "cocoknya", "pilih", "milih", "saran", "rekomendasi",
    "rekomen", "recommend", "bagusnya", "pasnya", "aman", "enaknya",
]
OCCASION_COLOR_ANSWERS = {
    "wisuda": "Buat wisuda, warna jas yang paling pas dan klasik itu Navy (biru dongker), Hitam, atau Abu-abu Tua — kesannya formal, rapi, dan enak difoto. Mau tampil beda dikit tapi tetap sopan, Abu-abu Muda juga oke. Biasanya dipaduin sama dasi warna senada atau navy/hitam polos biar makin matching.",
    "nikahan": "Buat kondangan/nikahan sebagai tamu, mending hindari hitam full biar gak kesan berkabung — coba warna yang lebih cerah tapi tetap formal kayak Abu-abu Muda, Biru Muda, atau Cream. Navy juga tetap aman dan elegan kalau mau yang klasik.",
    "lamaran": "Buat acara lamaran, biasanya paling pas warna yang kalem dan hangat kayak Cream, Abu-abu Muda, atau Coklat Tua — kesannya sopan dan gak terlalu mencolok. Navy juga bisa jadi pilihan klasik yang aman.",
    "interview_kerja": "Buat interview kerja atau acara formal kantor, paling aman dan profesional itu Navy atau Hitam — kesan rapi dan meyakinkan. Abu-abu Tua juga oke kalau mau sedikit beda tapi tetap formal.",
}


def try_event_color_suggestion(message: str) -> str | None:
    """Kalau user nyebut jenis acara (wisuda, nikahan, lamaran, interview)
    BARENG kata kunci yang nunjukkin dia lagi minta saran/rekomendasi warna,
    jawab pakai rekomendasi warna per-acara yang udah dikurasi -- bukan cuma
    daftar warna jas yang tersedia doang (itu udah ditangani intent
    tanya_warna_jas terpisah)."""
    lower = message.lower()
    if not any(kw in lower for kw in COLOR_SUGGESTION_TRIGGER_WORDS):
        return None
    for occasion, keywords in OCCASION_KEYWORDS.items():
        if any(kw in lower for kw in keywords):
            return OCCASION_COLOR_ANSWERS.get(occasion)
    return None


def try_product_attribute_answer(message: str) -> str | None:
    lower = message.lower()
    products = _detect_products_mentioned(lower)
    if len(products) != 1:
        # gak nyebut produk sama sekali, atau nyebut lebih dari 1 -> biar
        # LLM yang jawab (butuh gabungan data / konteks lebih)
        return None
    product = products[0]

    if any(kw in lower for kw in WARNA_TRIGGER_WORDS):
        tag = WARNA_INTENT_BY_PRODUCT.get(product)
        intent = INTENTS_BY_TAG.get(tag) if tag else None
        if intent:
            return intent["jawaban_default"]

    if any(kw in lower for kw in _UKURAN_TRIGGER_WORDS):
        tag = UKURAN_INTENT_BY_PRODUCT.get(product)
        intent = INTENTS_BY_TAG.get(tag) if tag else None
        if intent:
            return intent["jawaban_default"]

    return None


STOK_TRIGGER_WORDS = ["stok", "stock", "ready", "sisa", "tersisa", "kosong", "masih ada", "masih banyak"]


def try_stock_lookup_answer(message: str) -> str | None:
    lower = message.lower()
    if not any(kw in lower for kw in STOK_TRIGGER_WORDS):
        return None

    products = _detect_products_mentioned(lower)
    if len(products) != 1:
        return None
    product = products[0]

    varian = _find_warna_varian(product, lower)
    if not varian:
        return None

    ukuran = _find_ukuran_value(product, message)
    if not ukuran:
        return None

    stok_map = varian.get("stok_per_ukuran", {})
    jumlah = stok_map.get(ukuran)
    if jumlah is None:
        return None

    label = PRODUCT_LABELS[product]
    warna_txt = varian["warna"]
    if jumlah == 0:
        return (
            f"Waduh, {label} warna {warna_txt} ukuran {ukuran} lagi HABIS stoknya 🙏 "
            f"Boleh chat admin buat dicariin alternatif warna/ukuran lain yang masih ready ya."
        )
    return f"Stok {label} warna {warna_txt} ukuran {ukuran} saat ini masih ada {jumlah} pcs ya, ready buat disewa 👍"


PRICE_TRIGGER_WORDS = [
    "total", "totalnya", "berapa semua", "sekaligus", "gabungan", "harga semua",
    "biaya total", "biaya semua", "harga", "biaya", "budget",
]


def _paket_items(nama_paket: str) -> frozenset:
    lower = nama_paket.lower()
    return frozenset(p for p in PRODUCT_ALIASES if p in lower)


PAKET_BY_ITEMS = {_paket_items(p["nama_paket"]): p for p in KB["paket_sewa"]}


def try_combo_price_answer(message: str) -> str | None:
    lower = message.lower()
    products = _detect_products_mentioned(lower)
    if len(products) < 2:
        # kombinasi cuma masuk akal kalau nyebut 2+ produk sekaligus;
        # pertanyaan harga 1 produk saja ditangani guard umum tanya_harga
        return None
    if not any(kw in lower for kw in PRICE_TRIGGER_WORDS):
        return None

    items = frozenset(products)
    matched_paket = PAKET_BY_ITEMS.get(items)
    labels = " + ".join(PRODUCT_LABELS[p] for p in products)

    if matched_paket:
        return (
            f"Kalau sewa {labels} sekalian, itu udah masuk paketan \"{matched_paket['nama_paket']}\" "
            f"dengan harga {rp(matched_paket['harga_sewa_per_hari'])}/hari -- lebih hemat dibanding "
            f"disewa satuan satu-satu 👍"
        )

    total = 0
    breakdown_parts = []
    for p in products:
        harga = KB["produk"][p]["varian_warna"][0]["harga_sewa_per_hari"]
        total += harga
        breakdown_parts.append(f"{PRODUCT_LABELS[p]} {rp(harga)}")
    breakdown = ", ".join(breakdown_parts)
    return (
        f"Kalau {labels} disewa bareng (dihitung satuan, belum ada paket khusus buat kombinasi ini): "
        f"{breakdown}. Jadi totalnya sekitar {rp(total)}/hari ya."
    )


def try_general_stok_or_harga_answer(message: str) -> str | None:
    lower = message.lower()
    if any(kw in lower for kw in STOK_TRIGGER_WORDS):
        intent = INTENTS_BY_TAG.get("tanya_stok_barang")
        if intent:
            return intent["jawaban_default"]
    if any(kw in lower for kw in PRICE_TRIGGER_WORDS):
        intent = INTENTS_BY_TAG.get("tanya_harga")
        if intent:
            return intent["jawaban_default"]
    return None


_MARKDOWN_CHARS_RE = re.compile(r"[*_`#]")


def strip_markdown(text: str) -> str:
    return _MARKDOWN_CHARS_RE.sub("", text)


_SENTENCE_END_RE = re.compile(r"[.!?]")


def stream_ollama_response(
    model: str,
    messages: list,
    temperature: float,
    repeat_penalty: float = DEFAULT_REPEAT_PENALTY,
    max_tokens: int = DEFAULT_MAX_TOKENS,
):
    payload = {
        "model": model,
        "messages": messages,
        "stream": True,
        "options": {
            "temperature": temperature,
            "num_ctx": NUM_CTX,
            "repeat_penalty": repeat_penalty,
            "num_predict": max_tokens,
        },
    }

    sentence_buffer = ""
    last_sentence = None
    try:
        with requests.post(OLLAMA_URL, json=payload, stream=True, timeout=180) as resp:
            resp.raise_for_status()
            for line in resp.iter_lines():
                if not line:
                    continue
                chunk = json.loads(line.decode("utf-8"))
                if chunk.get("done"):
                    break
                content = chunk.get("message", {}).get("content", "")
                if not content:
                    continue
                sentence_buffer += strip_markdown(content)

                while True:
                    match = _SENTENCE_END_RE.search(sentence_buffer)
                    if not match:
                        break
                    end = match.end()
                    sentence = sentence_buffer[:end]
                    sentence_buffer = sentence_buffer[end:]
                    normalized = sentence.strip().lower()
                    if normalized and len(normalized) > 15 and normalized == last_sentence:
                        return  # kalimat persis diulang -> stop, jangan yield lagi
                    if normalized:
                        last_sentence = normalized
                    yield sentence

        if sentence_buffer.strip():
            yield sentence_buffer
    except requests.exceptions.Timeout:

        yield (
            "⚠️ Ollama kelamaan mikir (lebih dari 3 menit), jadi dihentikan. "
            "Ini biasanya karena model masih loading pertama kali atau laptop "
            "lagi berat — coba tanya ulang, biasanya percobaan kedua lebih cepat."
        )
    except requests.exceptions.ConnectionError:
        yield (
            "⚠️ Tidak bisa terhubung ke Ollama. Pastikan Ollama sudah jalan "
            "(buka aplikasi Ollama atau jalankan `ollama serve`), lalu coba lagi."
        )
    except requests.exceptions.HTTPError as e:
        yield f"⚠️ Error dari Ollama: {e}. Pastikan model sudah ditarik, misalnya: `ollama pull {model}`."


# ============================================================
# 4. FLASK APP
# ============================================================
app = Flask(__name__)
app.jinja_env.filters["rupiah"] = rp

# Pemetaan nama warna (Bahasa Indonesia) ke hex, buat swatch galeri warna.
WARNA_HEX = {
    "Hitam": "#111827",
    "Biru Dongker (Navy)": "#1E3A5F",
    "Biru Muda": "#7EA8D8",
    "Abu-abu Tua": "#4B5563",
    "Abu-abu Muda": "#9CA3AF",
    "Cream": "#F1E7D0",
    "Coklat Tua": "#5C4033",
    "Putih Tulang": "#F5F0E6",
    "Maroon": "#7A2331",
    "Hijau Army": "#4B5320",
    "Silver": "#C0C0C0",
    "Biru Elektrik": "#0B5ED7",
    "Coklat": "#5C4033",
    "Hitam Doff": "#1F2937",
}

# FAQ: subset intents.json yang paling relevan buat ditampilkan di landing page.
FAQ_TAGS = ["cara_sewa", "syarat_sewa", "cara_bayar", "denda_keterlambatan", "layanan_antar", "reschedule_pembatalan"]


def build_faq(intents: list) -> list:
    by_tag = {i["intent"]: i for i in intents}
    faq = []
    for tag in FAQ_TAGS:
        intent = by_tag.get(tag)
        if intent:
            faq.append({"q": intent["contoh_pertanyaan"][0], "a": intent["jawaban_default"]})
    return faq


FAQ = build_faq(INTENTS)


@app.route("/")
def index():
    return render_template(
        "index.html",
        default_model=DEFAULT_MODEL,
        shop_name=KB["informasi_toko"]["nama_usaha"],
        info=KB["informasi_toko"],
        produk=KB["produk"],
        paket=KB["paket_sewa"],
        warna_hex=WARNA_HEX,
        faq=FAQ,
    )


@app.route("/api/chat", methods=["POST"])
def api_chat():
    data = request.get_json(force=True)
    user_message = (data.get("message") or "").strip()
    history = data.get("history") or []  # [{role, content}, ...] tanpa system prompt
    model = data.get("model") or DEFAULT_MODEL
    temperature = float(data.get("temperature", DEFAULT_TEMPERATURE))

    if not user_message:
        return jsonify({"error": "Pesan kosong."}), 400

    if is_off_topic(user_message) and TIDAK_DIKENALI_INTENT:
        off_topic_reply = TIDAK_DIKENALI_INTENT["jawaban_default"]

        def generate_static():
            yield off_topic_reply

        return Response(stream_with_context(generate_static()), mimetype="text/plain")

    greeting_reply = try_greeting_answer(user_message)
    if greeting_reply:
        def generate_static_greeting():
            yield greeting_reply

        return Response(stream_with_context(generate_static_greeting()), mimetype="text/plain")

    size_reply = try_size_answer(user_message)
    if size_reply:
        def generate_static_size():
            yield size_reply

        return Response(stream_with_context(generate_static_size()), mimetype="text/plain")

    location_hours_reply = try_location_hours_answer(user_message)
    if location_hours_reply:
        def generate_static_location_hours():
            yield location_hours_reply

        return Response(stream_with_context(generate_static_location_hours()), mimetype="text/plain")

    damage_loss_reply = try_damage_loss_answer(user_message)
    if damage_loss_reply:
        def generate_static_damage_loss():
            yield damage_loss_reply

        return Response(stream_with_context(generate_static_damage_loss()), mimetype="text/plain")

    sensitive_reply = match_sensitive_intent(user_message)
    if sensitive_reply:
        def generate_static_sensitive():
            yield sensitive_reply

        return Response(stream_with_context(generate_static_sensitive()), mimetype="text/plain")

    qris_reply = try_qris_answer(user_message)
    if qris_reply:
        def generate_static_qris():
            yield qris_reply

        return Response(stream_with_context(generate_static_qris()), mimetype="text/plain")

    static_reply = match_static_intent(user_message)
    if static_reply:
        def generate_static_common():
            yield static_reply

        return Response(stream_with_context(generate_static_common()), mimetype="text/plain")

    event_color_reply = try_event_color_suggestion(user_message)
    if event_color_reply:
        def generate_static_event_color():
            yield event_color_reply

        return Response(stream_with_context(generate_static_event_color()), mimetype="text/plain")

    stock_reply = try_stock_lookup_answer(user_message)
    if stock_reply:
        def generate_static_stock():
            yield stock_reply

        return Response(stream_with_context(generate_static_stock()), mimetype="text/plain")

    combo_price_reply = try_combo_price_answer(user_message)
    if combo_price_reply:
        def generate_static_combo_price():
            yield combo_price_reply

        return Response(stream_with_context(generate_static_combo_price()), mimetype="text/plain")

    attribute_reply = try_product_attribute_answer(user_message)
    if attribute_reply:
        def generate_static_attribute():
            yield attribute_reply

        return Response(stream_with_context(generate_static_attribute()), mimetype="text/plain")

    general_reply = try_general_stok_or_harga_answer(user_message)
    if general_reply:
        def generate_static_general():
            yield general_reply

        return Response(stream_with_context(generate_static_general()), mimetype="text/plain")

    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + history + [
        {"role": "user", "content": user_message}
    ]

    if _mentions_ukuran(user_message):
        def generate_validated():
            full_text = "".join(stream_ollama_response(model, messages, temperature))
            yield _validate_size_mentions(full_text)

        return Response(stream_with_context(generate_validated()), mimetype="text/plain")

    def generate():
        for token in stream_ollama_response(model, messages, temperature):
            yield token

    return Response(stream_with_context(generate()), mimetype="text/plain")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)