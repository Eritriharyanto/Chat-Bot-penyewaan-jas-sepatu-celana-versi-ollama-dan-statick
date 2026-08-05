"""Helper format teks kecil-kecil yang dipakai di banyak tempat: format
rupiah, link WhatsApp, link Google Maps, dan pembersih simbol markdown."""
import re
from urllib.parse import quote


def rp(n: int) -> str:
    return f"Rp{n:,}".replace(",", ".")


def build_wa_link(nomor: str, pesan: str = "") -> str:
    """Ubah nomor kontak toko (mis. '0812-3456-7890') jadi link wa.me yang
    langsung bisa diklik & membuka chat WhatsApp. Nomor diawali '0' otomatis
    diganti kode negara '62' sesuai format yang diminta wa.me."""
    digits = re.sub(r"\D", "", nomor or "")
    if digits.startswith("0"):
        digits = "62" + digits[1:]
    elif not digits.startswith("62"):
        digits = "62" + digits
    link = f"https://wa.me/{digits}"
    if pesan:
        link += f"?text={quote(pesan)}"
    return link


def build_maps_link(alamat: str) -> str:
    """Ubah teks alamat toko jadi link pencarian Google Maps yang bisa diklik."""
    return f"https://www.google.com/maps/search/?api=1&query={quote(alamat or '')}"


_MARKDOWN_CHARS_RE = re.compile(r"[*_`#]")


def strip_markdown(text: str) -> str:
    return _MARKDOWN_CHARS_RE.sub("", text)
