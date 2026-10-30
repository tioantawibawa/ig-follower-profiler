"""Logika profiling follower: skor bot, estimasi usia akun, bahasa, gender, dan lokasi.

Semua hasil bersifat HEURISTIK (perkiraan), bukan fakta. Instagram tidak
mempublikasikan tanggal follow, lokasi, gender, atau umur follower.
"""
from __future__ import annotations

import math
import re
from datetime import datetime

import numpy as np
import pandas as pd

try:
    import gender_guesser.detector as _gg

    _GG = _gg.Detector(case_sensitive=False)
except Exception:  # library opsional
    _GG = None

# ---------------------------------------------------------------------------
# Estimasi usia akun dari user ID (ID Instagram naik kira-kira berurutan)
# Titik jangkar kasar (ID, tahun desimal). Interpolasi di skala log.
# ---------------------------------------------------------------------------
_ID_ANCHORS = [
    (1e6, 2010.9), (1e7, 2011.6), (1e8, 2012.9), (5e8, 2014.0), (1e9, 2014.8),
    (2e9, 2015.6), (5e9, 2016.9), (1e10, 2018.0), (2e10, 2019.2), (4e10, 2020.6),
    (5.5e10, 2022.0), (7e10, 2023.5), (9e10, 2025.0),
]
_LOG_IDS = np.log10([a for a, _ in _ID_ANCHORS])
_YEARS = np.array([b for _, b in _ID_ANCHORS])


def estimate_creation_year(user_id) -> float:
    try:
        uid = float(user_id)
    except (TypeError, ValueError):
        return float("nan")
    if not uid or uid <= 0 or math.isnan(uid):
        return float("nan")
    return float(np.interp(math.log10(uid), _LOG_IDS, _YEARS))


# ---------------------------------------------------------------------------
# Skor bot
# ---------------------------------------------------------------------------
_SPAM_WORDS = re.compile(
    r"\b(f4f|follow ?back|followback|l4l|dm (me )?for|promo|slot|gacor|judi|togel|"
    r"cuan|crypto|forex|trading|onlyfans|18\+|sugar|jasa follower|jual follower|"
    r"giveaway|win(ner)?|click (the )?link|link in bio)\b",
    re.I,
)
_VOWELS = set("aeiouAEIOU")


def _username_suspicion(username: str) -> tuple[int, str | None]:
    u = username or ""
    if not u:
        return 0, None
    digits = sum(c.isdigit() for c in u)
    longest_digit_run = max((len(m) for m in re.findall(r"\d+", u)), default=0)
    consonant_run = max((len(m) for m in re.findall(r"[^aeiou\d._]+", u.lower())), default=0)
    pts = 0
    if digits / len(u) > 0.4 or longest_digit_run >= 6:
        pts += 12
    elif longest_digit_run >= 4:
        pts += 6
    if consonant_run >= 6:
        pts += 6
    return pts, ("Username acak / banyak angka" if pts >= 6 else None)


def score_bot(row: pd.Series) -> tuple[int, list[str]]:
    """Skor 0-100: makin tinggi makin mirip akun bot / spam."""
    s, why = 0, []

    def add(points, reason):
        nonlocal s
        s += points
        why.append(reason)

    posts = row.get("posts") or 0
    followers = row.get("followers") or 0
    following = row.get("following") or 0
    bio = (row.get("biography") or "").strip()
    name = (row.get("full_name") or "").strip()

    if not row.get("has_profile_pic", True):
        add(20, "Tanpa foto profil")
    if posts == 0:
        add(20, "Belum pernah posting")
    elif posts < 3:
        add(8, "Postingan sangat sedikit")
    if following >= 1500 and followers / max(following, 1) < 0.1:
        add(20, "Following sangat banyak, follower sedikit")
    elif followers < 10 and following > 500:
        add(10, "Follower <10 tapi following >500")
    if not bio:
        add(8, "Bio kosong")
    if not name:
        add(8, "Nama lengkap kosong")
    pts, reason = _username_suspicion(row.get("username", ""))
    if reason:
        add(pts, reason)
    if bio and _SPAM_WORDS.search(bio):
        add(20, "Bio berisi kata kunci spam/promo")

    # sinyal akun asli (mengurangi skor)
    if row.get("is_verified"):
        s -= 50
    if posts >= 20 and followers >= 100:
        s -= 15
    if bio and name and row.get("has_profile_pic", True):
        s -= 10
    return int(max(0, min(100, s))), why


def classify(score: float) -> str:
    if score >= 55:
        return "Kemungkinan Bot"
    if score >= 30:
        return "Mencurigakan"
    return "Asli"


def account_type(r: pd.Series) -> str:
    if r.get("is_business"):
        return "Bisnis/Kreator"
    f = r.get("followers") or 0
    if f >= 10_000:
        return "Influencer (≥10K)"
    if f >= 1_000:
        return "Mikro-influencer (1K–10K)"
    return "Personal (<1K)"


# ---------------------------------------------------------------------------
# Bahasa, gender, lokasi
# ---------------------------------------------------------------------------
_ID_WORDS = set("yang dan di ke dari untuk dengan ini itu aku saya kamu gue lo ga gak nggak "
                "jangan suka cinta hidup jual beli kita kami anak bapak ibu mama papa "
                "pemilik toko online murah asli sehat bahagia".split())
_EN_WORDS = set("the and of to in for with my your love life lover living official "
                "shop store owner photographer travel just not you are is".split())
_MS_WORDS = set("saya awak kami dengan untuk adalah tidak boleh nak jom kedai".split())


def detect_language(text: str) -> str:
    t = (text or "").strip()
    if len(t) < 3:
        return "Tidak diketahui"
    if re.search(r"[一-鿿]", t):
        return "Mandarin/CJK"
    if re.search(r"[぀-ヿ가-힯]", t):
        return "Jepang/Korea"
    if re.search(r"[؀-ۿ]", t):
        return "Arab"
    if re.search(r"[Ѐ-ӿ]", t):
        return "Rusia/Sirilik"
    if re.search(r"[ऀ-ॿ]", t):
        return "India (Devanagari)"
    words = set(re.findall(r"[a-zA-Z']+", t.lower()))
    scores = {"Indonesia": len(words & _ID_WORDS), "Inggris": len(words & _EN_WORDS),
              "Melayu": len(words & _MS_WORDS)}
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "Tidak diketahui"


_ID_MALE = set("budi agus andi dedi eko joko bayu rizky rizki fajar dimas hendra arief ahmad "
               "muhammad muhamad yusuf ilham reza rendy rian wahyu bambang adi putra fauzan "
               "ridwan irfan hadi iwan teguh doni dian_m dika galih dwi_m aldi aditya".split())
_ID_FEMALE = set("siti sri dewi ayu putri nur nurul fitri rina rani indah lestari wulan ratna "
                 "sari yuni novi maya anisa annisa aisyah dina tiara nabila intan citra "
                 "melati rahma diah lia eka_f mega salsa sinta vina astri".split())


def guess_gender(full_name: str) -> str:
    first = re.sub(r"[^a-zA-Z ]", " ", full_name or "").strip().split(" ")[0].lower()
    if len(first) < 3:
        return "Tidak diketahui"
    if first in _ID_MALE:
        return "Pria"
    if first in _ID_FEMALE:
        return "Wanita"
    if _GG is not None:
        g = _GG.get_gender(first.capitalize())
        if g in ("male", "mostly_male"):
            return "Pria"
        if g in ("female", "mostly_female"):
            return "Wanita"
    return "Tidak diketahui"


# nama tempat -> (kota, provinsi/negara bagian, negara, lat, lon)
_ID = "Indonesia"
_PLACES = {
    "jakarta": ("Jakarta", "DKI Jakarta", _ID, -6.2, 106.82),
    "bogor": ("Bogor", "Jawa Barat", _ID, -6.6, 106.8),
    "depok": ("Depok", "Jawa Barat", _ID, -6.4, 106.82),
    "tangerang": ("Tangerang", "Banten", _ID, -6.17, 106.63),
    "bekasi": ("Bekasi", "Jawa Barat", _ID, -6.24, 106.99),
    "bandung": ("Bandung", "Jawa Barat", _ID, -6.92, 107.61),
    "cirebon": ("Cirebon", "Jawa Barat", _ID, -6.73, 108.55),
    "semarang": ("Semarang", "Jawa Tengah", _ID, -6.97, 110.42),
    "solo": ("Surakarta", "Jawa Tengah", _ID, -7.57, 110.82),
    "surakarta": ("Surakarta", "Jawa Tengah", _ID, -7.57, 110.82),
    "yogyakarta": ("Yogyakarta", "DI Yogyakarta", _ID, -7.8, 110.36),
    "jogja": ("Yogyakarta", "DI Yogyakarta", _ID, -7.8, 110.36),
    "surabaya": ("Surabaya", "Jawa Timur", _ID, -7.25, 112.75),
    "malang": ("Malang", "Jawa Timur", _ID, -7.98, 112.63),
    "denpasar": ("Denpasar", "Bali", _ID, -8.65, 115.22),
    "bali": ("Denpasar", "Bali", _ID, -8.65, 115.22),
    "medan": ("Medan", "Sumatera Utara", _ID, 3.59, 98.67),
    "palembang": ("Palembang", "Sumatera Selatan", _ID, -2.98, 104.75),
    "padang": ("Padang", "Sumatera Barat", _ID, -0.95, 100.35),
    "pekanbaru": ("Pekanbaru", "Riau", _ID, 0.51, 101.45),
    "batam": ("Batam", "Kepulauan Riau", _ID, 1.05, 104.03),
    "lampung": ("Bandar Lampung", "Lampung", _ID, -5.43, 105.26),
    "banjarmasin": ("Banjarmasin", "Kalimantan Selatan", _ID, -3.32, 114.59),
    "balikpapan": ("Balikpapan", "Kalimantan Timur", _ID, -1.24, 116.83),
    "pontianak": ("Pontianak", "Kalimantan Barat", _ID, -0.03, 109.33),
    "makassar": ("Makassar", "Sulawesi Selatan", _ID, -5.15, 119.43),
    "manado": ("Manado", "Sulawesi Utara", _ID, 1.47, 124.84),
    "jayapura": ("Jayapura", "Papua", _ID, -2.53, 140.72),
    "kuala lumpur": ("Kuala Lumpur", "KL", "Malaysia", 3.14, 101.69),
    "johor": ("Johor Bahru", "Johor", "Malaysia", 1.49, 103.74),
    "singapore": ("Singapore", "SG", "Singapura", 1.35, 103.82),
    "singapura": ("Singapore", "SG", "Singapura", 1.35, 103.82),
    "bangkok": ("Bangkok", "BKK", "Thailand", 13.76, 100.5),
    "manila": ("Manila", "NCR", "Filipina", 14.6, 120.98),
    "tokyo": ("Tokyo", "Tokyo", "Jepang", 35.68, 139.69),
    "seoul": ("Seoul", "Seoul", "Korea Selatan", 37.57, 126.98),
    "dubai": ("Dubai", "Dubai", "UEA", 25.2, 55.27),
    "london": ("London", "England", "Inggris", 51.51, -0.13),
    "new york": ("New York", "NY", "Amerika Serikat", 40.71, -74.0),
    "los angeles": ("Los Angeles", "CA", "Amerika Serikat", 34.05, -118.24),
    "sydney": ("Sydney", "NSW", "Australia", -33.87, 151.21),
    "melbourne": ("Melbourne", "VIC", "Australia", -37.81, 144.96),
    "india": ("—", "—", "India", 20.59, 78.96),
}
_PLACE_RE = re.compile(
    r"\b(" + "|".join(sorted((re.escape(k) for k in _PLACES), key=len, reverse=True)) + r")\b",
    re.I,
)
_COUNTRY_HINTS = [
    (re.compile(r"🇮🇩|indonesia|\+62\b|\bwa ?08\d"), "Indonesia"),
    (re.compile(r"🇲🇾|malaysia|\+60\b"), "Malaysia"),
    (re.compile(r"🇸🇬|\+65\b"), "Singapura"),
    (re.compile(r"🇺🇸|\busa\b|\+1\b"), "Amerika Serikat"),
    (re.compile(r"🇮🇳|\+91\b"), "India"),
    (re.compile(r"🇵🇭|\+63\b"), "Filipina"),
]
_COUNTRY_CENTER = {"Indonesia": (-2.5, 118.0), "Malaysia": (4.2, 102.0), "Singapura": (1.35, 103.82),
                   "Amerika Serikat": (39.8, -98.6), "India": (20.6, 78.9), "Filipina": (12.9, 121.8)}


def infer_location(text: str, language: str = "Tidak diketahui") -> dict:
    """Cari petunjuk lokasi di bio/nama. Bukan lokasi sebenarnya."""
    blob = text or ""
    m = _PLACE_RE.search(blob)
    if m:
        city, prov, country, lat, lon = _PLACES[m.group(1).lower()]
        return dict(kota=city, provinsi=prov, negara=country, lat=lat, lon=lon, sumber_lokasi="Teks bio")
    low = blob.lower()
    for rx, country in _COUNTRY_HINTS:
        if rx.search(low):
            lat, lon = _COUNTRY_CENTER[country]
            return dict(kota="—", provinsi="—", negara=country, lat=lat, lon=lon, sumber_lokasi="Teks bio")
    lang_country = {"Indonesia": "Indonesia (perkiraan bahasa)", "Melayu": "Malaysia (perkiraan bahasa)"}
    if language in lang_country:
        c = lang_country[language].split(" (")[0]
        lat, lon = _COUNTRY_CENTER[c]
        return dict(kota="—", provinsi="—", negara=c, lat=lat, lon=lon, sumber_lokasi="Bahasa bio")
    return dict(kota="—", provinsi="—", negara="Tidak diketahui", lat=np.nan, lon=np.nan,
                sumber_lokasi="—")


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------
REQUIRED_COLS = ["username", "user_id", "full_name", "biography", "is_private", "is_verified",
                 "is_business", "has_profile_pic", "followers", "following", "posts"]


def profile_followers(df: pd.DataFrame, newest_first: bool = True) -> pd.DataFrame:
    """Tambahkan kolom hasil profiling. `df` urut sesuai urutan daftar follower."""
    d = df.copy()
    for c in REQUIRED_COLS:
        if c not in d:
            d[c] = np.nan if c in ("user_id",) else (0 if c in ("followers", "following", "posts") else "")
    for c in ("full_name", "biography", "username"):
        d[c] = d[c].fillna("").astype(str)
    for c in ("is_private", "is_verified", "is_business"):
        d[c] = d[c].fillna(False).astype(bool)
    d["has_profile_pic"] = d["has_profile_pic"].fillna(True).astype(bool)
    for c in ("followers", "following", "posts"):
        d[c] = pd.to_numeric(d[c], errors="coerce").fillna(0).astype(int)
    d["user_id"] = pd.to_numeric(d["user_id"], errors="coerce")

    res = d.apply(score_bot, axis=1, result_type="reduce")
    d["skor_bot"] = [r[0] for r in res]
    d["alasan_flag"] = [r[1] for r in res]
    d["kelas"] = d["skor_bot"].map(classify)
    d["tipe_akun"] = d.apply(account_type, axis=1)

    # usia akun
    d["tahun_dibuat"] = d["user_id"].map(estimate_creation_year)
    now = datetime.now().year + datetime.now().timetuple().tm_yday / 365
    d["usia_akun_thn"] = (now - d["tahun_dibuat"]).clip(lower=0)
    d["kelompok_usia_akun"] = pd.cut(
        d["usia_akun_thn"], [-0.1, 1, 3, 6, 100],
        labels=["< 1 th", "1–3 th", "3–6 th", "> 6 th"],
    ).astype(object).where(d["usia_akun_thn"].notna(), "Tidak diketahui")

    # masa follow (proxy dari urutan daftar): ~1/3 terakhir = paling lama
    n = len(d)
    rank = np.arange(n)
    pos = rank / max(n - 1, 1)  # 0 = paling atas
    if not newest_first:
        pos = 1 - pos
    d["urutan_follow"] = rank + 1
    d["masa_follow"] = np.select([pos < 1 / 3, pos < 2 / 3], ["Baru", "Menengah"], "Lama")

    # demografi
    text = (d["full_name"] + " " + d["biography"])
    d["bahasa"] = text.map(detect_language)
    d["gender_tebakan"] = d["full_name"].map(guess_gender)
    loc = pd.DataFrame([infer_location(t, l) for t, l in zip(text, d["bahasa"])], index=d.index)
    d = pd.concat([d, loc], axis=1)
    d["status_privasi"] = np.where(d["is_private"], "Privat", "Publik")
    return d
