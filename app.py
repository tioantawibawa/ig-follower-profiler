import re

import numpy as np
import pandas as pd
import plotly.express as px
import streamlit as st

import data_sources as ds
from profiler import profile_followers

st.set_page_config(page_title="IG Follower Profiler", page_icon="📊", layout="wide")

COLORS = {"Asli": "#2a9d8f", "Mencurigakan": "#e9c46a", "Kemungkinan Bot": "#e76f51"}
ORDER = ["Asli", "Mencurigakan", "Kemungkinan Bot"]
AGE_ORDER = ["< 1 th", "1–3 th", "3–6 th", "> 6 th", "Tidak diketahui"]


def style(fig, h=340):
    fig.update_layout(height=h, margin=dict(l=10, r=10, t=40, b=10), legend_title_text="")
    return fig


def pct(n, d):
    return f"{(n / d * 100):.1f}%" if d else "–"


# ---------------------------------------------------------------- sidebar
with st.sidebar:
    st.title("📊 IG Follower Profiler")
    username = st.text_input("Akun Instagram", placeholder="contoh: natgeo").strip().lstrip("@")
    source = st.radio("Sumber data", ["Demo (data sintetis)", "Instaloader (tidak resmi)", "Upload CSV"])

    max_n, delay, newest_first = 300, 2.0, True
    login_user = password = twofa = ""
    csv_file = None
    if source.startswith("Demo"):
        max_n = st.slider("Jumlah follower sintetis", 100, 2000, 500, 100)
    elif source.startswith("Instaloader"):
        max_n = st.slider("Maks. follower diambil", 50, 2000, 300, 50)
        delay = st.slider("Jeda per profil (detik)", 1.0, 10.0, 3.0, 0.5,
                          help="Jeda lebih besar = lebih kecil risiko akun login diblokir.")
        login_user = st.text_input("Username login IG").strip()
        password = st.text_input("Password (tidak disimpan)", type="password")
        twofa = st.text_input("Kode 2FA (jika akun memakai 2FA)", max_chars=8,
                              help="Kode 6 digit dari aplikasi autentikator; isi sebelum klik Analisis "
                                   "(kode berlaku ±30 detik). Sesi disimpan sehingga berikutnya tidak perlu lagi.")
        st.caption("Gunakan akun cadangan. Login 2FA: buat sesi dulu lewat `instaloader --login=USER`.")
    else:
        csv_file = st.file_uploader("CSV follower", type="csv")
        newest_first = st.checkbox("Urutan baris = follower terbaru dulu", True)
        st.caption("Kolom: username (wajib), user_id, full_name, biography, is_private, is_verified, "
                   "is_business, has_profile_pic, followers, following, posts.")
    go = st.button("🔍 Analisis", type="primary", width="stretch")
    with st.expander("⚠️ Batasan & etika"):
        st.markdown(
            "- Instagram **tidak** menyediakan tanggal follow, lokasi, gender, atau umur follower. "
            "Semua itu **perkiraan heuristik**.\n"
            "- Pengambilan data via scraping melanggar ToS Instagram dan bisa memblokir akun. "
            "Gunakan hanya untuk akun Anda / dengan izin, dan jangan menyebarkan data pribadi follower.\n"
            "- Untuk akun bisnis sendiri, demografi resmi (usia, gender, kota) ada di Instagram Insights / Graph API."
        )

# ---------------------------------------------------------------- load
if go:
    if source.startswith("Demo") or source.startswith("Instaloader"):
        if not username:
            st.sidebar.error("Isi username akun terlebih dahulu.")
            st.stop()
    try:
        if source.startswith("Demo"):
            raw, target = ds.demo_followers(username, max_n), {"username": username, "demo": True}
        elif source.startswith("Instaloader"):
            bar = st.progress(0.0, "Menghubungkan ke Instagram…")
            target, raw = ds.instaloader_followers(username, max_n, login_user, password, delay,
                                                   lambda p, t: bar.progress(p, t), twofa)
            bar.empty()
        else:
            if csv_file is None:
                st.sidebar.error("Upload file CSV dulu.")
                st.stop()
            raw, target = ds.csv_followers(csv_file), {"username": username or "(CSV)"}
        if raw.empty:
            st.error("Tidak ada follower yang berhasil diambil.")
            st.stop()
        st.session_state["df"] = profile_followers(raw, newest_first)
        st.session_state["target"] = target
    except Exception as e:  # noqa: BLE001 — tampilkan semua galat ke pengguna
        st.error(f"Gagal mengambil data: {e}")
        st.stop()

if "df" not in st.session_state:
    st.title("Profiling follower Instagram")
    st.info("Masukkan akun Instagram di sidebar, pilih sumber data, lalu klik **Analisis**. "
            "Coba mode **Demo** untuk melihat tampilan dashboard.")
    st.stop()

df: pd.DataFrame = st.session_state["df"]
target: dict = st.session_state["target"]
n = len(df)

# ---------------------------------------------------------------- header
st.title(f"@{target.get('username', '')}")
if target.get("demo"):
    st.warning("Mode demo: data sintetis, bukan akun nyata.")
elif target.get("followers"):
    st.caption(f"{target['full_name']} · {target['followers']:,} follower · {target['posts']:,} post "
               f"· sampel dianalisis: {n:,} ({pct(n, target['followers'])} dari total)")

counts = df["kelas"].value_counts()
k = st.columns(5)
k[0].metric("Sampel", f"{n:,}")
k[1].metric("Asli", pct(counts.get("Asli", 0), n))
k[2].metric("Mencurigakan", pct(counts.get("Mencurigakan", 0), n))
k[3].metric("Kemungkinan Bot", pct(counts.get("Kemungkinan Bot", 0), n))
med = df["usia_akun_thn"].median()
k[4].metric("Median usia akun", f"{med:.1f} th" if pd.notna(med) else "–")

tabs = st.tabs(["Keaslian", "Lama vs Baru", "Demografi", "Geografi", "Data & Ekspor"])

# ---------------------------------------------------------------- keaslian
with tabs[0]:
    a, b = st.columns(2)
    fig = px.pie(df, names="kelas", hole=0.55, color="kelas", color_discrete_map=COLORS,
                 category_orders={"kelas": ORDER}, title="Komposisi follower")
    a.plotly_chart(style(fig), width="stretch")
    fig = px.histogram(df, x="skor_bot", nbins=20, color="kelas", color_discrete_map=COLORS,
                       category_orders={"kelas": ORDER}, title="Distribusi skor bot (0–100)")
    b.plotly_chart(style(fig), width="stretch")

    c, d = st.columns(2)
    reasons = df["alasan_flag"].explode().dropna().value_counts().head(10).reset_index()
    reasons.columns = ["alasan", "jumlah"]
    fig = px.bar(reasons.iloc[::-1], x="jumlah", y="alasan", orientation="h",
                 title="Sinyal yang paling sering memicu kecurigaan")
    fig.update_traces(marker_color="#e76f51")
    c.plotly_chart(style(fig), width="stretch")
    fig = px.scatter(df, x="followers", y="following", color="kelas", color_discrete_map=COLORS,
                     log_x=True, log_y=True, hover_name="username", opacity=0.7,
                     category_orders={"kelas": ORDER}, title="Follower vs following (skala log)")
    d.plotly_chart(style(fig), width="stretch")
    st.caption("Skor bot = penjumlahan sinyal (tanpa foto, tanpa postingan, rasio following ekstrem, "
               "username acak, bio spam, dll.). Ini indikator, bukan bukti; akun asli yang pasif bisa terlihat mencurigakan.")

# ---------------------------------------------------------------- lama vs baru
with tabs[1]:
    st.markdown("**Dua sudut pandang:** (1) *usia akun* — diperkirakan dari rentang user ID; "
                "(2) *masa follow* — dari urutan daftar follower (Instagram menampilkan yang terbaru lebih dulu).")
    a, b = st.columns(2)
    yr = df.dropna(subset=["tahun_dibuat"]).assign(tahun=lambda x: x["tahun_dibuat"].astype(int))
    fig = px.histogram(yr, x="tahun", color="kelas", color_discrete_map=COLORS, barmode="stack",
                       category_orders={"kelas": ORDER}, title="Perkiraan tahun akun dibuat")
    a.plotly_chart(style(fig), width="stretch")
    ct = df.groupby(["masa_follow", "kelas"]).size().reset_index(name="jumlah")
    fig = px.bar(ct, x="masa_follow", y="jumlah", color="kelas", color_discrete_map=COLORS,
                 category_orders={"masa_follow": ["Baru", "Menengah", "Lama"], "kelas": ORDER},
                 title="Masa follow × keaslian")
    b.plotly_chart(style(fig), width="stretch")

    c, d = st.columns(2)
    fig = px.bar(df["kelompok_usia_akun"].value_counts().reindex(AGE_ORDER).dropna().reset_index(),
                 x="kelompok_usia_akun", y="count", title="Kelompok usia akun")
    c.plotly_chart(style(fig), width="stretch")
    new_bot = df[(df["tahun_dibuat"] >= 2024) & (df["kelas"] != "Asli")]
    d.metric("Akun baru (≥2024) yang mencurigakan/bot", len(new_bot),
             help="Lonjakan akun baru mencurigakan sering menandakan follower dibeli atau serangan spam.")
    old_real = df[(df["usia_akun_thn"] > 6) & (df["kelas"] == "Asli")]
    d.metric("Follower asli berusia akun > 6 tahun", len(old_real))

# ---------------------------------------------------------------- demografi
with tabs[2]:
    a, b, c = st.columns(3)
    for col, field, title in [(a, "gender_tebakan", "Gender (tebakan dari nama)"),
                              (b, "bahasa", "Bahasa bio/nama"),
                              (c, "tipe_akun", "Tipe akun")]:
        vc = df[field].value_counts().reset_index()
        fig = px.pie(vc, names=field, values="count", hole=0.5, title=title)
        col.plotly_chart(style(fig, 320), width="stretch")
    a, b = st.columns(2)
    fig = px.pie(df, names="status_privasi", hole=0.5, title="Akun privat vs publik")
    a.plotly_chart(style(fig, 300), width="stretch")
    bins = pd.cut(df["followers"], [-1, 99, 499, 999, 9999, 10**9],
                  labels=["<100", "100–499", "500–999", "1K–10K", ">10K"]).value_counts().sort_index().reset_index()
    fig = px.bar(bins, x="followers", y="count", title="Jumlah follower milik follower")
    b.plotly_chart(style(fig, 300), width="stretch")
    st.caption("Gender hanya tebakan berbasis nama depan; banyak yang 'Tidak diketahui'. Usia tidak dapat disimpulkan dari data publik.")

# ---------------------------------------------------------------- geografi
with tabs[3]:
    known = df[df["negara"] != "Tidak diketahui"]
    st.metric("Follower dengan petunjuk lokasi", pct(len(known), n),
              help="Lokasi hanya terdeteksi bila bio/nama menyebut kota/negara atau bahasa jelas.")
    if known.empty:
        st.info("Tidak ada petunjuk lokasi yang terdeteksi pada sampel ini.")
    else:
        a, b = st.columns(2)
        vc = known["negara"].value_counts().reset_index()
        fig = px.bar(vc, x="count", y="negara", orientation="h", title="Negara")
        fig.update_yaxes(autorange="reversed")
        a.plotly_chart(style(fig), width="stretch")
        cities = known[known["kota"] != "—"]["kota"].value_counts().head(15).reset_index()
        if not cities.empty:
            fig = px.bar(cities, x="count", y="kota", orientation="h", title="Kota teratas")
            fig.update_yaxes(autorange="reversed")
            b.plotly_chart(style(fig), width="stretch")
        g = (known.dropna(subset=["lat"]).groupby(["kota", "negara", "lat", "lon"]).size()
             .reset_index(name="jumlah"))
        fig = px.scatter_geo(g, lat="lat", lon="lon", size="jumlah", hover_name="kota",
                             hover_data=["negara", "jumlah"], projection="natural earth",
                             title="Peta sebaran (titik = kota atau pusat negara)")
        st.plotly_chart(style(fig, 480), width="stretch")
        prov = known[known["provinsi"] != "—"]["provinsi"].value_counts().head(10).reset_index()
        if not prov.empty:
            st.dataframe(prov.rename(columns={"provinsi": "Provinsi", "count": "Jumlah"}),
                         hide_index=True, width="stretch")

# ---------------------------------------------------------------- data
with tabs[4]:
    f1, f2, f3 = st.columns(3)
    kelas_f = f1.multiselect("Kelas", ORDER, default=ORDER)
    masa_f = f2.multiselect("Masa follow", ["Baru", "Menengah", "Lama"], default=["Baru", "Menengah", "Lama"])
    q = f3.text_input("Cari username/nama")
    view = df[df["kelas"].isin(kelas_f) & df["masa_follow"].isin(masa_f)]
    if q:
        pat = re.escape(q)
        view = view[view["username"].str.contains(pat, case=False) | view["full_name"].str.contains(pat, case=False)]
    cols = ["urutan_follow", "username", "full_name", "kelas", "skor_bot", "masa_follow", "tahun_dibuat",
            "tipe_akun", "gender_tebakan", "bahasa", "negara", "kota", "followers", "following", "posts"]
    show = view[cols].copy()
    show["alasan"] = view["alasan_flag"].map(lambda r: "; ".join(r))
    show["tahun_dibuat"] = show["tahun_dibuat"].round(1)
    st.dataframe(show, hide_index=True, width="stretch", height=420)
    st.download_button("⬇️ Unduh CSV", show.to_csv(index=False).encode("utf-8"),
                       f"follower_profile_{target.get('username', 'akun')}.csv", "text/csv")
