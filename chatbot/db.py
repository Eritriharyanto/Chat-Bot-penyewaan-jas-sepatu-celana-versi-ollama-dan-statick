"""
Penyimpanan riwayat chat memakai SQLite (modul bawaan Python, tidak nambah
dependency baru). Beda dari knowledge_base.json/intents.json yang isinya
data toko yang jarang berubah dan diedit lewat form, data di sini terus
bertambah tiap ada chat baru -- makanya dipisah lewat database, bukan file
JSON yang ditulis ulang seluruhnya tiap kali (bisa berat & rawan konflik
kalau datanya sudah banyak).

Isinya 2 tabel:
- visitors        satu baris per nomor telepon (identitas pengunjung chat)
- chat_messages   satu baris per pesan (baik dari user maupun dari bot),
                   terhubung ke visitors lewat visitor_id
"""
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from chatbot.config import CHAT_DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS visitors (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    nama            TEXT NOT NULL,
    nomor_telepon   TEXT NOT NULL UNIQUE,
    created_at      TEXT NOT NULL,
    last_seen_at    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    visitor_id      INTEGER NOT NULL REFERENCES visitors(id),
    role            TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
    content         TEXT NOT NULL,
    chat_action     TEXT,
    created_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_chat_messages_visitor ON chat_messages(visitor_id);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def get_conn():
    conn = sqlite3.connect(CHAT_DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    """Bikin tabel kalau belum ada. Aman dipanggil berkali-kali (dipanggil
    setiap kali aplikasi start)."""
    with get_conn() as conn:
        conn.executescript(SCHEMA)


# ============================================================
# Visitor (identitas pengunjung: nama + nomor telepon)
# ============================================================
def find_visitor_by_phone(nomor_telepon: str) -> sqlite3.Row | None:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM visitors WHERE nomor_telepon = ?", (nomor_telepon,)
        ).fetchone()


def find_visitor_by_id(visitor_id: int) -> sqlite3.Row | None:
    with get_conn() as conn:
        return conn.execute("SELECT * FROM visitors WHERE id = ?", (visitor_id,)).fetchone()


def upsert_visitor(nama: str, nomor_telepon: str) -> sqlite3.Row:
    """Kalau nomor telepon ini sudah pernah chat sebelumnya, pakai baris yang
    sama (namanya ikut di-update kalau beda) supaya riwayat chat-nya
    nyambung terus jadi satu percakapan panjang -- bukan bikin identitas
    baru tiap kali dia isi form lagi. Kalau belum pernah, baru dibikin
    baris baru."""
    now = _now()
    with get_conn() as conn:
        existing = conn.execute(
            "SELECT * FROM visitors WHERE nomor_telepon = ?", (nomor_telepon,)
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE visitors SET nama = ?, last_seen_at = ? WHERE id = ?",
                (nama, now, existing["id"]),
            )
            visitor_id = existing["id"]
        else:
            cur = conn.execute(
                "INSERT INTO visitors (nama, nomor_telepon, created_at, last_seen_at) VALUES (?, ?, ?, ?)",
                (nama, nomor_telepon, now, now),
            )
            visitor_id = cur.lastrowid
        return conn.execute("SELECT * FROM visitors WHERE id = ?", (visitor_id,)).fetchone()


def touch_visitor(visitor_id: int) -> None:
    """Update waktu terakhir aktif, dipanggil tiap kali visitor kirim pesan."""
    with get_conn() as conn:
        conn.execute("UPDATE visitors SET last_seen_at = ? WHERE id = ?", (_now(), visitor_id))


def list_visitors(q: str = "") -> list[sqlite3.Row]:
    """Daftar visitor buat halaman rekap admin, diurutkan dari yang paling
    baru aktif, sekalian jumlah pesan tiap visitor.

    nomor_telepon di DB selalu tersimpan dalam format ternormalisasi
    (awalan '62', lihat services/visitors.py), sedangkan admin biasanya
    cari pakai format lokal ('0812...'). Jadi kalau query-nya kelihatan
    kayak nomor telepon, dicoba juga versi ternormalisasinya biar tetap
    ketemu.
    """
    sql = """
        SELECT v.*, COUNT(m.id) AS jumlah_pesan
        FROM visitors v
        LEFT JOIN chat_messages m ON m.visitor_id = v.id
    """
    params: tuple = ()
    if q:
        from chatbot.services.visitors import normalize_phone

        digits_only = re.sub(r"\D", "", q)
        if digits_only:
            like_normal = f"%{normalize_phone(digits_only)}%"
        else:
            like_normal = f"%{q}%"
        like_raw = f"%{q}%"
        sql += " WHERE v.nama LIKE ? OR v.nomor_telepon LIKE ? OR v.nomor_telepon LIKE ?"
        params = (like_raw, like_raw, like_normal)
    sql += " GROUP BY v.id ORDER BY v.last_seen_at DESC"
    with get_conn() as conn:
        return conn.execute(sql, params).fetchall()


def count_visitors() -> int:
    with get_conn() as conn:
        return conn.execute("SELECT COUNT(*) FROM visitors").fetchone()[0]


# ============================================================
# Chat messages
# ============================================================
def log_message(visitor_id: int, role: str, content: str, chat_action: str = "") -> None:
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO chat_messages (visitor_id, role, content, chat_action, created_at) VALUES (?, ?, ?, ?, ?)",
            (visitor_id, role, content, chat_action or None, _now()),
        )


def get_messages_for_visitor(visitor_id: int) -> list[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM chat_messages WHERE visitor_id = ? ORDER BY created_at ASC, id ASC",
            (visitor_id,),
        ).fetchall()


def count_messages() -> int:
    with get_conn() as conn:
        return conn.execute("SELECT COUNT(*) FROM chat_messages").fetchone()[0]
