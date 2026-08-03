"""
generate_qris.py — Generate gambar barcode pembayaran (QR statis)
====================================================================

Ini BUKAN QRIS resmi/tersertifikasi PJSP (Bank Indonesia). Ini QR statis
dummy yang isinya info rekening toko dalam bentuk teks — dipakai supaya
fitur "barcode pembayaran" bisa langsung didemokan di chatbot tanpa perlu
daftar merchant QRIS beneran.

Kalau nanti mau pakai QRIS asli (bisa dipindai semua e-wallet & scan-to-pay
beneran), ganti isi variabel PAYLOAD di bawah dengan string QRIS resmi yang
didapat dari bank/penyedia QRIS kamu, lalu jalankan ulang script ini.

Cara pakai:
    pip install qrcode[pil]
    python generate_qris.py

Data rekening diambil otomatis dari knowledge_base.json supaya gambar QR
selalu sinkron kalau nomor rekening/e-wallet diganti.
"""

import json
from pathlib import Path

import qrcode
from qrcode.image.styledpil import StyledPilImage
from qrcode.image.styles.colormasks import SolidFillColorMask
from qrcode.image.styles.moduledrawers import RoundedModuleDrawer

DATA_DIR = Path(__file__).parent
OUT_PATH = DATA_DIR / "static" / "assets" / "qris-pembayaran.png"

with open(DATA_DIR / "knowledge_base.json", encoding="utf-8") as f:
    kb = json.load(f)

info = kb["informasi_toko"]
rek = info["rekening_pembayaran"]

PAYLOAD = (
    f"Pembayaran {info['nama_usaha']}\n"
    f"Bank: {rek['bank']}\n"
    f"No. Rekening: {rek['nomor_rekening']}\n"
    f"a.n. {rek['atas_nama']}\n"
    f"E-wallet: {' / '.join(rek['e_wallet'])} ke nomor {info['kontak']}"
)

qr = qrcode.QRCode(
    version=None,
    error_correction=qrcode.constants.ERROR_CORRECT_M,
    box_size=10,
    border=3,
)
qr.add_data(PAYLOAD)
qr.make(fit=True)

img = qr.make_image(
    image_factory=StyledPilImage,
    module_drawer=RoundedModuleDrawer(),
    color_mask=SolidFillColorMask(front_color=(15, 23, 42), back_color=(255, 255, 255)),
)
img.save(OUT_PATH)
print(f"Barcode pembayaran disimpan ke: {OUT_PATH}")
