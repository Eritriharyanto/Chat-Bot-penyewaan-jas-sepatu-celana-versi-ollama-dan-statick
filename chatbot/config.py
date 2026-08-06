"""
Konfigurasi & konstanta global aplikasi.

Semua path, nilai default model Ollama, dan tabel referensi statis
(daftar ukuran standar, warna->hex, tag FAQ) ditaruh di sini supaya
mudah diubah tanpa perlu bongkar kode logic di modul lain.
"""
from pathlib import Path

# Chatbot7inc/  (root project, 1 level di atas folder package "chatbot")
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"

KB_PATH = DATA_DIR / "knowledge_base.json"
INTENTS_PATH = DATA_DIR / "intents.json"
ADMIN_CONFIG_PATH = DATA_DIR / "admin_config.json"
CHAT_DB_PATH = DATA_DIR / "chat_history.db"

TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

# ---------- Ollama ----------
OLLAMA_URL = "http://localhost:11434/api/chat"
DEFAULT_MODEL = "qwen2.5:0.5b"
NUM_CTX = 3192
DEFAULT_TEMPERATURE = 0.3
DEFAULT_REPEAT_PENALTY = 1.3
DEFAULT_MAX_TOKENS = 400

# ---------- Admin panel ----------
UKURAN_STANDAR = ["XS", "S", "M", "L", "XL", "XXL", "XXXL", "4XL", "5XL"]

# FAQ: subset intents.json yang paling relevan buat ditampilkan di landing page.
FAQ_TAGS = ["cara_sewa", "syarat_sewa", "cara_bayar", "denda_keterlambatan", "layanan_antar", "reschedule_pembatalan"]

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
