"""
Runtime state chatbot: knowledge base, intents, system prompt, dan semua
nilai turunan yang dibangun dari data itu.

PENTING soal cara pakai modul ini di file lain:
Modul lain WAJIB akses state lewat `state.KB`, `state.INTENTS`, dst (import
modulnya: `from chatbot import state`), BUKAN `from chatbot.state import KB`.
Kalau pakai cara kedua, nilai yang di-import bakal "beku" di titik waktu
import terjadi -- begitu reload_runtime_state() dipanggil (misal admin
simpan perubahan lewat admin panel), nilai global di sini berubah, tapi
salinan yang ke-import di file lain nggak ikut berubah. Ini satu-satunya
tempat yang boleh melakukan reassignment ke variabel-variabel di bawah.
"""
import json
import re

from chatbot.config import ADMIN_CONFIG_PATH, INTENTS_PATH, KB_PATH

# ---------- Data utama ----------
KB: dict = {}
INTENTS: list = []
ADMIN_CONFIG: dict = {}

# ---------- Nilai turunan (dibangun ulang oleh reload_runtime_state) ----------
SYSTEM_PROMPT: str = ""
TIDAK_DIKENALI_INTENT: dict | None = None
INTENTS_BY_TAG: dict = {}
DOMAIN_KEYWORDS: set = set()
PAKET_BY_ITEMS: dict = {}
FAQ: list = []

SIZE_LABELS_SORTED: list = []
SIZE_LABEL_RE: re.Pattern | None = None
SIZE_CHART_BY_LABEL: dict = {}


# ============================================================
# Baca / tulis file JSON di disk
# ============================================================
def load_data() -> tuple[dict, list]:
    with open(KB_PATH, encoding="utf-8") as f:
        kb = json.load(f)
    with open(INTENTS_PATH, encoding="utf-8") as f:
        intents = json.load(f)["intents"]
    return kb, intents


def save_kb(kb: dict) -> None:
    """Simpan knowledge_base.json ke disk lalu refresh semua state runtime
    yang diturunkan darinya, biar perubahan lewat admin panel langsung
    kepake tanpa perlu restart server."""
    with open(KB_PATH, "w", encoding="utf-8") as f:
        json.dump(kb, f, ensure_ascii=False, indent=2)
    reload_runtime_state()


def save_intents(intents: list) -> None:
    """Sama seperti save_kb, tapi buat intents.json."""
    with open(INTENTS_PATH, "w", encoding="utf-8") as f:
        json.dump({"intents": intents}, f, ensure_ascii=False, indent=2)
    reload_runtime_state()


def load_admin_config() -> dict:
    with open(ADMIN_CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def save_admin_config(config: dict) -> None:
    with open(ADMIN_CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)


# ============================================================
# Bangun ulang semua state turunan
# ============================================================
def reload_runtime_state() -> None:
    """Baca ulang knowledge_base.json & intents.json dari disk, lalu bangun
    ulang SEMUA state turunan yang dipakai chatbot (system prompt, kata
    kunci domain, FAQ landing page, dll). Dipanggil setiap kali admin
    panel menyimpan perubahan, biar efeknya langsung kepake tanpa restart
    server Flask."""
    global KB, INTENTS, SYSTEM_PROMPT, TIDAK_DIKENALI_INTENT, INTENTS_BY_TAG
    global DOMAIN_KEYWORDS, PAKET_BY_ITEMS, FAQ
    global SIZE_LABELS_SORTED, SIZE_LABEL_RE, SIZE_CHART_BY_LABEL

    # Import di dalam fungsi (bukan di atas file) supaya nggak circular
    # import: modul services/* juga butuh `from chatbot import state` buat
    # baca KB/INTENTS_BY_TAG dkk, jadi state.py sendiri baru boleh "narik"
    # fungsi builder dari services pas fungsi ini dipanggil, bukan pas
    # state.py pertama kali di-import.
    from chatbot.services.kb_summary import build_domain_keywords, build_faq, build_system_prompt
    from chatbot.services.product_lookup import build_paket_by_items

    KB, INTENTS = load_data()
    SYSTEM_PROMPT = build_system_prompt(KB, INTENTS)
    TIDAK_DIKENALI_INTENT = next((i for i in INTENTS if i["intent"] == "tidak_dikenali"), None)
    INTENTS_BY_TAG = {i["intent"]: i for i in INTENTS}
    DOMAIN_KEYWORDS = build_domain_keywords(KB)
    PAKET_BY_ITEMS = build_paket_by_items(KB)
    FAQ = build_faq(INTENTS)

    size_chart = KB["produk"].get("jas", {}).get("size_chart", [])
    # Sort dari label terpanjang -> terpendek, biar saat dicocokkan sebagai
    # regex "XXXL" dicek duluan sebelum "XXL" sebelum "XL" (jangan sampai
    # ke-cut duluan oleh label yang lebih pendek).
    SIZE_LABELS_SORTED = sorted((row["ukuran"] for row in size_chart), key=len, reverse=True)
    SIZE_LABEL_RE = (
        re.compile("(" + "|".join(re.escape(s) for s in SIZE_LABELS_SORTED) + ")", re.IGNORECASE)
        if SIZE_LABELS_SORTED
        else None
    )
    SIZE_CHART_BY_LABEL = {row["ukuran"]: row for row in size_chart}
