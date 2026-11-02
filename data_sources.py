"""Sumber data follower: demo (sintetis), Instaloader (tidak resmi), atau CSV."""
from __future__ import annotations

import random
import string
import time

import numpy as np
import pandas as pd

DEFAULT_PIC_MARKER = "44884218_345707102882519_2446069589734326272_n"


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------
_FIRST = ["Budi", "Siti", "Agus", "Dewi", "Rizky", "Putri", "Andi", "Nur", "Fajar", "Ayu", "Dimas",
          "Rina", "Yusuf", "Intan", "Reza", "Maya", "Wahyu", "Citra", "Ilham", "Nabila", "John",
          "Emma", "Ahmad", "Lim", "Sarah", "Michael"]
_LAST = ["Pratama", "Santoso", "Wijaya", "Lestari", "Hidayat", "Saputra", "Kusuma", "Nugroho",
         "Rahma", "Smith", "Tan", "Abdullah", "Putra"]
_CITIES = ["Jakarta", "Bandung", "Surabaya", "Yogyakarta", "Medan", "Makassar", "Denpasar", "Semarang",
           "Malang", "Palembang", "Bekasi", "Depok", "Kuala Lumpur", "Singapore", "Balikpapan"]
_BIO_REAL = ["Suka kopi dan jalan-jalan ☕ {c}", "Mahasiswa | {c} | cinta musik", "Living my best life 📸 {c}",
             "Ibu dua anak, hidup sehat dan bahagia", "Pemilik toko online murah dan asli",
             "Photographer | travel lover | {c}", "Dev & gamer 🎮", "Jangan lupa bahagia ya", ""]
_BIO_BOT = ["", "", "", "DM for promo 🔥", "click link in bio 18+", "slot gacor cuan banget", "f4f follow back",
            "Jasa follower murah", "crypto forex trading signals"]


def _id_for_year(year: float, rng: random.Random) -> int:
    from profiler import _ID_ANCHORS
    xs = np.log10([a for a, _ in _ID_ANCHORS])
    ys = np.array([b for _, b in _ID_ANCHORS])
    return int(10 ** (np.interp(year, ys, xs) + rng.uniform(-0.08, 0.08)))


def demo_followers(username: str, n: int = 500, seed: int | None = None) -> pd.DataFrame:
    rng = random.Random(seed if seed is not None else hash(username) % 10_000)
    rows = []
    for i in range(n):
        kind = rng.choices(["real", "casual", "suspicious", "bot"], [0.52, 0.18, 0.12, 0.18])[0]
        if kind in ("real", "casual"):
            fn, ln = rng.choice(_FIRST), rng.choice(_LAST)
            uname = rng.choice([f"{fn}.{ln}", f"{fn}{ln}{rng.randint(1, 99)}", f"{fn.lower()}_{ln.lower()}"]).lower()
            year = rng.triangular(2012, 2025.3, 2020)
            real = kind == "real"
            rows.append(dict(
                username=uname, user_id=_id_for_year(year, rng), full_name=f"{fn} {ln}",
                biography=rng.choice(_BIO_REAL).format(c=rng.choice(_CITIES)) if real or rng.random() < .4 else "",
                is_private=rng.random() < (0.35 if real else 0.5), is_verified=rng.random() < 0.004,
                is_business=rng.random() < 0.06, has_profile_pic=rng.random() < (0.98 if real else 0.8),
                followers=int(rng.lognormvariate(5.6 if real else 4.5, 1.4)),
                following=int(rng.lognormvariate(5.7, 0.8)),
                posts=int(rng.lognormvariate(3.4 if real else 1.3, 1.1)),
            ))
        else:
            bot = kind == "bot"
            uname = "".join(rng.choices(string.ascii_lowercase, k=rng.randint(5, 9))) + str(rng.randint(10000, 9999999))
            year = rng.triangular(2021, 2025.3, 2024.5) if bot else rng.triangular(2016, 2025, 2022)
            rows.append(dict(
                username=uname, user_id=_id_for_year(year, rng),
                full_name="" if bot and rng.random() < .6 else rng.choice(_FIRST),
                biography=rng.choice(_BIO_BOT), is_private=rng.random() < 0.3, is_verified=False,
                is_business=False, has_profile_pic=rng.random() < (0.35 if bot else 0.7),
                followers=int(rng.lognormvariate(1.5, 1.0)),
                following=int(rng.lognormvariate(7.2 if bot else 5.5, 0.5)),
                posts=0 if rng.random() < (0.7 if bot else 0.3) else rng.randint(1, 6),
            ))
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Instaloader (tidak resmi; berisiko diblokir Instagram)
# ---------------------------------------------------------------------------
def _verify_session(L) -> str:
    """Cek cookie lewat endpoint web terbaru; kembalikan username akun yang login."""
    sess = L.context._session
    try:
        r = sess.get("https://www.instagram.com/api/v1/accounts/current_user/?edit=true",
                     headers={"X-IG-App-ID": "936619743392459", "X-Requested-With": "XMLHttpRequest",
                              "Referer": "https://www.instagram.com/"})
    except Exception as e:  # noqa: BLE001
        raise ValueError(f"Tidak bisa menghubungi Instagram: {e}") from e
    if r.status_code == 200:
        try:
            return r.json()["user"]["username"]
        except Exception:  # noqa: BLE001
            pass
    # cadangan: pengecekan bawaan Instaloader
    who = L.test_login()
    if who:
        return who
    hint = {401: "cookie ditolak/kedaluwarsa", 403: "diblokir (coba ganti jaringan, matikan VPN)",
            429: "terlalu banyak permintaan, tunggu beberapa menit"}.get(r.status_code, "respons tak dikenal")
    raise ValueError(f"Instagram membalas HTTP {r.status_code} ({hint}). Pastikan yang disalin adalah nilai "
                     "cookie 'sessionid' dari akun yang sedang login, tanpa spasi.")


def instaloader_followers(username: str, max_n: int, login_user: str, password: str,
                          delay: float = 2.0, progress=None, twofa_code: str = "",
                          sessionid: str = "", csrftoken: str = ""):
    """Ambil follower. Perlu login. Mengembalikan (target_info, DataFrame)."""
    import instaloader

    L = instaloader.Instaloader(quiet=True, download_pictures=False, download_videos=False,
                                download_video_thumbnails=False, save_metadata=False,
                                compress_json=False, post_metadata_txt_pattern="")
    if sessionid.strip():
        # Login lewat browser biasa, lalu pakai cookie sessionid-nya (menghindari deteksi bot saat login)
        sid = sessionid.strip().strip('"\'')
        L.load_session(login_user or "", {"sessionid": sid, "csrftoken": csrftoken.strip().strip('"\'')})
        login_user = _verify_session(L)
    elif login_user:
        try:
            L.load_session_from_file(login_user)
        except FileNotFoundError:
            if not password:
                raise ValueError("Sesi tersimpan tidak ditemukan; isi password untuk login.")
            try:
                L.login(login_user, password)
            except instaloader.TwoFactorAuthRequiredException:
                code = (twofa_code or "").strip().replace(" ", "")
                if not code:
                    raise ValueError("Akun memakai 2FA: isi 'Kode 2FA' dari aplikasi autentikator, "
                                     "lalu klik Analisis lagi.")
                L.two_factor_login(code)
            L.save_session_to_file()
    else:
        raise ValueError("Instagram mewajibkan login untuk membaca daftar follower.")

    target = instaloader.Profile.from_username(L.context, username)
    info = dict(username=target.username, full_name=target.full_name, followers=target.followers,
                following=target.followees, posts=target.mediacount, biography=target.biography,
                is_private=target.is_private, is_verified=target.is_verified)
    if target.is_private and login_user.lower() != username.lower() and not target.followed_by_viewer:
        raise PermissionError("Akun privat dan akun login Anda tidak mengikutinya.")

    rows = []
    for i, f in enumerate(target.get_followers()):
        if i >= max_n:
            break
        try:
            rows.append(dict(
                username=f.username, user_id=f.userid, full_name=f.full_name, biography=f.biography,
                is_private=f.is_private, is_verified=f.is_verified, is_business=f.is_business_account,
                has_profile_pic=DEFAULT_PIC_MARKER not in (f.profile_pic_url or ""),
                followers=f.followers, following=f.followees, posts=f.mediacount,
            ))
        except Exception:  # satu profil gagal tidak menghentikan proses
            rows.append(dict(username=f.username, user_id=f.userid, full_name=f.full_name))
        if progress:
            progress(min((i + 1) / max_n, 1.0), f"{i + 1}/{max_n} follower diambil")
        time.sleep(delay)
    return info, pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# CSV
# ---------------------------------------------------------------------------
def csv_followers(file) -> pd.DataFrame:
    df = pd.read_csv(file)
    df.columns = [c.strip().lower() for c in df.columns]
    if "username" not in df:
        raise ValueError("CSV harus punya kolom 'username'.")
    return df
