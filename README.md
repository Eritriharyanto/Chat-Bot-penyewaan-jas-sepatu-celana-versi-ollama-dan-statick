## 1. Install Ollama

Download & install dari **https://ollama.com/download** (Windows/macOS/Linux).
Setelah terinstall, Ollama otomatis jalan sebagai service di background
(`http://localhost:11434`).

## 2. Tarik (download) model

```bash
ollama pull llama3.2:3b
```

Kalau nanti laptop terasa berat, ganti ke model yang lebih kecil:

```bash
ollama pull qwen2.5:1.5b
```

lalu isi nama model itu di kolom **"Model Ollama"** pada panel pengaturan (ikon
gear di pojok kanan atas aplikasi).

## 3. Install dependency Python

Pastikan Python 3.10+ sudah terpasang (kode ini pakai sintaks `str | None`).
Di folder project ini:

```bash
pip install -r requirements.txt
```

## 4. Jalankan aplikasi

```bash
python run.py
```

Buka browser ke **http://localhost:5000**.

## Struktur folder

```
Chatbot7inc/
├── run.py                      # Entry point ("python run.py" buat start server)
├── requirements.txt
├── data/                       # Semua data yang bisa berubah saat runtime
│   ├── knowledge_base.json     # Data toko (harga, ukuran, kebijakan, dll)
│   ├── intents.json            # Q&A per intent (referensi gaya bicara + keyword FAQ)
│   ├── admin_config.json       # Login admin (username, password ter-hash, secret key)
│   └── chat_history.db         # SQLite: identitas visitor + riwayat chat (auto-dibuat)
├── templates/
│   ├── index.html              # Halaman chat
│   └── admin/                  # Semua halaman panel admin
├── static/
│   ├── css/style.css           # Tampilan chat (tema navy & brass, terinspirasi tailor shop)
│   ├── css/admin.css           # Tampilan panel admin
│   └── js/chat.js              # Logic kirim pesan & streaming respons
└── chatbot/                    # Package Python utama (dulu semuanya 1 file app.py)
    ├── __init__.py             # create_app() — application factory Flask
    ├── config.py               # Konstanta & path (Ollama, file data, warna, dll)
    ├── state.py                # Runtime state: KB, INTENTS, SYSTEM_PROMPT, dan
    │                           # reload_runtime_state() buat refresh tanpa restart
    ├── db.py                   # Akses SQLite: identitas visitor & riwayat chat
    ├── services/                # Logic bisnis murni (tidak menyentuh Flask request)
    │   ├── formatting.py        # Format rupiah, link WA, link Maps, strip markdown
    │   ├── kb_summary.py        # Ringkas knowledge base -> system prompt LLM + FAQ
    │   ├── intent_matching.py   # Deteksi off-topic, intent sensitif, sapaan, FAQ statis/custom
    │   ├── size_matching.py     # Cocokkan ukuran dari cm/kg, validasi jawaban LLM soal ukuran
    │   ├── product_lookup.py    # Deteksi produk, warna/ukuran spesifik, stok, harga kombinasi
    │   ├── ollama_client.py     # Streaming response dari Ollama
    │   └── visitors.py          # Validasi & registrasi identitas visitor (nama + no. telp)
    └── routes/                  # Endpoint Flask, dipecah per fitur
        ├── public.py             # "/", "/api/chat", "/api/visitor", "/api/visitor/me"
        ├── auth.py               # Login/logout admin + decorator @admin_login_required
        └── admin/                 # Semua route /admin/*, 1 file per submenu
            ├── dashboard.py
            ├── produk.py          # Kategori produk + varian warna/harga/stok
            ├── paket.py           # Paket sewa kombinasi
            ├── info_toko.py       # Info toko (form + mode lanjutan JSON mentah)
            ├── intents.py         # CRUD FAQ/intent custom
            ├── riwayat.py         # Rekap chat: daftar visitor + transkrip percakapan
            └── pengaturan.py      # Ganti password admin
```

Nama endpoint Flask (dipakai `url_for(...)` di semua template) **tidak berubah
sama sekali** dari versi 1-file sebelumnya — jadi kalau ada yang mau nambah
halaman baru, tinggal ikuti pola modul yang sudah ada tanpa perlu sentuh
template lama.

## Cara kerja singkat

1. `knowledge_base.json` diringkas jadi teks (harga, ukuran, warna, kebijakan, dll)
   saat server Flask start (lihat `chatbot/services/kb_summary.py`).
2. Beberapa contoh Q&A dari `intents.json` disertakan sebagai referensi gaya
   bicara (santai, ramah, ala admin online shop).
3. Sebelum pesan user dikirim ke Ollama, ada rangkaian "guard" berbasis
   keyword (`chatbot/services/intent_matching.py`, `size_matching.py`,
   `product_lookup.py`) yang mencoba jawab langsung pakai data pasti —
   lebih cepat, lebih akurat, dan gratis (gak perlu panggil LLM). Kalau
   semua guard itu gak ada yang cocok, baru diserahkan ke Ollama.

## Gerbang identitas & riwayat chat

Sebelum bisa mulai chat, pengunjung wajib isi **nama & nomor telepon/WhatsApp**
lewat modal yang muncul otomatis. Sekali diisi, disimpan di session browser
(cookie) jadi gak perlu isi ulang tiap buka widget chat lagi. Kalau nomor
telepon yang sama chat lagi di kunjungan berikutnya, riwayatnya otomatis
nyambung ke identitas yang sama (bukan bikin baru) — lihat `db.upsert_visitor()`.

Setiap pesan (baik dari user maupun jawaban bot — dari guard statis maupun
dari Ollama) tercatat otomatis ke `data/chat_history.db` (SQLite bawaan
Python, **tidak nambah dependency baru**). Rekapnya bisa dilihat admin di
menu **Riwayat Chat**: daftar semua visitor (nama, nomor, jumlah pesan,
terakhir aktif, bisa dicari), klik salah satu buat lihat transkrip lengkap
percakapannya.

> Endpoint `/api/chat` menolak request (401) kalau browser itu belum isi
> identitas — jadi chatbot gak akan pernah balas apa pun sebelum nama &
> nomor telepon terisi.

## Panel admin (`/admin`)

- **Produk & Stok** — update harga sewa, stok per ukuran, tambah/hapus varian
  warna, tambah kategori produk baru
- **Paket Sewa** — tambah/edit/hapus paket gabungan (Jas+Celana+Sepatu, dll)
- **Info Toko** — jam operasional, kontak, alamat, syarat sewa, kebijakan
  denda/DP, promo. Ada juga mode lanjutan (edit JSON mentah) buat field yang
  jarang berubah dan belum ada form khususnya.
- **FAQ / Jawaban Chatbot** — tambah pertanyaan baru beserta kata kunci
  pemicunya. Begitu kata kunci itu muncul di chat user, chatbot langsung
  jawab pakai jawaban yang diisi di panel — ga perlu mikir ke AI/Ollama sama
  sekali, jadi lebih cepat & konsisten. Jawaban intent lama (bawaan
  developer) juga bisa diedit di sini.
- **Riwayat Chat** — daftar semua orang yang pernah chat (nama, nomor
  telepon, jumlah pesan, terakhir aktif) beserta transkrip lengkap tiap
  percakapan.

Semua perubahan disimpan ke `data/knowledge_base.json` / `data/intents.json`
dan langsung aktif di chatbot saat itu juga lewat `state.reload_runtime_state()`
(server otomatis reload data-nya di belakang layar, tidak perlu restart Flask
atau training ulang apa pun).

> Catatan keamanan: panel ini pakai login sederhana (1 akun admin, tanpa
> HTTPS bawaan). Kalau di-deploy ke internet (bukan cuma localhost), pasang
> di belakang HTTPS/reverse proxy dan pastikan password sudah diganti dari
> default.

> Catatan privasi: `data/chat_history.db` menyimpan nama & nomor telepon asli
> pengunjung. Perlakukan file ini sama hati-hatinya dengan `admin_config.json`
> — jangan di-commit ke repo publik, dan backup/hapus sesuai kebijakan privasi
> data pelanggan yang berlaku di tempat kamu.

## Troubleshooting

- **"Tidak bisa terhubung ke Ollama"** → pastikan aplikasi Ollama sudah jalan,
  atau jalankan manual: `ollama serve`.
- **Error model not found** → pastikan sudah `ollama pull <nama_model>` sesuai
  yang diisi di kolom "Model Ollama".
- **Port 5000 sudah dipakai** → ubah baris terakhir `run.py`:
  `app.run(host="0.0.0.0", port=5001, debug=True)` lalu buka
  `http://localhost:5001`.
