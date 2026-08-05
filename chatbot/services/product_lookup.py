"""Logic yang berhubungan langsung dengan data produk: deteksi produk apa
yang disebut user, cari varian warna/ukuran spesifik, saran warna per
acara, lookup stok pasti, dan hitung harga kombinasi beberapa produk."""
import re

from chatbot import state
from chatbot.services.formatting import rp
from chatbot.services.size_matching import UKURAN_TRIGGER_WORDS

PRODUCT_ALIASES = {
    "jas": ["jas"],
    "celana": ["celana"],
    "sepatu": ["sepatu", "pantofel"],
    "vest": ["vest", "rompi"],
    "dasi": ["dasi"],
}
PRODUCT_LABELS = {"jas": "jas", "celana": "celana", "sepatu": "sepatu", "vest": "vest/rompi", "dasi": "dasi"}


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
    detail = state.KB["produk"].get(product, {})
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
    detail = state.KB["produk"].get(product, {})
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
    "vest": "tanya_warna_vest",
}
UKURAN_INTENT_BY_PRODUCT = {
    "jas": "tanya_ukuran",
    "celana": "tanya_ukuran_celana",
    "sepatu": "tanya_ukuran_sepatu",
    "dasi": "tanya_ukuran_dasi",
    "vest": "tanya_ukuran_vest",
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
        intent = state.INTENTS_BY_TAG.get(tag) if tag else None
        if intent:
            return intent["jawaban_default"]

    if any(kw in lower for kw in UKURAN_TRIGGER_WORDS):
        tag = UKURAN_INTENT_BY_PRODUCT.get(product)
        intent = state.INTENTS_BY_TAG.get(tag) if tag else None
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


def build_paket_by_items(kb: dict) -> dict:
    return {_paket_items(p["nama_paket"]): p for p in kb["paket_sewa"]}


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
    matched_paket = state.PAKET_BY_ITEMS.get(items)
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
        harga = state.KB["produk"][p]["varian_warna"][0]["harga_sewa_per_hari"]
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
        intent = state.INTENTS_BY_TAG.get("tanya_stok_barang")
        if intent:
            return intent["jawaban_default"]
    if any(kw in lower for kw in PRICE_TRIGGER_WORDS):
        intent = state.INTENTS_BY_TAG.get("tanya_harga")
        if intent:
            return intent["jawaban_default"]
    return None
