"""Validasi & normalisasi identitas visitor (nama + nomor telepon) yang
wajib diisi sebelum bisa mulai chat, plus pencatatan pesan ke riwayat."""
import re

from chatbot import db

_PHONE_RE = re.compile(r"^(?:\+62|62|0)8[0-9]{7,11}$")


class VisitorValidationError(Exception):
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


def normalize_phone(nomor_telepon: str) -> str:
    """Samakan format nomor telepon jadi awalan '62' (tanpa '+'), biar
    nomor yang sama gak dianggap 2 visitor beda cuma gara-gara ditulis
    '0812...' vs '+62812...' vs '62812...'."""
    digits = re.sub(r"\D", "", nomor_telepon or "")
    if digits.startswith("0"):
        digits = "62" + digits[1:]
    elif not digits.startswith("62"):
        digits = "62" + digits
    return digits


def register_visitor(nama: str, nomor_telepon: str):
    """Validasi input dari form gerbang chat, lalu simpan/perbarui identitas
    visitor. Raise VisitorValidationError kalau inputnya gak valid."""
    nama = (nama or "").strip()
    nomor_telepon_raw = (nomor_telepon or "").strip()

    if len(nama) < 2:
        raise VisitorValidationError("Nama minimal 2 karakter.")
    if len(nama) > 80:
        raise VisitorValidationError("Nama terlalu panjang.")
    if not _PHONE_RE.match(nomor_telepon_raw.replace(" ", "").replace("-", "")):
        raise VisitorValidationError("Nomor telepon tidak valid. Contoh: 08123456789.")

    nomor_normal = normalize_phone(nomor_telepon_raw)
    return db.upsert_visitor(nama, nomor_normal)
