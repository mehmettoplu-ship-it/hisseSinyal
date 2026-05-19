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
    "1h":  "1 Saatlik",
    "4h":  "4 Saatlik",
    "1d":  "Günlük",
    "1w":  "Haftalık",
    "1mo": "Aylık",
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

    low_s  = df['Low']
    high_s = df['High']
    n      = len(low_s)

    # Vectorized: centered rolling min/max replaces O(n²) Python loop
    win     = 2 * pencere + 1
    lo_v    = low_s.values
    hi_v    = high_s.values
    roll_lo = low_s.rolling(win, center=True).min().values
    roll_hi = high_s.rolling(win, center=True).max().values
    sl      = slice(pencere, n - pencere)

    destekler = lo_v[sl][lo_v[sl] <= roll_lo[sl] * 1.001].tolist()
    direncler = hi_v[sl][hi_v[sl] >= roll_hi[sl] * 0.999].tolist()

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

def ema_siralanma_bul(close, max_prime_pct=8.0, _emas=None):
    """
    EMA5 > EMA8 > EMA13 > EMA21 hizası yeni oluştu.
    Fiyat EMA21'den fazla uzaklaşmamış (primli değil).
    _emas: {periyot: pd.Series} önden hesaplanmış EMA dizileri (opsiyonel).
    """
    if len(close) < 26:
        return None

    if _emas:
        ema5, ema8, ema13, ema21 = _emas[5], _emas[8], _emas[13], _emas[21]
    else:
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

def kutu_konsolidasyon_bul(df, gun_sayisi=50, maks_aralik_pct=0.10, min_dokunma=2):
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
# RSI Bullish Diverjans Tespiti
# ────────────────────────────────────────────

def rsi_diverjans_bul(close, rsi_seri=None, lookback=50, pencere=5):
    """
    Fiyat daha düşük dip yaparken RSI daha yüksek dip yapıyor.
    Kurumsal alımın erken habercisi — dönüş sinyali.
    rsi_seri: önceden hesaplanmış seri (None → içerde hesaplanır).
    """
    if len(close) < lookback + pencere:
        return None
    if rsi_seri is None:
        rsi_seri = rsi_hesapla(close)

    c = close.values[-lookback:]
    r = rsi_seri.values[-lookback:]
    n = len(c)

    # Vectorized local minima
    roll_lo = pd.Series(c).rolling(2 * pencere + 1, center=True).min().values
    is_dip  = c <= roll_lo * 1.001
    is_dip[:pencere]       = False
    is_dip[n - pencere:]   = False
    dipler = np.where(is_dip)[0].tolist()

    if len(dipler) < 2:
        return None

    d1, d2 = dipler[-2], dipler[-1]

    if c[d2] >= c[d1] * 0.999:    # fiyat daha düşük dip yapmıyor
        return None
    if r[d2] <= r[d1] * 1.10:      # RSI en az %10 daha yüksek olmalı (yüzdesel tolerans)
        return None
    if r[d2] > 60:                 # RSI zaten yüksek → diverjans anlamsız
        return None

    return {
        'fiyat_dip1': round(float(c[d1]), 2),
        'fiyat_dip2': round(float(c[d2]), 2),
        'rsi_dip1':   round(float(r[d1]), 1),
        'rsi_dip2':   round(float(r[d2]), 1),
        'guclu':      r[d2] < 45,   # oversold'da daha güçlü
    }


# ────────────────────────────────────────────
# EMA21 Geri Çekilme (Pullback) Tespiti
# ────────────────────────────────────────────

def ema_pullback_bul(close, _emas=None, tolerans_pct=3.0):
    """
    Yükselen trendde EMA21'e geri çekilip yukarı kırma.
    - EMA21 yükselen trend (son 10 bar eğimi pozitif)
    - Son 5 bar içinde fiyat EMA21'e ±tolerans% mesafeye girmiş
    - Şu an fiyat EMA21 üstünde ve önceki bardan yüksek
    - EMA21'den uzaklaşma %8'i geçmiyor (primli değil)
    """
    if len(close) < 30:
        return None

    ema21    = _emas[21] if _emas else close.ewm(span=21, adjust=False).mean()
    e21_son  = float(ema21.iloc[-1])
    e21_eski = float(ema21.iloc[-10])
    fiyat    = float(close.iloc[-1])

    if e21_son <= e21_eski * 1.001:      # EMA21 yükselmiyor
        return None
    if fiyat <= e21_son:                  # fiyat EMA21 altında
        return None
    if fiyat <= float(close.iloc[-2]):    # fiyat yükselmiyor
        return None

    # Son 5 bar içinde EMA21'e dokunma
    son5_c   = close.values[-6:-1]
    son5_e21 = ema21.values[-6:-1]
    dokunma  = np.any(np.abs(son5_c - son5_e21) / (son5_e21 + 1e-10) <= tolerans_pct / 100)
    if not dokunma:
        return None

    prime_pct = (fiyat - e21_son) / e21_son * 100
    if prime_pct > 8.0:                   # çok uzaklaşmış
        return None

    return {
        'ema21':      round(e21_son, 2),
        'prime_pct':  round(prime_pct, 1),
        'trend_hizi': round((e21_son - e21_eski) / e21_eski * 100, 2),
    }


# ────────────────────────────────────────────
# Bollinger Band Sıkışması (Squeeze) Tespiti
# ────────────────────────────────────────────

def bollinger_squeeze_bul(close, min_lookback=60):
    """
    Bollinger bantları son N günün en dar noktasında → büyük hareket kapıda.
    MACD pozitif yönlüyse AL yönünde filtrele.
    """
    if len(close) < min_lookback + 20:
        return None

    bb_ust, bb_ort, bb_alt = bollinger_hesapla(close)
    genislik = ((bb_ust - bb_alt) / bb_ort).dropna()

    if len(genislik) < min_lookback:
        return None

    son_g = float(genislik.iloc[-1])
    min_g = float(genislik.tail(min_lookback).min())
    max_g = float(genislik.tail(min_lookback).max())

    if son_g > min_g * 1.08:             # yeterince sıkışmamış
        return None

    sikisma_pct = 100 - (son_g - min_g) / max(max_g - min_g, 1e-10) * 100

    return {
        'genislik_pct': round(son_g * 100, 2),
        'sikisma_pct':  round(sikisma_pct, 1),
    }


# ────────────────────────────────────────────
# Mum Formasyonu Tespiti (Çekiç / Bullish Engulfing)
# ────────────────────────────────────────────

def mum_formasyonu_bul(df, destekler=None):
    """
    Bullish mum formasyonu arar.

    Bar indeksleme:
      1-2 bar formasyonlar → sinyal: bar[-2], onay: bar[-1]
      3 bar formasyonlar   → ilk: bar[-3], orta: bar[-2], son: bar[-1]  (son bar tamamlayıcı)

    Filtreler: ATR tabanlı min gövde + 5-7 bar düşüş trendi + hacim kontrolü
    """
    if len(df) < 8:
        return None

    def _ohlc(row):
        return (float(row['Open']), float(row['High']),
                float(row['Low']),  float(row['Close']))

    # Sinyal ve onay barları (1-2 bar formasyonlar)
    o_on, h_on, l_on, c_on = _ohlc(df.iloc[-1])   # onay mumu
    o,    h,    l,    c    = _ohlc(df.iloc[-2])    # sinyal mumu
    o2,   h2,   l2,   c2   = _ohlc(df.iloc[-3])   # sinyal öncesi bar (2-bar bağlamı)

    # 3-bar formasyonlar
    o_i, h_i, l_i, c_i = _ohlc(df.iloc[-3])   # ilk bar (düşüş)
    o_m, h_m, l_m, c_m = _ohlc(df.iloc[-2])   # orta bar (yıldız/geçiş)
    o_s, h_s, l_s, c_s = _ohlc(df.iloc[-1])   # son bar (tamamlayıcı)

    toplam = h - l
    if toplam <= 0:
        return None

    govde     = abs(c  - o)
    govde2    = abs(c2 - o2)
    govde_on  = abs(c_on - o_on)
    alt_golge = min(c, o)  - l
    ust_golge = h - max(c, o)

    # ── ATR: son 7 barın ortalama aralığı ──────────────────────
    atr_seri = df['High'].iloc[-8:-1] - df['Low'].iloc[-8:-1]
    atr = float(atr_seri.mean()) if len(atr_seri) >= 5 else 0.0
    if atr <= 0:
        return None   # yeterli bar yoksa formasyon aramasını atla
    min_govde = atr * 0.15     # anlamsız toz mumları elemek için alt sınır

    # ── Düşüş trendi bağlamı ────────────────────────────────────
    # 6 bar önce fiyat, sinyal barından önceki barın kapanışından anlamlı yüksek
    trend_yukari = float(df['Close'].iloc[-7])   # 6 bar önceki kapanış
    trend_asagi  = c2                            # sinyal barı öncesi kapanış
    dusus_trendi = trend_yukari > trend_asagi * 1.005   # en az %0.5 düşüş

    # ── Hacim kontrolü ──────────────────────────────────────────
    if 'Volume' in df.columns:
        avg_vol  = float(df['Volume'].iloc[-8:-1].mean())
        vol_sin  = float(df['Volume'].iloc[-2])
        hacim_onay = avg_vol > 0 and vol_sin >= avg_vol * 0.75
    else:
        hacim_onay = True

    # ── Onay mumu koşulları ─────────────────────────────────────
    onay_yukselis = c_on > o_on                   # yükseliş mumu
    onay_kapanisi = c_on > c                      # sinyal barının kapanışı üstünde
    onay_anlamli  = govde_on >= min_govde         # anlamsız küçük mum değil

    # ═══════════════════════════════════════════════════════════
    # TEK MUM FORMASYONLARI  —  onay mumu zorunlu
    # ═══════════════════════════════════════════════════════════

    # Çekiç: uzun alt gölge, küçük gövde, düşüş dipinde dönüş
    cekic = (
        govde >= min_govde and
        alt_golge >= govde  * 2.2 and
        alt_golge >= toplam * 0.45 and
        ust_golge <= toplam * 0.30 and
        c >= l + toplam * 0.55 and
        dusus_trendi and
        hacim_onay and
        onay_yukselis and onay_kapanisi and onay_anlamli
    )

    # Dragonfly Doji: gövde yok, sadece uzun alt gölge — dipten fıyatı itti
    dragonfly = (
        govde    <= toplam * 0.05 and
        alt_golge >= toplam * 0.72 and
        ust_golge <= toplam * 0.10 and
        toplam   >= atr * 0.6 and              # anlamsız küçük mum değil
        dusus_trendi and
        onay_yukselis and onay_kapanisi and onay_anlamli
    )

    # Doji: iki taraflı gölge, belirsizlik → güçlü onay mumu zorunlu
    doji = (
        toplam    >= atr * 0.5 and
        govde     <= toplam * 0.07 and
        alt_golge >= toplam * 0.32 and
        ust_golge >= toplam * 0.32 and
        c2 < o2 and dusus_trendi and
        hacim_onay and
        onay_yukselis and onay_kapanisi and onay_anlamli and
        govde_on  >= atr * 0.35                # onay mumu gerçekten anlamlı olmalı
    )

    # Ters Çekiç: en zayıf — sadece üst gölgeyi aşan güçlü onay ile geçer
    ters_cekic = (
        govde     >= min_govde and
        ust_golge >= govde  * 2.2 and
        ust_golge >= toplam * 0.45 and
        alt_golge <= toplam * 0.20 and
        c2 < o2 and dusus_trendi and
        hacim_onay and
        c_on >= h and                          # onay mumu çekicin tepesini aşmalı
        govde_on >= govde * 1.5               # güçlü onay mumu şart
    )

    # ═══════════════════════════════════════════════════════════
    # İKİ MUM FORMASYONLARI  —  hafif onay koşulu
    # ═══════════════════════════════════════════════════════════

    # Bullish Engulfing: önceki düşüşü tamamen yutuyor
    engulfing = (
        c2 < o2 and govde2 >= min_govde and    # gerçek bir düşüş mumu
        c  > o  and govde  >= min_govde and    # gerçek bir yükseliş mumu
        o  <= c2 and                           # açılış önceki kapanış altında
        c  >= o2 and                           # kapanış önceki açılış üstünde
        govde >= govde2 * 1.1 and             # yutan mum belirgin şekilde büyük
        dusus_trendi and
        hacim_onay and
        onay_yukselis                          # hafif onay yeterli
    )

    # Piercing: gap-down açılış, önceki mumun orta noktasını kurtarıyor
    piercing = (
        c2 < o2 and govde2 >= atr * 0.4 and   # anlamlı düşüş mumu
        c  > o  and govde  >= min_govde and
        o  < l2 and                            # kesin gap-down açılış
        c  > (o2 + c2) / 2 and               # önceki mumun ortasını aştı
        c  < o2 and                            # ama tam yutmadı (o engulfing olurdu)
        dusus_trendi and hacim_onay and
        onay_yukselis
    )

    # Harami: büyük düşüş mumunun içinde küçük yükseliş — zayıf, güçlü onay şart
    harami = (
        c2 < o2 and govde2 >= atr * 0.45 and  # büyük bir düşüş mumu
        c  > o  and
        o  > c2 and c  < o2 and              # gövde tamamen içeride
        govde <= govde2 * 0.40 and           # belirgin şekilde küçük
        dusus_trendi and
        hacim_onay and
        onay_yukselis and onay_kapanisi and onay_anlamli   # güçlü onay şart
    )

    # ═══════════════════════════════════════════════════════════
    # ÜÇ MUM FORMASYONLARI  —  son bar tamamlayıcı, onay ayrıca gerekmez
    # ═══════════════════════════════════════════════════════════

    govde_i = abs(c_i - o_i)
    govde_m = abs(c_m - o_m)
    govde_s = abs(c_s - o_s)

    # Sabah Yıldızı: büyük düşüş → küçük yıldız → büyük yükseliş
    sabah_yildizi = (
        c_i < o_i and govde_i >= atr * 0.50 and   # büyük düşüş mumu
        govde_m <= govde_i * 0.35 and              # küçük yıldız
        c_m < c_i and                              # yıldız önceki kapanışın altında
        c_s > o_s and govde_s >= atr * 0.40 and   # anlamlı yükseliş mumu
        c_s > (o_i + c_i) / 2 and                 # ilk mumun ortasını geçti
        dusus_trendi
    )

    # 3 Beyaz Asker: art arda 3 güçlü yükseliş mumu, üst gölgeler küçük
    uc_asker = (
        c_s > o_s and c_m > o_m and c_i > o_i and
        govde_s >= atr * 0.40 and govde_m >= atr * 0.35 and govde_i >= atr * 0.30 and
        o_s >= c_m * 0.996 and o_m >= c_i * 0.996 and   # ardışık, büyük gap yok
        c_s > c_m > c_i and                              # her kapanış öncekinin üstünde
        (h_s - max(o_s, c_s)) <= govde_s * 0.40 and     # üst gölgeler küçük
        (h_m - max(o_m, c_m)) <= govde_m * 0.40 and
        (h_i - max(o_i, c_i)) <= govde_i * 0.40
    )

    # ── Öncelik sırası: en güçlüden en zayıfa ──────────────────
    if   sabah_yildizi: formasyon = "SABAH YILDIZI"
    elif uc_asker:      formasyon = "3 BEYAZ ASKER"
    elif engulfing:     formasyon = "YUTAN MUM"
    elif cekic:         formasyon = "ÇEKIÇ"
    elif dragonfly:     formasyon = "DRAGONFLY DOJİ"
    elif piercing:      formasyon = "PİERCİNG"
    elif harami:        formasyon = "HARAMİ"
    elif ters_cekic:    formasyon = "TERS ÇEKIÇ"
    elif doji:          formasyon = "DOJİ"
    else:               return None

    # Referans fiyat: 3-bar formasyonlarda son barın kapanışı, diğerlerinde onay barı
    ref = c_s if formasyon in ("SABAH YILDIZI", "3 BEYAZ ASKER") else c_on
    destek_yakin = bool(destekler and
                        any(abs(ref - d) / (d + 1e-10) < 0.05 for d in destekler[:3]))

    guclu = destek_yakin or formasyon in ("SABAH YILDIZI", "3 BEYAZ ASKER", "YUTAN MUM")

    return {
        'formasyon':    formasyon,
        'destek_yakin': destek_yakin,
        'guclu':        guclu,
    }


# ────────────────────────────────────────────
# Heikin Ashi
# ────────────────────────────────────────────

def heikin_ashi(df: "pd.DataFrame") -> "pd.DataFrame":
    """Normal OHLCV DataFrame'i Heikin Ashi mumlarına dönüştürür."""
    ha = df.copy()
    ha['Close'] = (df['Open'] + df['High'] + df['Low'] + df['Close']) / 4
    ha_open = [(df['Open'].iloc[0] + df['Close'].iloc[0]) / 2]
    for i in range(1, len(df)):
        ha_open.append((ha_open[-1] + ha['Close'].iloc[i - 1]) / 2)
    ha['Open'] = ha_open
    ha['High'] = pd.concat([ha['Open'], ha['Close'], df['High']], axis=1).max(axis=1)
    ha['Low']  = pd.concat([ha['Open'], ha['Close'], df['Low']],  axis=1).min(axis=1)
    return ha


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
    _KW = dict(auto_adjust=True, progress=False, timeout=20)
    try:
        if periyot_tipi == "1h":
            df = yf.download(ticker, period="30d", interval="1h", **_KW)
        elif periyot_tipi == "4h":
            df = yf.download(ticker, period="90d", interval="1h", **_KW)
            if df is not None and not df.empty:
                df = _sutunlari_duzenle(df)
                df = df.resample('4h').agg({
                    'Open': 'first', 'High': 'max',
                    'Low': 'min',   'Close': 'last',
                    'Volume': 'sum'
                }).dropna()
                return df if len(df) >= 30 else None
        elif periyot_tipi == "1w":
            df = yf.download(ticker, period="3y",  interval="1wk", **_KW)
        elif periyot_tipi == "1mo":
            df = yf.download(ticker, period="10y", interval="1mo", **_KW)
        else:  # "1d"
            df = yf.download(ticker, period="2y",  interval="1d", **_KW)

        if df is None or df.empty:
            return None
        df = _sutunlari_duzenle(df)
        df = df.dropna(subset=['Open', 'High', 'Low', 'Close'])
        return df if len(df) >= 30 else None
    except Exception:
        return None


_PERIOD_MAP = {"1h": ("30d", "1h"), "4h": ("90d", "1h"), "1w": ("3y", "1wk"), "1d": ("2y", "1d"), "1mo": ("10y", "1mo")}

def veri_cek_toplu(hisseler: list, periyot_tipi: str) -> dict:
    """Tüm hisseleri tek yf.download çağrısıyla çeker. {hisse: df} döner."""
    if not hisseler:
        return {}
    period, interval = _PERIOD_MAP.get(periyot_tipi, ("1y", "1d"))
    tickers = " ".join(f"{h}.IS" for h in hisseler)
    try:
        raw = yf.download(tickers, period=period, interval=interval,
                          auto_adjust=True, progress=False, group_by='ticker',
                          timeout=30)
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


def _hizala_gunluk_ema(df_g, close_gunluk, _emas=None):
    """Günlük close serisinden hesaplanan EMAları df_g barlarına hizalar."""
    import numpy as np, pandas as pd

    def _to_days(idx):
        # Timezone uyumsuzluğunu önlemek için UTC'ye normalize et, sonra gün sayısına çevir
        dti = pd.DatetimeIndex(idx)
        if dti.tz is not None:
            dti = dti.tz_convert('UTC').tz_localize(None)
        return dti.asi8 // (86_400 * 10**9)

    g_days = _to_days(df_g.index)

    for p in (5, 8, 13, 21, 50):
        ema_s  = (_emas[p] if _emas and p in _emas else
                  close_gunluk.ewm(span=p, adjust=False).mean())
        e_days = _to_days(ema_s.index)
        e_vals = ema_s.values.astype(float)

        # Vectorized: single searchsorted call on whole array
        idxs   = np.searchsorted(e_days, g_days, side='right') - 1
        valid  = idxs >= 0
        result = np.full(len(df_g), np.nan)
        result[valid] = e_vals[idxs[valid]]
        df_g[f'EMA{p}'] = result


def sinyal_gucu_hesapla(r: dict) -> int:
    """Sinyal gücünü 1-10 arası puanlar."""
    puan = 0

    if r.get('macd_kesisim'):
        puan += 3 if r.get('macd_kesisim_kac_once', 2) == 0 else 2
    elif r.get('macd_yaklasan'):
        puan += 1

    hacim = r.get('hacim')
    if hacim:
        oran = hacim.get('hacim_orani', 1.0)
        puan += 1 if oran < 2 else (2 if oran < 3 else 3)

    if r.get('kutu'):
        puan += 2

    destek_tam = r.get('destek_uzeri') and r.get('destek_yakin') and r.get('destek_test')
    if destek_tam or r.get('dip_sinyal'):
        puan += 1

    ema_sir = r.get('ema_sir')
    if ema_sir:
        puan += 1
        if ema_sir.get('yeni'):
            puan += 1

    rsi = r.get('rsi', 50)
    if rsi < 35:
        puan += 1
    elif rsi > 65:
        puan -= 1

    if r.get('trend_sinyal') == 'AL':
        puan += 1

    rsi_div = r.get('rsi_div')
    if rsi_div:
        puan += 2 if rsi_div.get('guclu') else 1

    if r.get('ema_pull'):
        puan += 1

    if r.get('bol_sq'):
        puan += 1

    mum = r.get('mum')
    if mum:
        puan += 2 if mum.get('guclu') else 1

    if r.get('macd_olum'):
        puan -= 2

    if r.get('destek_kirildi'):
        puan -= 2

    return max(1, min(10, puan))


def sinyal_hesapla(df, periyot_tipi="1d", destek_gun_sayisi=3, close_gunluk=None, grafik=True):
    """
    Tüm indikatörleri hesaplar, destek filtresi uygular ve sinyal üretir.
    grafik=False → chart serisini atla (BacktestThread için hız optimizasyonu).
    Döndürür: dict (tüm değerler + genel_sinyal) veya None
    """
    if df is None or len(df) < 50:
        return None

    # df.copy() kaldırıldı — fonksiyon df'yi değiştirmiyor
    close = df['Close'].squeeze()
    high  = df['High'].squeeze()
    low   = df['Low'].squeeze()

    r = {}
    r['fiyat']   = round(float(close.iloc[-1]), 2)
    r['periyot'] = periyot_tipi

    # EMA dizileri — bir kez hesapla, hem sinyal hem grafik için yeniden kullan
    _emas = {p: close.ewm(span=p, adjust=False).mean() for p in (5, 8, 13, 21, 50)}

    # ── RSI — seri önbelleğe alınır; hem sinyal hem grafik kullanır ──
    rsi_seri = rsi_hesapla(close)
    rsi_val  = float(rsi_seri.iloc[-1])
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

    # ── MACD — seri önbelleğe alınır; hem sinyal hem grafik kullanır ──
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

    # MACD ölüm kesişimi: histogram pozitiften negatife geçti (son 2 mum)
    macd_olum     = False
    olum_kac_once = None
    if len(hist_arr) >= 4:
        for i in range(len(hist_arr) - 1, max(len(hist_arr) - 5, 0), -1):
            if hist_arr[i] < 0 and hist_arr[i - 1] >= 0:
                kac = len(hist_arr) - 1 - i
                if kac <= 1:
                    macd_olum     = True
                    olum_kac_once = kac
                break
    r['macd_olum']          = macd_olum
    r['macd_olum_kac_once'] = olum_kac_once

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
    # Dip son 18-3 gün arasında oluştuysa (çok eski veya çok yeni değil)
    dip_eski   = 3 <= (30 - dip_konum) <= 18
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

    # YOL 5: EMA sıralaması — önden hesaplanmış _emas'ı geç
    ema_sir = ema_siralanma_bul(close, _emas=_emas)
    r['ema_sir'] = ema_sir

    # YOL 6: RSI Bullish Diverjans — önden hesaplanan rsi_seri'yi geç
    rsi_div = rsi_diverjans_bul(close, rsi_seri=rsi_seri)
    r['rsi_div'] = rsi_div

    # YOL 7: EMA21 Pullback — önden hesaplanan _emas'ı geç
    ema_pull = ema_pullback_bul(close, _emas=_emas)
    r['ema_pull'] = ema_pull

    # YOL 8: Bollinger Band Sıkışması
    bol_sq = bollinger_squeeze_bul(close)
    r['bol_sq'] = bol_sq

    # YOL 9: Mum Formasyonu — destekler listesini geç
    mum = mum_formasyonu_bul(df, destekler=destekler)
    r['mum'] = mum

    # Destek kırılımı: fiyat en yakın desteğin belirgin altına geçmiş
    destek_kirildi = bool(destekler and r['fiyat'] < destekler[0] * 0.99)
    r['destek_kirildi'] = destek_kirildi

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

    kutu_ok      = bool(kutu)     and rsi_ok and not bearish
    macd_kes_ok  = macd_kesisim  and rsi_ok and not bearish
    macd_yak_ok  = macd_yaklasan and rsi_ok and not bearish
    hacim_ok     = bool(hacim)   and rsi_ok and not bearish
    ema_sir_ok   = bool(ema_sir) and rsi_ok and not bearish
    rsi_div_ok   = bool(rsi_div) and rsi_ok and not bearish
    ema_pull_ok  = bool(ema_pull) and rsi_ok and not bearish
    bol_sq_ok    = bool(bol_sq)  and rsi_ok and not bearish
    mum_ok       = bool(mum)     and rsi_ok and not bearish
    macd_olum_ok = macd_olum     and sat_puan > al_puan

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
    elif rsi_div_ok and macd_kes_ok:
        r['genel_sinyal'] = "DIV+MACD"
    elif macd_kes_ok:
        r['genel_sinyal'] = "MACD KESİŞİM"
    elif ema_sir_ok and ema_sir.get('yeni'):
        r['genel_sinyal'] = "EMA SIRALANMA"
    elif ema_pull_ok and macd_kes_ok:
        r['genel_sinyal'] = "EMA+MACD"
    elif macd_yak_ok:
        r['genel_sinyal'] = "MACD YAKLAŞIM"
    elif rsi_div_ok:
        r['genel_sinyal'] = "RSI DİVERJANS"
    elif ema_pull_ok:
        r['genel_sinyal'] = "EMA PULLBACK"
    elif bol_sq_ok and macd_val > 0:
        r['genel_sinyal'] = "BOL. SIKIŞMA"
    elif mum_ok and mum.get('guclu'):
        r['genel_sinyal']   = "YÜKSELİŞ FORMASYONU"
        r['mum_formasyon']  = mum.get('formasyon', '')
    elif destek_ok:
        r['genel_sinyal'] = "DESTEK AL"
    elif macd_olum_ok:
        r['genel_sinyal'] = "MACD ÖLÜ"
    elif destek_kirildi:
        r['genel_sinyal'] = "DESTEK KIRILDI"
    elif sat_puan >= 5.5 and sat_puan >= al_puan * 2.0:
        r['genel_sinyal'] = "GÜÇLÜ SAT"
    elif sat_puan >= 4.0 and sat_puan > al_puan * 1.2:
        r['genel_sinyal'] = "SAT"
    else:
        r['genel_sinyal'] = "NÖTR"

    # ── Grafik verisi (periyoda göre mum sayısı + EMA + MACD + RSI) ──────
    # grafik=False → BacktestThread'de atlanır (~9 EWM hesabı tasarruf)
    if grafik:
        _N = {"1h": 120, "4h": 120, "1d": 150, "1w": 100, "1mo": 80}.get(periyot_tipi, 120)
        df_g = df.tail(_N).copy()
        if periyot_tipi == "1d" or close_gunluk is None:
            for p in (5, 8, 13, 21, 50):
                df_g[f'EMA{p}'] = _emas[p].tail(_N).values
        else:
            _hizala_gunluk_ema(df_g, close_gunluk)
        df_g['RSI']       = rsi_seri.tail(_N).values
        df_g['MACD_LINE'] = macd_line.tail(_N).values
        df_g['MACD_SIG']  = macd_sig.tail(_N).values
        df_g['MACD_HIST'] = hist.tail(_N).values
        r['df_grafik'] = df_g

    r['sinyal_gucu'] = sinyal_gucu_hesapla(r)

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
