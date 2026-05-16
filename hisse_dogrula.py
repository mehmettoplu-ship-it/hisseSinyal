#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
TradingView BIST tarayıcısından tüm sembolleri çeker,
Yahoo Finance'de doğrular, gecerli_hisseler.py'ye yazar.
"""

import sys, io, json, time
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import requests
import yfinance as yf

# ────────────────────────────────────────────────────────
# 1. TradingView Scanner API'sinden tüm BIST sembollerini çek
# ────────────────────────────────────────────────────────

TV_URL = "https://scanner.tradingview.com/turkey/scan"
TV_HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Content-Type": "application/json",
    "Origin": "https://tr.tradingview.com",
    "Referer": "https://tr.tradingview.com/",
}

def tv_sembolleri_cek() -> list[str]:
    payload = {
        "filter":  [],
        "options": {"lang": "tr"},
        "symbols": {"query": {"types": []}, "tickers": []},
        "columns": ["name", "description"],
        "sort":    {"sortBy": "name", "sortOrder": "asc"},
        "range":   [0, 1500],
    }
    try:
        r = requests.post(TV_URL, headers=TV_HEADERS, json=payload, timeout=20)
        r.raise_for_status()
        data = r.json()
        semboller = []
        for row in data.get("data", []):
            s = row.get("s", "")          # "BIST:THYAO"  →  "THYAO"
            if ":" in s:
                s = s.split(":")[-1]
            # BIST sembolleri büyük harf, rakam veya nokta içerir; kısa olanlar geçerli
            if s and s.isalpha() and 2 <= len(s) <= 8:
                semboller.append(s)
        return sorted(set(semboller))
    except Exception as e:
        print(f"TradingView API hatası: {e}")
        return []

print("TradingView'dan semboller çekiliyor…")
tv_semboller = tv_sembolleri_cek()
print(f"  → {len(tv_semboller)} sembol bulundu\n")

if not tv_semboller:
    print("Sembol listesi boş, çıkılıyor.")
    sys.exit(1)

# ────────────────────────────────────────────────────────
# 2. Yahoo Finance'de doğrula
# ────────────────────────────────────────────────────────
gecerli  = []
gecersiz = []
toplam   = len(tv_semboller)

print(f"Yahoo Finance doğrulaması başlıyor ({toplam} sembol)…\n")

for i, sembol in enumerate(tv_semboller, 1):
    try:
        df = yf.download(
            f"{sembol}.IS", period="5d", interval="1d",
            auto_adjust=True, progress=False,
        )
        if df is not None and not df.empty:
            fiyat = float(df["Close"].iloc[-1])
            if fiyat > 0:
                gecerli.append(sembol)
                sys.stdout.write(
                    f"\r  [{i:3d}/{toplam}] {sembol:8s} ✓  {fiyat:>10.2f} TL   ")
                sys.stdout.flush()
                continue
    except Exception:
        pass
    gecersiz.append(sembol)
    sys.stdout.write(f"\r  [{i:3d}/{toplam}] {sembol:8s} ✗                    ")
    sys.stdout.flush()

print(f"\n\n{'─'*50}")
print(f"Sonuç  :  {len(gecerli)} geçerli  /  {len(gecersiz)} geçersiz")
if gecersiz:
    print(f"Geçersiz ({len(gecersiz)}): {', '.join(gecersiz[:30])}"
          + ("…" if len(gecersiz) > 30 else ""))

# ────────────────────────────────────────────────────────
# 3. gecerli_hisseler.py'ye yaz
# ────────────────────────────────────────────────────────
with open("gecerli_hisseler.py", "w", encoding="utf-8") as f:
    f.write("# Otomatik oluşturuldu — TradingView + Yahoo Finance doğrulaması\n")
    f.write(f"# Toplam: {len(gecerli)} hisse\n\n")
    f.write("GECERLI_HISSELER = [\n")
    for j in range(0, len(gecerli), 8):
        satir = gecerli[j:j+8]
        f.write("    " + ", ".join(f'"{s}"' for s in satir) + ",\n")
    f.write("]\n")

print(f"\nKaydedildi: gecerli_hisseler.py  ({len(gecerli)} hisse)")
