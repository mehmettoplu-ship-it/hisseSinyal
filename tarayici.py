#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BIST Teknik Analiz Motoru
RSI, MACD, Bollinger, Stokastik, Momentum + Destek/Direnç Filtresi
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')

# ────────────────────────────────────────────
# BIST Hisse Listeleri
# TradingView'dan alınıp Yahoo Finance'de doğrulanmış (335 hisse)
# ────────────────────────────────────────────

# BIST30 — Mayıs 2026 XU030 endeks bileşenleri
BIST_30 = [
    "THYAO", "GARAN", "AKBNK", "ISCTR", "YKBNK",
    "KCHOL", "SAHOL", "ASELS", "EREGL", "SASA",
    "ENKAI", "TUPRS", "FROTO", "TOASO", "BIMAS",
    "EKGYO", "TTKOM", "TCELL", "TAVHL", "PGSUS",
    "PETKM", "SISE",  "MGROS", "ULKER", "AEFES",
    "CIMSA", "HEKTS", "ASTOR", "KRDMD", "GUBRF",
]

# BIST100 — Mayıs 2026 XU100 endeks bileşenleri (uzmanpara.milliyet.com.tr)
BIST_HISSELER = [
    "AEFES", "AGHOL", "AGROT", "AHGAZ", "AKBNK",
    "AKSA",  "AKSEN", "ALARK", "ALFAS", "ALTNY",
    "ANHYT", "ANSGR", "ARCLK", "ARDYZ", "ASELS",
    "ASTOR", "AVPGY", "BERA",  "BIMAS", "BRSAN",
    "BRYAT", "BSOKE", "BTCIM", "CANTE", "CCOLA",
    "CIMSA", "CLEBI", "CWENE", "DOAS",  "DOHOL",
    "ECILC", "EFOR",  "EGEEN", "EKGYO", "ENERY",
    "ENJSA", "ENKAI", "EREGL", "EUPWR", "FROTO",
    "GARAN", "GESAN", "GOLTS", "GRTHO", "GSRAY",
    "GUBRF", "HALKB", "HEKTS", "IEYHO", "ISCTR",
    "ISMEN", "KARSN", "KCAER", "KCHOL", "KONTR",
    "KONYA", "KRDMD", "KTLEV", "LMKDC", "MAGEN",
    "MAVI",  "MGROS", "MIATK", "MPARK", "OBAMS",
    "ODAS",  "OTKAR", "OYAKC", "PAHOL", "PASEU",
    "PETKM", "PGSUS", "RALYH", "REEDR", "RYGYO",
    "SAHOL", "SASA",  "SELEC", "SISE",  "SKBNK",
    "SMRTG", "SOKM",  "TABGD", "TAVHL", "TCELL",
    "THYAO", "TKFEN", "TOASO", "TRALT", "TRENJ",
    "TRMET", "TSKB",  "TTKOM", "TTRAK", "TUPRS",
    "TURSG", "ULKER", "VAKBN", "VESTL", "YEOTK",
    "YKBNK", "ZOREN",
]

# Tüm doğrulanmış BIST hisseleri (Yahoo Finance'de çalışıyor)
from gecerli_hisseler import GECERLI_HISSELER as BIST_TUMHISSELER

PERIYOT_ADLARI = {
    "1h": "1 Saatlik",
    "4h": "4 Saatlik",
    "1d": "Günlük",
    "1w": "Haftalık",
}

# ────────────────────────────────────────────
# Teknik İndikatörler
# ────────────────────────────────────────────

def rsi_hesapla(close, periyot=14):
    delta = close.diff()
    kazan = delta.clip(lower=0)
    kayip = -delta.clip(upper=0)
    rs = (kazan.ewm(com=periyot - 1, adjust=True).mean() /
          (kayip.ewm(com=periyot - 1, adjust=True).mean() + 1e-10))
    return 100 - (100 / (1 + rs))


def macd_hesapla(close, hizli=12, yavas=26, sinyal=9):
    ema_h = close.ewm(span=hizli, adjust=False).mean()
    ema_y = close.ewm(span=yavas, adjust=False).mean()
    macd  = ema_h - ema_y
    sig   = macd.ewm(span=sinyal, adjust=False).mean()
    return macd, sig, macd - sig


def bollinger_hesapla(close, periyot=20, std=2):
    ort = close.rolling(periyot).mean()
    s   = close.rolling(periyot).std()
    return ort + std * s, ort, ort - std * s


def stokastik_hesapla(high, low, close, k=14, d=3):
    en_dusuk  = low.rolling(k).min()
    en_yuksek = high.rolling(k).max()
    stk = 100 * (close - en_dusuk) / ((en_yuksek - en_dusuk).replace(0, np.nan))
    return stk, stk.rolling(d).mean()


def momentum_hesapla(close, periyot=10):
    return ((close / close.shift(periyot)) - 1) * 100


def destek_direnc_bul(df, pencere=10):
    """Pivot-point tabanlı destek/direnç seviyelerini bulur."""
    if len(df) < pencere * 3:
        return [], []

    high = df['High'].values
    low  = df['Low'].values
    n    = len(low)

    destekler, direncler = [], []
    for i in range(pencere, n - pencere):
        if low[i]  <= low[i - pencere:i + pencere + 1].min() * 1.001:
            destekler.append(float(low[i]))
        if high[i] >= high[i - pencere:i + pencere + 1].max() * 0.999:
            direncler.append(float(high[i]))

    def grupla(liste, tolerans=0.015):
        if not liste:
            return []
        liste = sorted(liste)
        gruplar = [[liste[0]]]
        for s in liste[1:]:
            if abs(s - np.mean(gruplar[-1])) / np.mean(gruplar[-1]) < tolerans:
                gruplar[-1].append(s)
            else:
                gruplar.append([s])
        return [float(np.mean(g)) for g in gruplar]

    destekler = grupla(destekler)
    direncler = grupla(direncler)
    fiyat     = float(df['Close'].iloc[-1])

    alt = sorted([d for d in destekler if d < fiyat * 0.995], reverse=True)[:3]
    ust = sorted([d for d in direncler if d > fiyat * 1.005])[:3]
    return alt, ust


# ────────────────────────────────────────────
# Hacim Kırılımı Tespiti
# ────────────────────────────────────────────

def hacim_kirilim_bul(df, pencere=20, carpan=1.5):
    """
    Fiyat son N barın zirvesini kırarken hacim ortalamanın carpan katı üstünde.
    Kurumsal alım + momentum başlangıcı sinyali.
    """
    if len(df) < pencere + 5:
        return None
    if 'Volume' not in df.columns:
        return None

    son_vol = float(df['Volume'].iloc[-1])
    ort_vol = float(df['Volume'].tail(pencere + 1).iloc[:-1].mean())
    if ort_vol <= 0 or son_vol <= 0:
        return None
    oran = son_vol / ort_vol
    if oran < carpan:
        return None

    son_k = float(df['Close'].iloc[-1])
    son_o = float(df['Open'].iloc[-1])
    if son_k <= son_o:              # düşüş barı → geçersiz
        return None

    dir_n = float(df['High'].tail(pencere + 1).iloc[:-1].max())
    if son_k < dir_n * 0.985:      # N-bar zirvesini kırmıyor
        return None

    return {
        'hacim_orani':  round(oran, 1),
        'kirilim':      round(dir_n, 2),
    }


# EMA Sıralaması Tespiti
# ────────────────────────────────────────────

def ema_siralanma_bul(close, max_prime_pct=8.0):
    """
    EMA5 > EMA8 > EMA13 > EMA21 hizası yeni oluştu.
    Fiyat EMA21'den fazla uzaklaşmamış (primli değil).
    """
    if len(close) < 26:
        return None

    ema5  = close.ewm(span=5,  adjust=False).mean()
    ema8  = close.ewm(span=8,  adjust=False).mean()
    ema13 = close.ewm(span=13, adjust=False).mean()
    ema21 = close.ewm(span=21, adjust=False).mean()

    e5, e8  = float(ema5.iloc[-1]),  float(ema8.iloc[-1])
    e13, e21 = float(ema13.iloc[-1]), float(ema21.iloc[-1])

    if not (e5 > e8 > e13 > e21):   # tam hizalı değil
        return None

    fiyat     = float(close.iloc[-1])
    prime_pct = (fiyat - e21) / e21 * 100
    if prime_pct > max_prime_pct or prime_pct < 0:
        return None                  # çok pahalı veya EMA21 altında

    # Hizalama yeni mi başladı? (5 bar önce tam sıralı değildi)
    e5_p  = float(ema5.iloc[-5])
    e8_p  = float(ema8.iloc[-5])
    e13_p = float(ema13.iloc[-5])
    yeni  = not (e5_p > e8_p > e13_p)

    return {
        'prime_pct': round(prime_pct, 1),
        'yeni':      yeni,
        'e21':       round(e21, 2),
    }


# Konsolidasyon Kutusu Tespiti
# ────────────────────────────────────────────

def kutu_konsolidasyon_bul(df, gun_sayisi=30, maks_aralik_pct=0.10, min_dokunma=2):
    """
    Yatay konsolidasyon kutusu + çoklu destek testi arar.

    Aranan senaryo (örnekSeneryo.png):
      - Son N günde fiyat dar bir bantta sıkışmış (aralik < %10)
      - Alt destek çizgisine min_dokunma kadar Low değeri yakın
      - Son 3 günde fiyat desteğin üstünde kapanmış
      - Güncel fiyat direncin %5 içinde (breakout hazırlığı)

    Döner: dict veya None
    """
    if len(df) < gun_sayisi + 5:
        return None

    son    = df.tail(gun_sayisi)
    guncel = float(df['Close'].iloc[-1])

    highs = son['High'].values.astype(float)
    lows  = son['Low'].values.astype(float)
    closes = son['Close'].values.astype(float)

    p_high = float(highs.max())
    p_low  = float(lows.min())

    if p_low <= 0:
        return None

    aralik_pct = (p_high - p_low) / p_low
    if aralik_pct > maks_aralik_pct:
        return None        # Aralık çok geniş → konsolidasyon yok

    # Alt destek zonu: p_low'un %2.5 üstüne kadar
    destek_zone = p_low * 1.025

    # Desteğe dokunma sayısı
    dokunmalar = int(np.sum(lows <= destek_zone))
    if dokunmalar < min_dokunma:
        return None

    # Son 3 günde fiyat desteğin üstünde mi?
    son3_closes = df['Close'].tail(3).values.astype(float)
    if not (son3_closes > p_low * 0.995).all():
        return None        # Destek kırılmış

    # Güncel fiyat desteğin en az %0.5 üstünde (desteğin içinde değil kırılmamış)
    if guncel < p_low * 1.005:
        return None

    # Breakout puanı: fiyat direncin ne kadarına yaklaştı?
    breakout_pct = (guncel - p_low) / (p_high - p_low) if p_high > p_low else 0

    # Konsolidasyon öncesi düşüş var mı? (daha inandırıcı senaryo)
    if len(df) >= gun_sayisi + 10:
        onceki = df.iloc[-(gun_sayisi + 10):-(gun_sayisi)]
        onceki_ort = float(onceki['Close'].mean())
        oncesi_dusus = onceki_ort > p_high * 1.03   # Önceden yukarıdaydı
    else:
        oncesi_dusus = False

    return {
        'destek':       round(p_low, 2),
        'direnc':       round(p_high, 2),
        'aralik_pct':   round(aralik_pct * 100, 1),
        'dokunma':      dokunmalar,
        'breakout_pct': round(breakout_pct * 100, 1),
        'oncesi_dusus': oncesi_dusus,
        'gun_sayisi':   gun_sayisi,
    }


# ────────────────────────────────────────────
# Veri Çekme
# ────────────────────────────────────────────

def _sutunlari_duzenle(df):
    """yfinance MultiIndex sütunlarını düzleştirir."""
    if isinstance(df.columns, pd.MultiIndex):
        df = df.copy()
        df.columns = df.columns.get_level_values(0)
    return df


def veri_cek(hisse_kodu, periyot_tipi="1d"):
    """Yahoo Finance'den OHLCV verisi çeker. Hata varsa None döner."""
    ticker = f"{hisse_kodu}.IS"
    try:
        if periyot_tipi == "1h":
            df = yf.download(ticker, period="7d",  interval="1h",
                             auto_adjust=True, progress=False)
        elif periyot_tipi == "4h":
            df = yf.download(ticker, period="60d", interval="1h",
                             auto_adjust=True, progress=False)
            if df is not None and not df.empty:
                df = _sutunlari_duzenle(df)
                df = df.resample('4h').agg({
                    'Open': 'first', 'High': 'max',
                    'Low': 'min',   'Close': 'last',
                    'Volume': 'sum'
                }).dropna()
                return df if len(df) >= 30 else None
        elif periyot_tipi == "1w":
            df = yf.download(ticker, period="3y",  interval="1wk",
                             auto_adjust=True, progress=False)
        else:  # "1d"
            df = yf.download(ticker, period="1y",  interval="1d",
                             auto_adjust=True, progress=False)

        if df is None or df.empty:
            return None
        df = _sutunlari_duzenle(df)
        return df if len(df) >= 30 else None
    except Exception:
        return None


_PERIOD_MAP = {"1h": ("7d", "1h"), "4h": ("60d", "1h"), "1w": ("3y", "1wk"), "1d": ("1y", "1d")}

def veri_cek_toplu(hisseler: list, periyot_tipi: str) -> dict:
    """Tüm hisseleri tek yf.download çağrısıyla çeker. {hisse: df} döner."""
    if not hisseler:
        return {}
    period, interval = _PERIOD_MAP.get(periyot_tipi, ("1y", "1d"))
    tickers = " ".join(f"{h}.IS" for h in hisseler)
    try:
        raw = yf.download(tickers, period=period, interval=interval,
                          auto_adjust=True, progress=False, group_by='ticker')
    except Exception:
        return {}

    if raw is None or raw.empty:
        return {}

    # MultiIndex kolon formatını tespit et
    # Eski yfinance: (ticker, price)  → raw['THYAO.IS'] çalışır
    # Yeni yfinance: (price, ticker)  → raw.xs('THYAO.IS', axis=1, level=1) gerekir
    is_multi = isinstance(raw.columns, pd.MultiIndex)
    if is_multi:
        lvl0 = set(raw.columns.get_level_values(0))
        lvl1 = set(raw.columns.get_level_values(1))
    else:
        lvl0 = lvl1 = set()

    def _hisse_df(key):
        if not is_multi:
            return raw.copy()
        if key in lvl0:                        # (ticker, price) formatı
            return raw[key].copy()
        if key in lvl1:                        # (price, ticker) formatı
            return raw.xs(key, axis=1, level=1).copy()
        return None

    sonuclar = {}
    for hisse in hisseler:
        try:
            key = f"{hisse}.IS"
            df = _hisse_df(key)
            if df is None:
                continue
            df = _sutunlari_duzenle(df).dropna(how='all')
            if periyot_tipi == "4h" and len(df) >= 10:
                df = df.resample('4h').agg({
                    'Open': 'first', 'High': 'max',
                    'Low': 'min', 'Close': 'last', 'Volume': 'sum'
                }).dropna()
            if df is not None and len(df) >= 30:
                sonuclar[hisse] = df
        except Exception:
            pass
    return sonuclar


# ────────────────────────────────────────────
# Sinyal Hesaplama
# ────────────────────────────────────────────

def _indikatör_degerlendır(sinyal):
    return 1 if sinyal == "AL" else (-1 if sinyal == "SAT" else 0)


def _hizala_gunluk_ema(df_g, close_gunluk):
    """Günlük close serisinden hesaplanan EMAları df_g barlarına hizalar."""
    import numpy as np, pandas as pd

    def _gun_no(ts):
        return int(pd.Timestamp(ts).value // (86_400 * 10**9))

    g_days = np.array([_gun_no(t) for t in df_g.index])

    for p in (5, 8, 13, 21, 50):
        ema_vals = close_gunluk.ewm(span=p, adjust=False).mean()
        e_days   = np.array([_gun_no(t) for t in ema_vals.index])
        e_vals   = ema_vals.values.astype(float)

        result = np.full(len(df_g), np.nan)
        for i, gd in enumerate(g_days):
            idx = int(np.searchsorted(e_days, gd, side='right')) - 1
            if idx >= 0:
                result[i] = e_vals[idx]
        df_g[f'EMA{p}'] = result


def sinyal_hesapla(df, periyot_tipi="1d", destek_gun_sayisi=3, close_gunluk=None):
    """
    Tüm indikatörleri hesaplar, destek filtresi uygular ve sinyal üretir.
    Döndürür: dict (tüm değerler + genel_sinyal) veya None
    """
    if df is None or len(df) < 50:
        return None

    df = df.copy()
    close = df['Close'].squeeze()
    high  = df['High'].squeeze()
    low   = df['Low'].squeeze()

    r = {}
    r['fiyat']   = round(float(close.iloc[-1]), 2)
    r['periyot'] = periyot_tipi

    # ── RSI ──────────────────────────────────
    rsi_val = float(rsi_hesapla(close).iloc[-1])
    r['rsi'] = round(rsi_val, 1)
    if   rsi_val < 30:         r['rsi_sinyal'] = "AL";   r['rsi_yorum'] = "Aşırı Satım"
    elif rsi_val <= 55:        r['rsi_sinyal'] = "NÖTR"; r['rsi_yorum'] = f"{rsi_val:.0f}"
    else:                      r['rsi_sinyal'] = "SAT";  r['rsi_yorum'] = "Aşırı Alım"

    # ── Trend (SMA50) ──────────────────────────
    sma50 = close.rolling(50).mean()
    sma50_son = float(sma50.iloc[-1])
    r['sma50'] = round(sma50_son, 2)
    if r['fiyat'] > sma50_son: r['trend_sinyal'] = "AL";  r['trend_yorum'] = "Yükseliş"
    else:                      r['trend_sinyal'] = "SAT"; r['trend_yorum'] = "Düşüş"

    # ── MACD ──────────────────────────────────
    macd_line, macd_sig, hist = macd_hesapla(close)
    macd_val  = float(macd_line.iloc[-1])
    hist_son  = float(hist.iloc[-1])
    hist_prev = float(hist.iloc[-2]) if len(hist) > 1 else 0
    r['macd']      = round(macd_val, 3)
    r['macd_hist'] = round(hist_son, 4)

    # Taze MACD kesişimi: son 3 mum içinde histogram negatiften pozitife geçti
    hist_arr = hist.dropna().values
    macd_kesisim      = False
    kesisim_kac_once  = None
    if len(hist_arr) >= 4:
        for i in range(len(hist_arr) - 1, max(len(hist_arr) - 5, 0), -1):
            if hist_arr[i] > 0 and hist_arr[i - 1] <= 0:
                kac = len(hist_arr) - 1 - i   # 0 = bu mum, 1 = bir önceki mum
                if kac <= 1:
                    macd_kesisim     = True
                    kesisim_kac_once = kac
                break
    r['macd_kesisim']          = macd_kesisim
    r['macd_kesisim_kac_once'] = kesisim_kac_once

    # Yaklaşan kesişim: histogram hâlâ negatif ama bu hızla kaç bar sonra geçer?
    macd_yaklasan    = False
    yaklasan_bar     = None
    if not macd_kesisim and len(hist_arr) >= 4:
        h0 = hist_arr[-1]   # son bar
        h1 = hist_arr[-2]   # 1 önceki
        h2 = hist_arr[-3]   # 2 önceki
        hiz = h0 - h1       # son artış miktarı
        # Histogram negatif, 2 ardışık bar boyunca yükseliyor, sıfıra yaklaşıyor
        if h0 < 0 and h0 > h1 > h2 and hiz > 0:
            bar_kala = abs(h0) / hiz   # doğrusal ekstrapolasyon
            if bar_kala <= 2.0:
                macd_yaklasan = True
                yaklasan_bar  = round(bar_kala, 1)
    r['macd_yaklasan']  = macd_yaklasan
    r['macd_yaklasan_bar'] = yaklasan_bar

    if macd_kesisim:
        ne_zaman = "bu mumda" if kesisim_kac_once == 0 else f"{kesisim_kac_once} mum önce"
        r['macd_sinyal'] = "AL"
        r['macd_yorum']  = f"KESİŞİM ({ne_zaman})"
    elif macd_yaklasan:
        r['macd_sinyal'] = "AL"
        r['macd_yorum']  = f"~{yaklasan_bar} bar kala"
    elif hist_son > 0 and hist_son >= hist_prev:
        r['macd_sinyal'] = "AL";   r['macd_yorum'] = f"{macd_val:.3f}"
    elif hist_son < 0 and hist_son <= hist_prev:
        r['macd_sinyal'] = "NÖTR"; r['macd_yorum'] = f"{macd_val:.3f}"
    else:
        r['macd_sinyal'] = "NÖTR"; r['macd_yorum'] = f"{macd_val:.3f}"

    # ── Bollinger ─────────────────────────────
    bb_ust, _, bb_alt = bollinger_hesapla(close)
    bb_u = float(bb_ust.iloc[-1])
    bb_a = float(bb_alt.iloc[-1])
    pozisyon = (r['fiyat'] - bb_a) / (bb_u - bb_a + 1e-10)
    r['bb_ust'] = round(bb_u, 2)
    r['bb_alt'] = round(bb_a, 2)
    if   pozisyon <= 0.15: r['bollinger_sinyal'] = "AL";   r['bollinger_yorum'] = "Alt Bant"
    elif pozisyon >= 0.85: r['bollinger_sinyal'] = "SAT";  r['bollinger_yorum'] = "Üst Bant"
    else:                  r['bollinger_sinyal'] = "NÖTR"; r['bollinger_yorum'] = "Orta Bant"

    # ── Stokastik ─────────────────────────────
    k_val = float(stokastik_hesapla(high, low, close)[0].iloc[-1])
    r['stokastik'] = round(k_val, 1)
    if   k_val < 25: r['stokastik_sinyal'] = "AL";   r['stokastik_yorum'] = f"%K {k_val:.0f}"
    elif k_val > 75: r['stokastik_sinyal'] = "SAT";  r['stokastik_yorum'] = f"%K {k_val:.0f}"
    else:            r['stokastik_sinyal'] = "NÖTR"; r['stokastik_yorum'] = f"%K {k_val:.0f}"

    # ── Momentum ──────────────────────────────
    mom_val = float(momentum_hesapla(close).iloc[-1])
    r['momentum'] = round(mom_val, 1)
    if   mom_val > 3:  r['momentum_sinyal'] = "AL";   r['momentum_yorum'] = f"%{mom_val:.1f}"
    elif mom_val < -3: r['momentum_sinyal'] = "SAT";  r['momentum_yorum'] = f"%{mom_val:.1f}"
    else:              r['momentum_sinyal'] = "NÖTR"; r['momentum_yorum'] = f"%{mom_val:.1f}"

    # ── Destek / Direnç ───────────────────────
    destekler, direncler = destek_direnc_bul(df)
    r['destekler'] = [round(d, 2) for d in destekler]
    r['direncler'] = [round(d, 2) for d in direncler]

    # ── Destek / Direnç Koşulları ─────────────────────────
    # YOL 1: Pivot-point desteği (yakın zamanda test edilmiş)
    en_yakin = destekler[0] if destekler else None
    r['en_yakin_destek'] = round(en_yakin, 2) if en_yakin else None
    r['destek_uzeri']    = False
    r['destek_yakin']    = False
    r['destek_test']     = False

    if en_yakin:
        son_n   = df['Close'].tail(destek_gun_sayisi)
        uzaklik = (r['fiyat'] - en_yakin) / en_yakin
        # Son 20 periyottaki en düşük Low desteğe %6 yakın mı?
        son_20_min = float(df['Low'].tail(20).min())
        r['destek_uzeri'] = bool((son_n > en_yakin).all())
        r['destek_yakin'] = 0 < uzaklik < 0.08
        r['destek_test']  = abs(son_20_min - en_yakin) / en_yakin < 0.06

    # YOL 2: Son 30 periyodun dip noktasından sıçrama (yakın zamanlı dip)
    # Periyodun minimumunu bul ve fiyat oradan N gün üstünde mi?
    dip_30 = float(df['Low'].tail(30).min())
    dip_konum = int(df['Low'].tail(30).values.argmin())
    # Dip son 20-5 gün arasında oluştuysa (çok eski veya çok yeni değil)
    dip_eski   = 5 <= (30 - dip_konum) <= 25
    son_n_dip  = df['Close'].tail(destek_gun_sayisi)
    dip_uzeri  = bool((son_n_dip > dip_30 * 1.001).all())
    dip_yakin  = 0 < (r['fiyat'] - dip_30) / dip_30 < 0.10
    dip_sinyal = dip_eski and dip_uzeri and dip_yakin

    if dip_sinyal and r['en_yakin_destek'] is None:
        r['en_yakin_destek'] = round(dip_30, 2)

    # YOL 3: Yatay kutu konsolidasyon (sıkışma + destek tutma)
    kutu = kutu_konsolidasyon_bul(df)
    r['kutu'] = kutu
    if kutu and r['en_yakin_destek'] is None:
        r['en_yakin_destek'] = round(kutu['destek'], 2)

    # YOL 4: Hacim kırılımı
    hacim = hacim_kirilim_bul(df)
    r['hacim'] = hacim

    # YOL 5: EMA sıralaması
    ema_sir = ema_siralanma_bul(close)
    r['ema_sir'] = ema_sir


    # ── Gösterge puanı (sadece SAT tespiti için) ──────────
    agirliklar = {'rsi': 1.5, 'trend': 2.0, 'macd': 1.5,
                  'bollinger': 1.0, 'stokastik': 1.0, 'momentum': 0.5}
    al_puan = sat_puan = 0.0
    for ind, agirlik in agirliklar.items():
        s = r.get(f'{ind}_sinyal', 'NÖTR')
        if s == "AL":  al_puan  += agirlik
        if s == "SAT": sat_puan += agirlik

    r['al_puan']  = round(al_puan, 2)
    r['sat_puan'] = round(sat_puan, 2)
    r['dip_sinyal'] = dip_sinyal

    # ── Fiyat Hareketi Pattern Koşulları ──────────────────
    rsi_ok   = r['rsi'] <= 68                             # Aşırı alım yok
    bearish  = sat_puan >= 4.0 and sat_puan > al_puan    # Güçlü satış baskısı var

    destek_tam = r['destek_uzeri'] and r['destek_yakin'] and r['destek_test']
    destek_ok  = (destek_tam or dip_sinyal) and rsi_ok and not bearish

    kutu_ok     = bool(kutu)    and rsi_ok and not bearish
    macd_kes_ok = macd_kesisim and rsi_ok and not bearish
    macd_yak_ok = macd_yaklasan and rsi_ok and not bearish
    hacim_ok    = bool(hacim)   and rsi_ok and not bearish
    ema_sir_ok  = bool(ema_sir) and rsi_ok and not bearish

    # ── Sinyal hiyerarşisi ────────────────────────────────
    if kutu_ok and macd_kes_ok:
        r['genel_sinyal'] = "KUTU+MACD"
    elif kutu_ok:
        r['genel_sinyal'] = "KUTU AL"
    elif hacim_ok and macd_kes_ok:
        r['genel_sinyal'] = "HACİM+MACD"
    elif hacim_ok:
        r['genel_sinyal'] = "HACİM KIRILIM"
    elif destek_ok and macd_kes_ok:
        r['genel_sinyal'] = "DESTEK+MACD"
    elif macd_kes_ok:
        r['genel_sinyal'] = "MACD KESİŞİM"
    elif ema_sir_ok and ema_sir.get('yeni'):
        r['genel_sinyal'] = "EMA SIRALANMA"
    elif macd_yak_ok:
        r['genel_sinyal'] = "MACD YAKLAŞIM"
    elif destek_ok:
        r['genel_sinyal'] = "DESTEK AL"
    elif sat_puan >= 5.5 and sat_puan >= al_puan * 2.0:
        r['genel_sinyal'] = "GÜÇLÜ SAT"
    elif sat_puan >= 4.0 and sat_puan > al_puan * 1.2:
        r['genel_sinyal'] = "SAT"
    else:
        r['genel_sinyal'] = "NÖTR"

    # ── Grafik verisi (son 80 mum + EMA + MACD + RSI) ──────
    df_g = df.tail(80).copy()
    if periyot_tipi == "1d" or close_gunluk is None:
        for p in (5, 8, 13, 21, 50):
            df_g[f'EMA{p}'] = close.ewm(span=p, adjust=False).mean().tail(80).values
    else:
        _hizala_gunluk_ema(df_g, close_gunluk)

    # RSI serisi (tüm close üzerinden hesapla, son 80'i al)
    rsi_seri = rsi_hesapla(close)
    df_g['RSI'] = rsi_seri.tail(80).values

    # MACD serisi
    macd_l_s, sinyal_l_s, hist_s = macd_hesapla(close)
    df_g['MACD_LINE'] = macd_l_s.tail(80).values
    df_g['MACD_SIG']  = sinyal_l_s.tail(80).values
    df_g['MACD_HIST'] = hist_s.tail(80).values

    r['df_grafik'] = df_g

    return r


# ────────────────────────────────────────────
# Bildirim Metni (Telegram / Sosyal Medya)
# ────────────────────────────────────────────

def bildirim_metni(sonuc):
    """Kullanıcının istediği bildirim formatını oluşturur."""
    hisse   = sonuc.get('hisse', '?')
    fiyat   = sonuc.get('fiyat', 0)
    periyot = PERIYOT_ADLARI.get(sonuc.get('periyot', '1d'), sonuc.get('periyot', ''))

    simdi = datetime.now()
    tarih = simdi.strftime("%d %B %Y")
    for en, tr in [("January","Ocak"),("February","Şubat"),("March","Mart"),
                   ("April","Nisan"),("May","Mayıs"),("June","Haziran"),
                   ("July","Temmuz"),("August","Ağustos"),("September","Eylül"),
                   ("October","Ekim"),("November","Kasım"),("December","Aralık")]:
        tarih = tarih.replace(en, tr)
    tarih = tarih.lstrip('0')

    genel = sonuc.get('genel_sinyal', 'NÖTR')
    if 'AL' in genel:
        yon_emoji = "💸"
        yon_etiket = "#ALIŞ"
        destek_val = sonuc.get('en_yakin_destek')
        ek_satir = f"🕵🏼 Destek Fiyatı: {destek_val:.2f} ₺\n" if destek_val else ""
    else:
        yon_emoji = "🔴"
        yon_etiket = "#SATIŞ"
        direncler = sonuc.get('direncler', [])
        direnc_val = direncler[0] if direncler else None
        ek_satir = f"⛔ Direnç Fiyatı: {direnc_val:.2f} ₺\n" if direnc_val else ""

    return (
        f"📊 Hisse: #{hisse}\n"
        f"{yon_emoji} {yon_etiket} Fiyatı: {fiyat:.2f} ₺\n"
        f"{ek_satir}"
        f"⏰ Periyot: {periyot}\n"
        f"📅 Tarih: {tarih}"
    )
