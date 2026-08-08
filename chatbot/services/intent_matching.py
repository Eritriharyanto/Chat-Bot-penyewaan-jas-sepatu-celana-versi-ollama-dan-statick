"""Semua logic pencocokan intent berbasis keyword: deteksi pesan di luar
topik, intent sensitif (denda/reschedule/dll), sapaan, intent statis
bawaan kode, dan intent custom yang keyword-nya diisi lewat admin panel."""
import re

from chatbot import state

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
        if any(kw in lower for kw in state.DOMAIN_KEYWORDS):
            return False
        return True

    return False


SENSITIVE_INTENT_KEYWORDS = [
    ("denda_kerusakan_kehilangan", [
        "hilang", "ilang", "kehilangan", "kehilangannya",
        "rusak", "kerusakan", "sobek", "kotor parah", "kebakar", "bolong",
    ]),
    ("reschedule_sewa", [
        "reschedule", "resceduel", "reschedul", "geser tanggal", "ganti tanggal",
        "pindah tanggal", "geser jadwal", "tukar tanggal", "undur tanggal",
    ]),
    ("pembatalan_sewa", [
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


def match_sensitive_intent(message: str) -> str | None:
    lower = message.lower()
    for tag, keywords in SENSITIVE_INTENT_KEYWORDS:
        if any(kw.lower() in lower for kw in keywords):
            intent = state.INTENTS_BY_TAG.get(tag)
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
        sapaan_intent = state.INTENTS_BY_TAG.get("sapaan")
        if sapaan_intent:
            return sapaan_intent["jawaban_default"]
    return None


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
    ("tanya_alamat", [
        "alamat", "lokasi toko", "posisi toko", "dimana toko", "toko dimana",
        "tempatnya dimana", "tempatnya apa", "gmaps", "google maps", "map nya",
        "patokan", "rute ke toko", "arah ke toko", "dari stasiun", "kesininya",
        "cara kesana", "nyampe sana", "letak toko", "posisi tokonya", "lokasi", "info lokasi",
    ]),
    ("tanya_jam_operasional", [
        "jam buka", "jam tutup", "jam operasional", "buka jam", "tutup jam",
        "buka dari jam", "jam berapa buka", "buka sampai jam", "operasional toko",
        "buka setiap hari", "buka weekend", "buka hari libur", "buka tanggal merah",
        "masih terima tamu", "jam kerja toko", "buka full seharian",
    ]),
    ("bayar_qris", [
        "qris", "bayar qris", "bisa qris", "scan qris", "kode qr",
        "qr code", "barcode qris", "gambar qris", "kirim qris",
        "qrisnya mana", "pakai qris", "lewat qris", "via qris",
    ]),
    ("cara_bayar", [
        "cara bayar", "metode bayar", "metode pembayaran", "bayar pakai apa",
        "bayar pake apa", "bisa transfer", "transfer bank",
        "bisa cash", "bayar cash", "bukti transfer",
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
        "thanks", "thank you", "oke", "ok", "sip", "mantap", "bagus", "keren", "top markotop",
    ]),
    ("tanya_kontak", [
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
    ("cara_perpanjang_sewa", [
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
    ("testimoni_toko", [
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
    ("tanya_komplain_pelayanan", [
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


def match_static_intent(message: str) -> str | None:
    lower = message.lower()
    for tag, keywords in STATIC_INTENT_KEYWORDS:
        if any(kw in lower for kw in keywords):
            intent = state.INTENTS_BY_TAG.get(tag)
            if intent:
                return intent["jawaban_default"]
    return None


def match_static_intent_tag(message: str) -> str | None:
    """Sama seperti match_static_intent, tapi return NAMA TAG intent-nya
    (bukan teks jawaban). Dipakai buat nentuin apakah balasan ini perlu
    ditempeli elemen interaktif tambahan (link WA, link Maps, gambar QRIS)."""
    lower = message.lower()
    for tag, keywords in STATIC_INTENT_KEYWORDS:
        if any(kw in lower for kw in keywords):
            return tag
    return None


def detect_chat_action(user_message: str, matched_tag: str | None) -> str:
    """Tentukan elemen interaktif tambahan apa (kalau ada) yang perlu
    ditampilkan di bawah bubble jawaban asisten:
    - 'qris'   -> intent 'bayar_qris' -> tampilkan gambar QRIS + tombol konfirmasi WA
    - 'alamat' -> intent 'tanya_alamat' -> tampilkan tombol buka Google Maps
    - 'kontak' -> intent 'tanya_kontak'/'cara_bayar' -> tombol chat WA
    - ''       -> tidak ada elemen tambahan
    """
    if matched_tag == "bayar_qris":
        return "qris"
    if matched_tag == "tanya_alamat":
        return "alamat"
    if matched_tag in ("tanya_kontak", "cara_bayar"):
        return "kontak"
    return ""


def match_custom_intent(message: str) -> str | None:
    """Cek intent yang keyword pemicunya diisi lewat admin panel (field
    'keywords' di intents.json). Ini melengkapi match_static_intent yang
    daftar keyword-nya di-hardcode di kode ini — jadi admin/CS bisa
    menambahkan FAQ baru beserta kata kunci pemicunya TANPA edit kode."""
    lower = message.lower()
    for intent in state.INTENTS:
        keywords = intent.get("keywords") or []
        if keywords and any(kw.lower() in lower for kw in keywords):
            return intent["jawaban_default"]
    return None
