# IG Follower Profiler

Dashboard Streamlit untuk memprofilkan follower sebuah akun Instagram: keaslian (asli/mencurigakan/bot),
lama vs baru, demografi, dan geografi.

```bash
pip install -r requirements.txt
streamlit run app.py
```

Sumber data (sidebar): **Demo** (sintetis), **Instaloader** (tidak resmi, perlu login, lambat & berisiko diblokir),
atau **CSV** (kolom `username` wajib).

## Cara kerja & batasan
| Output | Metode | Catatan |
|---|---|---|
| Skor bot | Aturan berbobot (foto, postingan, rasio follow, username acak, bio spam, verifikasi) | Indikator, bukan bukti |
| Usia akun | Interpolasi dari user ID | Perkiraan kasar (±1 th) |
| Masa follow | Posisi di daftar follower (terbaru dulu) | Proxy, bukan tanggal follow |
| Gender | Tebakan nama depan | Banyak "Tidak diketahui" |
| Lokasi | Kota/negara di bio, kode telepon, bahasa | Hanya sebagian follower |

Umur tidak bisa disimpulkan dari data publik. Untuk demografi akurat milik akun bisnis sendiri, pakai Instagram
Insights / Graph API. Gunakan hanya dengan izin dan hormati ToS Instagram serta privasi follower.
