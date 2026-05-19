
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BIST Sinyal Tarayıcısı — Masaüstü Uygulaması
PyQt6 + Matplotlib dark tema
"""

import sys
import os
import json
import winsound
from datetime import datetime

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QListWidget, QListWidgetItem, QProgressBar,
    QComboBox, QTextEdit, QFrame, QGridLayout, QSplitter,
    QSizePolicy, QStatusBar, QScrollArea, QLineEdit,
    QDialog, QTableWidget, QTableWidgetItem, QHeaderView,
    QMessageBox, QInputDialog, QMenu, QSystemTrayIcon,
    QTabWidget, QCheckBox,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer, QSize, QUrl
from PyQt6.QtGui import QFont, QColor, QClipboard, QIcon, QAction, QDesktopServices

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import matplotlib.patches as mpatches
import matplotlib.ticker as mticker
import numpy as np

from tarayici import (
    BIST_30, BIST_HISSELER, BIST_TUMHISSELER, PERIYOT_ADLARI,
    veri_cek, veri_cek_toplu, sinyal_hesapla, bildirim_metni, _hizala_gunluk_ema
)

# ═══════════════════════════════════════════════════════════
# Renk Sabitleri  —  iOS / macOS dark mode paleti
# ═══════════════════════════════════════════════════════════
C_BG        = "#000000"   # tam siyah (iOS zemin)
C_CARD      = "#1c1c1e"   # kart yüzeyi
C_CARD2     = "#2c2c2e"   # ikinci yüzey
C_BORDER    = "#38383a"   # ince ayırıcı
C_HEADER    = "#1c1c1e"   # toolbar / header
C_TEXT      = "#ffffff"   # birincil metin
C_TEXT2     = "#ebebf5"   # ikincil metin
C_MUTED     = "#8e8e93"   # soluk metin
C_BLUE      = "#0a84ff"   # iOS mavi
C_GREEN     = "#30d158"   # iOS yeşil
C_RED       = "#ff453a"   # iOS kırmızı
C_ORANGE    = "#ff9f0a"   # iOS turuncu
C_GREEN_DIM = "#0d2e18"   # yeşil dim
C_RED_DIM   = "#2d0f0f"   # kırmızı dim

# ═══════════════════════════════════════════════════════════
# Favori Yöneticisi
# ═══════════════════════════════════════════════════════════
class FavorilerYoneticisi:
    DOSYA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "favoriler.json")

    def __init__(self):
        self._veri: dict = {}
        self._yukle()

    def _yukle(self):
        yedek = self.DOSYA + ".bak"
        for yol in (self.DOSYA, yedek):
            if os.path.exists(yol):
                try:
                    with open(yol, 'r', encoding='utf-8') as f:
                        oku = json.load(f)
                    if isinstance(oku, dict):
                        self._veri = oku
                        return
                except Exception:
                    continue  # bozuksa yedeğe geç

    def _kaydet(self):
        # Atomik yaz: önce .tmp, sonra yeniden adlandır
        tmp = self.DOSYA + ".tmp"
        yedek = self.DOSYA + ".bak"
        try:
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(self._veri, f, ensure_ascii=False, indent=2)
            # Mevcut dosyayı yedekle
            if os.path.exists(self.DOSYA):
                if os.path.exists(yedek):
                    os.remove(yedek)
                os.rename(self.DOSYA, yedek)
            os.rename(tmp, self.DOSYA)
        except Exception:
            pass  # yazma hatası veriyi bellekte kaybettirme

    def ekle(self, hisse: str, fiyat: float, periyot: str, sinyal: str):
        self._veri[hisse] = {
            'tarih':  datetime.now().strftime('%d.%m.%Y %H:%M'),
            'fiyat':  round(fiyat, 2),
            'periyot': periyot,
            'sinyal': sinyal,
        }
        self._kaydet()

    def cikar(self, hisse: str):
        if hisse in self._veri:
            del self._veri[hisse]
            self._kaydet()

    def toggle(self, hisse: str, fiyat: float, periyot: str, sinyal: str) -> bool:
        if hisse in self._veri:
            self.cikar(hisse)
            return False
        self.ekle(hisse, fiyat, periyot, sinyal)
        return True

    def favori_mi(self, hisse: str) -> bool:
        return hisse in self._veri

    def al(self, hisse: str) -> dict | None:
        return self._veri.get(hisse)

    def hepsi(self) -> dict:
        return dict(self._veri)


FAVORILER = FavorilerYoneticisi()


# ═══════════════════════════════════════════════════════════
# Sinyal Geçmişi
# ═══════════════════════════════════════════════════════════
class SinyalGecmisi:
    DOSYA    = "sinyal_gecmisi.json"
    MAX_KAYIT = 600

    def kaydet(self, hisse, sinyal, fiyat, periyot):
        kayitlar = self._yukle_ham()
        kayitlar.insert(0, {
            'tarih':   datetime.now().strftime('%Y-%m-%d %H:%M'),
            'hisse':   hisse,
            'sinyal':  sinyal,
            'fiyat':   round(float(fiyat), 2),
            'periyot': periyot,
        })
        kayitlar = kayitlar[:self.MAX_KAYIT]
        tmp = self.DOSYA + ".tmp"
        try:
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(kayitlar, f, ensure_ascii=False)
            os.replace(tmp, self.DOSYA)
        except Exception:
            pass

    def _yukle_ham(self):
        try:
            with open(self.DOSYA, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return []

    def yukle(self, limit=200):
        return self._yukle_ham()[:limit]


GECMIS = SinyalGecmisi()


# ═══════════════════════════════════════════════════════════
# Alarm Yöneticisi
# ═══════════════════════════════════════════════════════════
class AlarmYoneticisi:
    DOSYA = "alarmlar.json"

    def __init__(self):
        self._alarmlar = self._yukle()

    def _yukle(self):
        try:
            with open(self.DOSYA, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            return {}

    def _kaydet(self):
        try:
            with open(self.DOSYA, 'w', encoding='utf-8') as f:
                json.dump(self._alarmlar, f, ensure_ascii=False)
        except Exception:
            pass

    def ekle(self, hisse, hedef):
        self._alarmlar[hisse] = round(float(hedef), 2)
        self._kaydet()

    def kaldir(self, hisse):
        self._alarmlar.pop(hisse, None)
        self._kaydet()

    def listesi(self):
        return dict(self._alarmlar)

    def alarm_var_mi(self, hisse):
        return hisse in self._alarmlar

    def hedef(self, hisse):
        return self._alarmlar.get(hisse)


ALARMLAR = AlarmYoneticisi()


# ═══════════════════════════════════════════════════════════
# Sabitleme Yöneticisi
# ═══════════════════════════════════════════════════════════
class SabitleYoneticisi:
    DOSYA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sabitlenmis.json")

    def __init__(self):
        self._set: set = set()
        self._yukle()

    def _yukle(self):
        try:
            with open(self.DOSYA, 'r', encoding='utf-8') as f:
                data = json.load(f)
            if isinstance(data, list):
                self._set = set(data)
        except Exception:
            pass

    def _kaydet(self):
        tmp = self.DOSYA + ".tmp"
        try:
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(sorted(self._set), f, ensure_ascii=False)
            os.replace(tmp, self.DOSYA)
        except Exception:
            pass

    def toggle(self, hisse: str) -> bool:
        if hisse in self._set:
            self._set.discard(hisse)
            self._kaydet()
            return False
        self._set.add(hisse)
        self._kaydet()
        return True

    def sabitlenen(self, hisse: str) -> bool:
        return hisse in self._set


SABITLENMIS = SabitleYoneticisi()


# ═══════════════════════════════════════════════════════════
# Telegram Ayarları
# ═══════════════════════════════════════════════════════════
class TelegramAyarlari:
    DOSYA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "telegram_ayar.json")

    def __init__(self):
        self._cfg = {
            'token': '', 'chat_id': '', 'aktif': False,
            'guclu_sinyal': True, 'min_guc': 6, 'tekrar_saat': 4,
        }
        self._yukle()
        self._gonderilen: dict = {}   # (hisse, sinyal, periyot) → datetime

    def _yukle(self):
        try:
            with open(self.DOSYA, 'r', encoding='utf-8') as f:
                self._cfg.update(json.load(f))
        except Exception:
            pass

    def kaydet(self):
        try:
            with open(self.DOSYA, 'w', encoding='utf-8') as f:
                json.dump(self._cfg, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def gonder(self, mesaj: str) -> bool:
        if not self._cfg.get('aktif') or not self._cfg.get('token') or not self._cfg.get('chat_id'):
            return False
        try:
            import requests as _req
            url = f"https://api.telegram.org/bot{self._cfg['token']}/sendMessage"
            r = _req.post(url, json={
                'chat_id': self._cfg['chat_id'],
                'text': mesaj, 'parse_mode': 'HTML',
            }, timeout=6)
            return r.status_code == 200
        except Exception:
            return False

    def zaten_gonderildi(self, hisse: str, sinyal: str, periyot: str) -> bool:
        """Aynı (hisse, sinyal, periyot) tekrar_saat içinde gönderildiyse True döner."""
        from datetime import timedelta
        anahtar = (hisse, sinyal, periyot)
        son = self._gonderilen.get(anahtar)
        if son is None:
            return False
        return (datetime.now() - son) < timedelta(hours=self._cfg.get('tekrar_saat', 4))

    def gonderim_kaydet(self, hisse: str, sinyal: str, periyot: str):
        self._gonderilen[(hisse, sinyal, periyot)] = datetime.now()

    def gonder_foto(self, mesaj: str, foto_bytes: bytes) -> bool:
        if not self._cfg.get('aktif') or not self._cfg.get('token') or not self._cfg.get('chat_id'):
            return False
        try:
            import requests as _req
            url = f"https://api.telegram.org/bot{self._cfg['token']}/sendPhoto"
            r = _req.post(url, data={
                'chat_id': self._cfg['chat_id'],
                'caption': mesaj,
                'parse_mode': 'HTML',
            }, files={'photo': ('chart.png', foto_bytes, 'image/png')}, timeout=15)
            return r.status_code == 200
        except Exception:
            return False

    def set(self, **kw):
        self._cfg.update(kw)
        self.kaydet()

    @property
    def aktif(self):       return self._cfg.get('aktif', False)
    @property
    def token(self):       return self._cfg.get('token', '')
    @property
    def chat_id(self):     return self._cfg.get('chat_id', '')
    @property
    def min_guc(self):     return int(self._cfg.get('min_guc', 6))
    @property
    def guclu_sinyal(self): return self._cfg.get('guclu_sinyal', True)
    @property
    def tekrar_saat(self):  return int(self._cfg.get('tekrar_saat', 4))


TELEGRAM = TelegramAyarlari()


# ═══════════════════════════════════════════════════════════
# Portföy Yöneticisi
# ═══════════════════════════════════════════════════════════
class PortfoyYoneticisi:
    DOSYA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "portfoy.json")

    def __init__(self):
        self._aktif: dict  = {}
        self._gecmis: list = []
        self._yukle()

    def _yukle(self):
        try:
            with open(self.DOSYA, 'r', encoding='utf-8') as f:
                veri = json.load(f)
            self._aktif  = veri.get('aktif', {})
            self._gecmis = veri.get('gecmis', [])
        except Exception:
            pass

    def _kaydet(self):
        tmp = self.DOSYA + ".tmp"
        try:
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump({'aktif': self._aktif, 'gecmis': self._gecmis},
                          f, ensure_ascii=False, indent=2)
            os.replace(tmp, self.DOSYA)
        except Exception:
            pass

    def pozisyon_ac(self, hisse: str, giris: float, lot: int = 1):
        self._aktif[hisse] = {
            'giris': round(giris, 2),
            'tarih': datetime.now().strftime('%d.%m.%Y %H:%M'),
            'lot':   lot,
        }
        self._kaydet()

    def pozisyon_kapat(self, hisse: str, cikis: float):
        if hisse not in self._aktif:
            return
        p   = self._aktif.pop(hisse)
        kar = (cikis - p['giris']) / p['giris'] * 100
        self._gecmis.insert(0, {
            'hisse':        hisse,
            'giris':        p['giris'],
            'cikis':        round(cikis, 2),
            'lot':          p['lot'],
            'tarih_giris':  p['tarih'],
            'tarih_cikis':  datetime.now().strftime('%d.%m.%Y %H:%M'),
            'kar_yuzde':    round(kar, 2),
        })
        self._kaydet()

    def aktif_listesi(self):      return dict(self._aktif)
    def gecmis_listesi(self):     return list(self._gecmis)
    def pozisyon_var_mi(self, h): return h in self._aktif
    def pozisyon(self, h):        return self._aktif.get(h)

    def stop_hedef_ayarla(self, hisse: str, stop_pct: float, hedef_pct: float):
        if hisse in self._aktif:
            self._aktif[hisse]["stop_pct"] = stop_pct
            self._aktif[hisse]["hedef_pct"] = hedef_pct
            self._kaydet()


PORTFOY = PortfoyYoneticisi()


# ═══════════════════════════════════════════════════════════
# Risk Ayarları
# ═══════════════════════════════════════════════════════════
class RiskAyarlari:
    DOSYA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "risk_ayar.json")

    def __init__(self):
        self._cfg = {'sermaye': 10000.0, 'max_risk_pct': 2.0}
        self._yukle()

    def _yukle(self):
        try:
            with open(self.DOSYA, 'r', encoding='utf-8') as f:
                self._cfg.update(json.load(f))
        except Exception:
            pass

    def kaydet(self):
        try:
            with open(self.DOSYA, 'w', encoding='utf-8') as f:
                json.dump(self._cfg, f, ensure_ascii=False)
        except Exception:
            pass

    def set(self, **kw):
        self._cfg.update(kw)
        self.kaydet()

    @property
    def sermaye(self):      return float(self._cfg.get('sermaye', 10000))
    @property
    def max_risk_pct(self): return float(self._cfg.get('max_risk_pct', 2.0))


RISK_AYAR = RiskAyarlari()


# ═══════════════════════════════════════════════════════════
# Backtest Sonuçları Yöneticisi
# ═══════════════════════════════════════════════════════════
class BacktestSonuclariYoneticisi:
    DOSYA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backtest_sonuclari.json")

    def __init__(self):
        self._veri: dict = {}
        self._yukle()

    def _yukle(self):
        try:
            with open(self.DOSYA, 'r', encoding='utf-8') as f:
                self._veri = json.load(f)
        except Exception:
            pass

    def kaydet_sonuc(self, hisse: str, periyot: str, ist: dict):
        self._veri.setdefault(hisse, {})[periyot] = {
            'toplam':  ist.get('toplam', 0),
            'oran':    ist.get('oran', 0),
            'ort_kar': ist.get('ort_kar', 0),
            'tarih':   datetime.now().strftime('%d.%m.%Y'),
        }
        tmp = self.DOSYA + ".tmp"
        try:
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(self._veri, f, ensure_ascii=False)
            os.replace(tmp, self.DOSYA)
        except Exception:
            pass

    def al(self, hisse: str, periyot: str) -> dict | None:
        return self._veri.get(hisse, {}).get(periyot)


BACKTEST_SONUCLARI = BacktestSonuclariYoneticisi()


# ═══════════════════════════════════════════════════════════
# Notlar Yöneticisi
# ═══════════════════════════════════════════════════════════
class NotlarYoneticisi:
    DOSYA = os.path.join(os.path.dirname(__file__), "notlar.json")

    def __init__(self):
        self._data = {}
        self._yukle()

    def _yukle(self):
        try:
            with open(self.DOSYA, encoding="utf-8") as f:
                self._data = json.load(f)
        except Exception:
            self._data = {}

    def _kaydet(self):
        tmp = self.DOSYA + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.DOSYA)

    def kaydet(self, hisse: str, metin: str):
        self._data[hisse] = {"metin": metin, "tarih": datetime.now().strftime("%d.%m.%Y %H:%M")}
        self._kaydet()

    def sil(self, hisse: str):
        self._data.pop(hisse, None)
        self._kaydet()

    def al(self, hisse: str) -> str:
        return self._data.get(hisse, {}).get("metin", "")

    def var_mi(self, hisse: str) -> bool:
        return hisse in self._data and bool(self._data[hisse].get("metin", ""))


NOTLAR = NotlarYoneticisi()


# ═══════════════════════════════════════════════════════════
# Çizgi Yöneticisi
# ═══════════════════════════════════════════════════════════
class CizgiYoneticisi:
    DOSYA = os.path.join(os.path.dirname(__file__), "cizgiler.json")

    def __init__(self):
        self._data = {}
        self._yukle()

    def _yukle(self):
        try:
            with open(self.DOSYA, encoding="utf-8") as f:
                self._data = json.load(f)
        except Exception:
            self._data = {}

    def _kaydet(self):
        tmp = self.DOSYA + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.DOSYA)

    def _anahtar(self, hisse: str, periyot: str) -> str:
        return f"{hisse}_{periyot}"

    def yukle(self, hisse: str, periyot: str) -> list:
        return self._data.get(self._anahtar(hisse, periyot), [])

    def ekle(self, hisse: str, periyot: str, x1, y1, x2, y2):
        key = self._anahtar(hisse, periyot)
        if key not in self._data:
            self._data[key] = []
        self._data[key].append({"x1": x1, "y1": y1, "x2": x2, "y2": y2,
                                 "tarih": datetime.now().strftime("%d.%m.%Y %H:%M")})
        self._kaydet()

    def sil(self, hisse: str, periyot: str, idx: int):
        key = self._anahtar(hisse, periyot)
        if key in self._data and 0 <= idx < len(self._data[key]):
            self._data[key].pop(idx)
            self._kaydet()

    def tumunu_sil(self, hisse: str, periyot: str):
        key = self._anahtar(hisse, periyot)
        if key in self._data:
            del self._data[key]
            self._kaydet()


CIZGILER = CizgiYoneticisi()


# ═══════════════════════════════════════════════════════════
# Güncelleme Kontrol Thread
# ═══════════════════════════════════════════════════════════
class GuncellemeFetchThread(QThread):
    sonuc = pyqtSignal(str, str)   # (son_sha, commit_mesaji)
    hata  = pyqtSignal()

    def run(self):
        try:
            import urllib.request, json as _json
            REPO_URL = "https://api.github.com/repos/mehmettoplu-ship-it/hisseSinyal/commits?per_page=1"
            req = urllib.request.Request(REPO_URL, headers={"User-Agent": "BISTScanner/1.0"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                veriler = _json.loads(resp.read().decode())
            son_sha = veriler[0]["sha"][:7]
            mesaj = veriler[0]["commit"]["message"].split("\n")[0][:60]
            yerel_sha = ""
            dosya = os.path.join(os.path.dirname(__file__), "versiyon.json")
            try:
                with open(dosya, encoding="utf-8") as f:
                    yerel_sha = _json.load(f).get("sha", "")
            except Exception:
                pass
            if son_sha != yerel_sha:
                self.sonuc.emit(son_sha, mesaj)
        except Exception:
            self.hata.emit()


# ═══════════════════════════════════════════════════════════
# Alarm Kontrol Thread
# ═══════════════════════════════════════════════════════════
class AlarmThread(QThread):
    tetiklendi = pyqtSignal(str, float, float)   # hisse, hedef, guncel

    def __init__(self):
        super().__init__()
        self._dur = False

    def dur(self):
        self._dur = True

    def _fiyat_cek(self, hisse: str):
        import yfinance as yf
        try:
            df = yf.download(f"{hisse}.IS", period="2d", interval="1h",
                             auto_adjust=True, progress=False)
            if df is not None and not df.empty:
                from tarayici import _sutunlari_duzenle
                df = _sutunlari_duzenle(df)
                return float(df["Close"].iloc[-1])
        except Exception:
            pass
        return None

    def run(self):
        import time
        while not self._dur:
            # Fiyat alarmları
            alarmlar = list(ALARMLAR.listesi().items())
            for hisse, hedef in alarmlar:
                if self._dur:
                    break
                guncel = self._fiyat_cek(hisse)
                if guncel is not None and guncel >= hedef:
                    self.tetiklendi.emit(hisse, hedef, guncel)

            # Portföy stop/hedef alarmları
            try:
                aktif = PORTFOY.aktif_listesi()
                for hisse, pos in aktif.items():
                    if self._dur:
                        break
                    stop_pct  = pos.get("stop_pct", 0)
                    hedef_pct = pos.get("hedef_pct", 0)
                    if not stop_pct and not hedef_pct:
                        continue
                    giris = pos.get("giris", 0)
                    if not giris:
                        continue
                    guncel = self._fiyat_cek(hisse)
                    if guncel is None:
                        continue
                    if stop_pct and guncel <= giris * (1 - stop_pct / 100):
                        self.tetiklendi.emit(f"STOP:{hisse}", giris * (1 - stop_pct / 100), guncel)
                    elif hedef_pct and guncel >= giris * (1 + hedef_pct / 100):
                        self.tetiklendi.emit(f"HEDEF:{hisse}", giris * (1 + hedef_pct / 100), guncel)
            except Exception:
                pass

            # 1 dakika bekle — 1'er saniyelik uykularla iptal edilebilir
            for _ in range(60):
                if self._dur:
                    break
                time.sleep(1)


SINYAL_RENK = {
    "KUTU+MACD":      "#fbbf24",  # parlak altın — en güçlü kombinasyon
    "HACİM+MACD":     "#4ade80",  # parlak yeşil — hacim kırılımı + macd
    "DESTEK+MACD":    "#2dd4bf",  # parlak teal — destek + macd teyidi
    "DIV+MACD":       "#a855f7",  # mor — rsi diverjans + macd
    "KUTU AL":        "#f59e0b",  # amber — konsolidasyon kutusu
    "HACİM KIRILIM":  "#fcd34d",  # sarı-amber — hacim kırılımı
    "MACD KESİŞİM":   "#38bdf8",  # sky blue — taze kesişim
    "EMA SIRALANMA":  "#86efac",  # açık yeşil — ema dizilimi
    "EMA+MACD":       "#22d3ee",  # cyan — ema pullback + macd
    "MACD YAKLAŞIM":  "#818cf8",  # indigo — yaklaşıyor
    "RSI DİVERJANS":  "#c084fc",  # açık mor — bullish diverjans
    "EMA PULLBACK":   "#5eead4",  # açık teal — ema21 geri çekilme
    "BOL. SIKIŞMA":   "#eab308",  # sarı — bant sıkışması
    "YÜKSELİŞ FORMASYONU": "#fb923c",  # turuncu — mum formasyonu grubu
    "DESTEK AL":      "#34d399",  # yeşil — destekte tutunma
    "MACD ÖLÜ":      C_RED,
    "DESTEK KIRILDI": "#ef4444",
    "GÜÇLÜ SAT":     C_RED,
    "SAT":           C_RED,
    "NÖTR":          C_MUTED,
}
C_KUTU = "#f59e0b"  # amber — kutu konsolidasyon rengi

# Sinyal badge arka plan renkleri
_SINYAL_BG = {
    "KUTU+MACD":      "#5a3c00",
    "HACİM+MACD":     "#064e3b",
    "DESTEK+MACD":    "#0c3d38",
    "DIV+MACD":       "#4a1042",
    "KUTU AL":        "#6b4c00",
    "HACİM KIRILIM":  "#713f12",
    "MACD KESİŞİM":   "#0c3547",
    "EMA SIRALANMA":  "#14532d",
    "EMA+MACD":       "#0c3747",
    "MACD YAKLAŞIM":  "#1e1b4b",
    "RSI DİVERJANS":  "#3b1762",
    "EMA PULLBACK":   "#0f3834",
    "BOL. SIKIŞMA":   "#422006",
    "YÜKSELİŞ FORMASYONU": "#431407",
    "DESTEK AL":      "#064e3b",
    "MACD ÖLÜ":      "#5c1111",
    "DESTEK KIRILDI": "#450a0a",
    "GÜÇLÜ SAT":     "#5c1111",
    "SAT":           C_RED_DIM,
}

def sinyal_bg(genel: str) -> str:
    return _SINYAL_BG.get(genel, C_HEADER)


def skor_kirilim(sonuc: dict) -> list:
    """Aktif skor bileşenlerini [(etiket, puan, renk)] olarak döner."""
    p = []

    if sonuc.get('macd_kesisim'):
        pts = 3 if sonuc.get('macd_kesisim_kac_once', 2) == 0 else 2
        p.append(("MACD Kes.", pts, "#38bdf8"))
    elif sonuc.get('macd_yaklasan'):
        p.append(("MACD Yak.", 1, "#818cf8"))

    hacim = sonuc.get('hacim')
    if hacim:
        oran = hacim.get('hacim_orani', 1.0)
        pts  = 1 if oran < 2 else (2 if oran < 3 else 3)
        p.append((f"Hacim {oran:.1f}×", pts, "#ff9f0a"))

    if sonuc.get('kutu'):
        p.append(("Kutu", 2, "#f59e0b"))

    destek_tam = (sonuc.get('destek_uzeri') and
                  sonuc.get('destek_yakin') and sonuc.get('destek_test'))
    if destek_tam or sonuc.get('dip_sinyal'):
        p.append(("Destek", 1, "#34d399"))

    ema_sir = sonuc.get('ema_sir')
    if ema_sir:
        pts = 2 if ema_sir.get('yeni') else 1
        etiket = "EMA Sır.✨" if ema_sir.get('yeni') else "EMA Sır."
        p.append((etiket, pts, "#5b9cf6"))

    rsi = sonuc.get('rsi', 50)
    if rsi < 35:
        p.append(("RSI Düşük", 1, C_GREEN))
    elif rsi > 65:
        p.append(("RSI Yüksek", -1, C_RED))

    if sonuc.get('trend_sinyal') == 'AL':
        p.append(("Trend ↑", 1, "#22d3ee"))

    rsi_div = sonuc.get('rsi_div')
    if rsi_div:
        pts = 2 if rsi_div.get('guclu') else 1
        p.append(("RSI Div.", pts, "#c084fc"))

    if sonuc.get('ema_pull'):
        p.append(("EMA Pull.", 1, "#67e8f9"))

    if sonuc.get('bol_sq'):
        p.append(("Bol.Sık.", 1, "#eab308"))

    mum = sonuc.get('mum')
    if mum:
        pts = 2 if mum.get('guclu') else 1
        p.append((mum.get('formasyon', 'Mum'), pts, "#fb923c"))

    if sonuc.get('macd_olum'):
        p.append(("MACD Ölüm", -2, C_RED))

    if sonuc.get('destek_kirildi'):
        p.append(("D. Kırıldı", -2, C_RED))

    return p


def _seg_btn_stili(aktif: bool) -> str:
    bg, fg = ("#ffffff", "#000000") if aktif else ("transparent", C_MUTED)
    return (f"QPushButton{{background:{bg};color:{fg};border:none;"
            f"border-radius:7px;font-weight:{'600' if aktif else '400'};"
            f"font-size:12px;padding:0;}}"
            f"QPushButton:hover{{background:#48484a;color:{C_TEXT};padding:0;}}")

# ═══════════════════════════════════════════════════════════
# Dark QSS Stylesheet
# ═══════════════════════════════════════════════════════════
DARK_QSS = f"""
QMainWindow, QWidget, QFrame, QScrollArea {{
    background-color: {C_BG};
    color: {C_TEXT};
    font-family: 'Segoe UI';
    font-size: 13px;
}}
QSplitter::handle {{
    background-color: {C_BORDER};
    width: 1px;
}}
QListWidget {{
    background-color: {C_CARD};
    border: none;
    border-radius: 12px;
    outline: none;
    padding: 4px;
}}
QListWidget::item {{
    border-radius: 8px;
    margin: 1px 0;
}}
QListWidget::item:selected {{
    background-color: #0a84ff22;
}}
QListWidget::item:hover {{
    background-color: {C_CARD2};
}}
QPushButton {{
    background-color: {C_GREEN};
    color: white;
    border: none;
    border-radius: 10px;
    padding: 8px 20px;
    font-weight: 600;
    font-size: 13px;
}}
QPushButton:hover {{ background-color: #34e35e; }}
QPushButton:disabled {{ background-color: {C_CARD2}; color: {C_MUTED}; }}
QPushButton#stopBtn   {{ background-color: {C_RED}; border-radius: 10px; }}
QPushButton#stopBtn:hover {{ background-color: #ff6961; }}
QPushButton#stopBtn:disabled {{ background-color: {C_CARD2}; color: {C_MUTED}; }}
QPushButton#copyBtn   {{ background-color: {C_CARD2}; border-radius: 8px; padding: 6px 14px; }}
QPushButton#copyBtn:hover {{ background-color: #48484a; }}
QComboBox {{
    background-color: {C_CARD2};
    color: {C_TEXT};
    border: none;
    border-radius: 8px;
    padding: 5px 10px;
    min-width: 90px;
}}
QComboBox::drop-down {{ border: none; }}
QComboBox QAbstractItemView {{
    background-color: {C_CARD};
    color: {C_TEXT};
    selection-background-color: {C_BLUE};
    border-radius: 8px;
}}
QProgressBar {{
    background-color: {C_CARD2};
    border: none;
    border-radius: 8px;
    height: 22px;
    text-align: center;
    font-size: 11px;
    font-weight: 700;
    color: {C_TEXT};
}}
QProgressBar::chunk {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 #1a7a5e, stop:0.6 {C_GREEN}, stop:1 #5effa8);
    border-radius: 8px;
}}
QTextEdit {{
    background-color: {C_CARD};
    color: {C_TEXT};
    border: none;
    border-radius: 10px;
    font-family: 'SF Mono', 'Consolas';
    font-size: 12px;
    padding: 10px;
}}
QScrollBar:vertical {{
    background: transparent;
    width: 6px;
    border-radius: 3px;
}}
QScrollBar::handle:vertical {{
    background: {C_BORDER};
    border-radius: 3px;
    min-height: 30px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{ height: 0; }}
QStatusBar {{ background-color: {C_CARD}; color: {C_MUTED}; font-size: 11px; border-top: 1px solid {C_BORDER}; }}
QLabel#hisseAd  {{ font-size: 26px; font-weight: 700; color: {C_TEXT}; letter-spacing: 0.5px; }}
QLabel#fiyatLbl {{ font-size: 20px; font-weight: 500; color: {C_TEXT2}; }}
QLabel#gecikme  {{ font-size: 11px; color: {C_MUTED}; }}
QLineEdit {{
    background-color: {C_CARD2};
    color: {C_TEXT};
    border: none;
    border-radius: 8px;
    padding: 0 10px;
    font-size: 13px;
    selection-background-color: {C_BLUE};
}}
QLineEdit:focus {{ background-color: {C_CARD2}; border: 1px solid {C_BLUE}; }}
"""

# ═══════════════════════════════════════════════════════════
# Gösterge Kartı (RSI, MACD, vb.)
# ═══════════════════════════════════════════════════════════
class GostergekKart(QFrame):
    def __init__(self, baslik, deger_str, sinyal, yorum):
        super().__init__()
        self.setFixedHeight(70)
        if sinyal == "AL":
            accent = C_GREEN
        elif sinyal == "SAT":
            accent = C_RED
        else:
            accent = C_CARD2
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {C_CARD};
                border: none;
                border-radius: 10px;
                border-left: 3px solid {accent};
            }}
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 7, 10, 7)
        layout.setSpacing(3)

        ust = QHBoxLayout()
        lbl_baslik = QLabel(baslik.split('  ')[0])   # kısa isim ("RSI", "MACD" vs.)
        lbl_baslik.setStyleSheet(
            f"color:{C_MUTED}; font-size:10px; font-weight:500; "
            f"background:transparent; border:none; letter-spacing:0.5px;")
        lbl_deger  = QLabel(deger_str)
        lbl_deger.setStyleSheet(
            f"color:{C_TEXT}; font-size:16px; font-weight:700; "
            f"background:transparent; border:none;")
        ust.addWidget(lbl_baslik)
        ust.addStretch()
        ust.addWidget(lbl_deger)
        layout.addLayout(ust)

        if sinyal == "AL":
            bg, renk = C_GREEN_DIM, C_GREEN
        elif sinyal == "SAT":
            bg, renk = C_RED_DIM, C_RED
        else:
            bg, renk = "#2c2c2e", C_MUTED
        metin = sinyal if sinyal != "NÖTR" else yorum
        lbl_badge = QLabel(metin)
        lbl_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_badge.setStyleSheet(f"""
            background-color: {bg};
            color: {renk};
            border-radius: 5px;
            padding: 2px 0;
            font-size: 10px;
            font-weight: 600;
            border: none;
        """)
        layout.addWidget(lbl_badge)

# ═══════════════════════════════════════════════════════════
# Telegram için PNG grafik üretici (Qt gerektirmez)
# ═══════════════════════════════════════════════════════════
def _telegram_grafik_png(sonuc: dict) -> bytes | None:
    """df_grafik verisinden PNG bayt dizisi üretir (Qt canvas olmadan)."""
    from io import BytesIO
    from matplotlib.figure import Figure

    df_g      = sonuc.get('df_grafik')
    destekler = sonuc.get('destekler', [])[:3]
    direncler = sonuc.get('direncler', [])[:3]
    hisse     = sonuc.get('hisse', '')
    kutu      = sonuc.get('kutu')

    if df_g is None or df_g.empty:
        return None

    BG_FRAME = "#0d1f30"; BG_CHART = "#0b1829"
    C_UP = "#26a69a"; C_DOWN = "#ef5350"
    C_DESTEK = "#26a69a"; C_DIRENC = "#ef5350"
    C_KUTU = "#f59e0b"; C_GRID = "#1a2e42"; C_AXIS = "#546e7a"
    EMA_STILLER = [(5,"#5b9cf6",1.3),(8,"#fb923c",1.3),(13,"#22d3ee",1.2),(21,"#f87171",1.2),(50,"#c084fc",1.5)]

    fig    = Figure(figsize=(10, 6), facecolor=BG_FRAME)
    ax     = fig.add_axes([0.02, 0.18, 0.78, 0.76])
    ax_vol = fig.add_axes([0.02, 0.04, 0.78, 0.12])

    for a in (ax, ax_vol):
        a.set_facecolor(BG_CHART)
        for side in ('top', 'left', 'bottom'):
            a.spines[side].set_visible(False)
        a.spines['right'].set_color(C_GRID)
        a.yaxis.set_label_position('right'); a.yaxis.tick_right(); a.set_axisbelow(True)

    ax.tick_params(axis='y', colors=C_AXIS, labelsize=8, length=0, pad=4)
    ax.tick_params(axis='x', bottom=False, labelbottom=False)
    ax_vol.tick_params(axis='y', colors=C_AXIS, labelsize=6, length=0, pad=3)
    ax_vol.tick_params(axis='x', colors=C_AXIS, labelsize=7, length=0, pad=3)
    ax.yaxis.grid(True,     color=C_GRID, linewidth=0.35, linestyle='--', alpha=0.8)
    ax_vol.yaxis.grid(True, color=C_GRID, linewidth=0.2,  linestyle='--', alpha=0.4)

    n = len(df_g); tum_fiyatlar = []; vol_data = []

    for i, (_, row) in enumerate(df_g.iterrows()):
        try:
            o = float(row['Open']); c = float(row['Close'])
            h = float(row['High']); l = float(row['Low'])
        except Exception:
            continue
        tum_fiyatlar.extend([h, l])
        yukari = c >= o; renk = C_UP if yukari else C_DOWN
        bot = min(o, c); yuk = max(abs(c - o), (h - l) * 0.003)
        ax.add_patch(mpatches.Rectangle((i-0.38, bot), 0.76, yuk,
            linewidth=0.4, edgecolor=renk, facecolor=renk, alpha=0.88, zorder=3))
        ax.plot([i,i],[max(o,c),h], color=renk, lw=0.7, zorder=2, solid_capstyle='round')
        ax.plot([i,i],[l,bot],      color=renk, lw=0.7, zorder=2, solid_capstyle='round')
        try:    vol_data.append((i, float(row['Volume']), renk))
        except: vol_data.append((i, 0, renk))

    for period, renk, kalinlik in EMA_STILLER:
        col = f'EMA{period}'
        if col not in df_g.columns: continue
        vals = df_g[col].values.astype(float); mask = ~np.isnan(vals)
        if mask.sum() < 2: continue
        xs = np.where(mask)[0]
        ax.plot(xs, vals[mask], color=renk, lw=kalinlik*2.5, alpha=0.12, zorder=3)
        ax.plot(xs, vals[mask], color=renk, lw=kalinlik, alpha=0.88, zorder=4, label=f"EMA{period}")

    if vol_data:
        vols = [v for _,v,_ in vol_data]; max_v = max(vols) or 1
        for iv,v,rk in vol_data:
            ax_vol.add_patch(mpatches.Rectangle((iv-0.38,0),0.76,v,
                linewidth=0, facecolor=rk, alpha=0.45, zorder=2))
        ax_vol.set_ylim(0, max_v*1.35); ax_vol.set_xlim(-0.8, n+4)
        ax_vol.yaxis.set_major_locator(mticker.MaxNLocator(2, integer=False))
        ax_vol.yaxis.set_major_formatter(
            mticker.FuncFormatter(lambda x,_: f"{x/1e6:.1f}M" if x>=1e6 else f"{x/1e3:.0f}K"))

    if not tum_fiyatlar:
        return None

    pmin, pmax = min(tum_fiyatlar), max(tum_fiyatlar)
    pad = (pmax-pmin)*0.07 or pmin*0.02
    lvls = destekler + direncler
    if kutu: lvls += [kutu['destek'], kutu['direnc']]
    y_lo = min(pmin-pad, (min(lvls)-pad*0.5) if lvls else pmin-pad)
    y_hi = max(pmax+pad*3.0, (max(lvls)+pad) if lvls else pmax+pad)
    ax.set_xlim(-0.8, n+4); ax.set_ylim(y_lo, y_hi)

    def _frac(price): return (price - y_lo) / (y_hi - y_lo)

    try:
        son_k = float(df_g['Close'].iloc[-1]); son_o = float(df_g['Open'].iloc[-1])
    except Exception:
        son_k = son_o = 0.0

    _lbls = []; _MIN_GAP = 0.058

    def _etiket_ekle(frac, metin, renk, badge_fc=None, kalin=True):
        for _ in range(15):
            conflict = next((f for f,*_ in _lbls if abs(frac-f) < _MIN_GAP), None)
            if conflict is None: break
            frac = conflict - _MIN_GAP if frac < conflict else conflict + _MIN_GAP
        _lbls.append((max(0.02, min(0.97, frac)), metin, renk, badge_fc, kalin))

    _low_vals  = df_g['Low'].values.astype(float)  if df_g is not None else np.array([])
    _high_vals = df_g['High'].values.astype(float) if df_g is not None else np.array([])

    for idx, d in enumerate(destekler):
        guc  = 1.0 - idx * 0.20
        lw   = 1.6 - idx * 0.25
        mesafe = (son_k - d) / son_k * 100 if son_k > 0 else 0
        stil = '-' if idx == 0 else '--'
        test_n = int(np.sum(np.abs(_low_vals - d) / (d + 1e-10) < 0.020)) if len(_low_vals) else 0
        ax.axhspan(d*0.993, d*1.007, alpha=max(0.03, 0.08-idx*0.02), color=C_DESTEK, zorder=1)
        ax.axhline(d, color=C_DESTEK, lw=lw, linestyle=stil, alpha=guc*0.85, zorder=5)
        if len(_low_vals):
            touch_idx = np.where(np.abs(_low_vals - d) / (d + 1e-10) < 0.015)[0]
            for ti in touch_idx:
                ax.plot(ti, _low_vals[ti], 'v', color=C_DESTEK,
                        ms=3.5, alpha=0.55*guc, zorder=7, markeredgewidth=0)
        ax.plot(n-1, d, 'o', color=C_DESTEK, ms=4.0-idx*0.4, alpha=guc*0.85, zorder=8)
        test_str = f" {test_n}×" if test_n >= 2 else ""
        _etiket_ekle(_frac(d), f" D{idx+1}  {d:.2f}  ↓{mesafe:.1f}%{test_str} ", C_DESTEK, BG_CHART)

    for idx, rv in enumerate(direncler):
        guc  = 1.0 - idx * 0.20
        lw   = 1.6 - idx * 0.25
        mesafe = (rv - son_k) / son_k * 100 if son_k > 0 else 0
        stil = '-' if idx == 0 else '--'
        test_n = int(np.sum(np.abs(_high_vals - rv) / (rv + 1e-10) < 0.020)) if len(_high_vals) else 0
        ax.axhspan(rv*0.993, rv*1.007, alpha=max(0.03, 0.08-idx*0.02), color=C_DIRENC, zorder=1)
        ax.axhline(rv, color=C_DIRENC, lw=lw, linestyle=stil, alpha=guc*0.85, zorder=5)
        if len(_high_vals):
            touch_idx = np.where(np.abs(_high_vals - rv) / (rv + 1e-10) < 0.015)[0]
            for ti in touch_idx:
                ax.plot(ti, _high_vals[ti], '^', color=C_DIRENC,
                        ms=3.5, alpha=0.55*guc, zorder=7, markeredgewidth=0)
        ax.plot(n-1, rv, 'o', color=C_DIRENC, ms=4.0-idx*0.4, alpha=guc*0.85, zorder=8)
        test_str = f" {test_n}×" if test_n >= 2 else ""
        _etiket_ekle(_frac(rv), f" R{idx+1}  {rv:.2f}  ↑{mesafe:.1f}%{test_str} ", C_DIRENC, BG_CHART)

    if kutu:
        k_d=kutu['destek']; k_r=kutu['direnc']
        k_pct=kutu['aralik_pct']; k_doc=kutu.get('dokunma',0); k_bar=kutu.get('gun_sayisi',50)
        x0=max(0, n-k_bar-1-k_bar//5); xs=list(range(x0,n))
        ax.fill_between(xs, k_d, k_r, alpha=0.13, color=C_KUTU, zorder=1)
        x_start=max(0,n-k_bar-1)
        ax.plot([x_start,x_start],[k_d,k_r], color=C_KUTU, lw=1.0, alpha=0.45, zorder=4)
        ax.plot([x0,n+3],[k_d,k_d], color=C_KUTU, lw=2.0, alpha=0.88, zorder=6)
        ax.plot([x0,n+3],[k_r,k_r], color=C_KUTU, lw=1.4, linestyle='--', alpha=0.82, zorder=6)
        _etiket_ekle(_frac(k_r), f" KUTU ▸ {k_r:.2f}  %{k_pct} ", C_KUTU, "#2d1e00")
        _etiket_ekle(_frac(k_d), f" KUTU ▸ {k_d:.2f}  {k_doc}x ", C_KUTU, "#2d1e00")

    if son_k > 0:
        f_renk = C_UP if son_k >= son_o else C_DOWN
        ax.axhline(son_k, color=f_renk, lw=0.6, linestyle='--', alpha=0.45, zorder=4)
        _etiket_ekle(_frac(son_k), f" {son_k:.2f} ", 'white', f_renk)

    for frac, metin, renk, badge_fc, kalin in _lbls:
        fc = badge_fc if badge_fc else BG_CHART
        ax.annotate(metin, xy=(1.0, frac), xycoords='axes fraction',
            color=renk, fontsize=7.5, fontweight='bold' if kalin else 'normal',
            va='center', ha='left', annotation_clip=False,
            bbox=dict(boxstyle='round,pad=0.28', facecolor=fc, edgecolor=renk,
                      alpha=0.92, linewidth=0.0 if badge_fc==renk else 0.7))

    adim = max(1, n//8); ticks = list(range(0, n, adim))
    labels = [df_g.index[i].strftime('%d/%m') for i in ticks if i < n]
    ax_vol.set_xticks(ticks[:len(labels)]); ax_vol.set_xticklabels(labels, fontsize=7, color=C_AXIS)
    ax.set_xticks([])

    try:
        leg = ax.legend(loc='upper left', fontsize=7, framealpha=0.25,
                        facecolor=BG_CHART, edgecolor=C_GRID,
                        handlelength=1.5, handletextpad=0.5, borderpad=0.4, labelspacing=0.25)
        for txt, (_, renk, _) in zip(leg.get_texts(), EMA_STILLER):
            txt.set_color(renk)
    except Exception:
        pass

    genel      = sonuc.get('genel_sinyal', '')
    skor       = sonuc.get('sinyal_gucu', 0)
    periyot_ad = PERIYOT_ADLARI.get(sonuc.get('periyot', '1d'), '')
    fig.text(0.02, 0.975, hisse, color='#e2e8f0', fontsize=13, fontweight='bold', va='top', ha='left')
    try:
        ilk = float(df_g['Close'].iloc[0]); son = float(df_g['Close'].iloc[-1])
        deg = (son-ilk)/ilk*100; d_renk = C_UP if deg >= 0 else C_DOWN
        fig.text(0.02+len(hisse)*0.012, 0.975,
                 f"   {'+' if deg>=0 else ''}{deg:.2f}%",
                 color=d_renk, fontsize=10, fontweight='bold', va='top', ha='left')
    except Exception:
        pass
    sinyal_renk = SINYAL_RENK.get(genel, '#8e8e93')
    fig.text(0.02, 0.957, f"{genel}  ·  Skor {skor}/10  ·  {periyot_ad}",
             color=sinyal_renk, fontsize=9, fontweight='bold', va='top', ha='left')

    buf = BytesIO()
    fig.savefig(buf, format='png', dpi=120, bbox_inches='tight', facecolor=BG_FRAME)
    fig.clf()
    return buf.getvalue()


# ═══════════════════════════════════════════════════════════
# Mum Grafiği Widget (Matplotlib embedded)
# ═══════════════════════════════════════════════════════════
class GrafikWidget(FigureCanvas):
    # Renk paleti — test.jpg ile birebir
    BG_CHART  = "#0b1829"   # Grafik alanı (koyu navy)
    BG_FRAME  = "#0d1f30"   # Dış çerçeve
    C_UP      = "#26a69a"   # Yükselen mum (teal)
    C_DOWN    = "#ef5350"   # Düşen mum (kırmızı)
    C_SMA     = "#ff9800"   # (kullanılmıyor, aşağıda EMA renkleri var)
    EMA_STILLER = [
        (5,  "#5b9cf6", 1.3),   # mavi
        (8,  "#fb923c", 1.3),   # turuncu
        (13, "#22d3ee", 1.2),   # açık mavi
        (21, "#f87171", 1.2),   # kırmızı
        (50, "#c084fc", 1.5),   # mor — en uzun, biraz kalın
    ]
    C_DESTEK  = "#26a69a"   # Destek çizgisi (teal)
    C_DIRENC  = "#ef5350"   # Direnç çizgisi (kırmızı)
    C_GRID    = "#1a2e42"   # Grid çizgisi
    C_AXIS    = "#546e7a"   # Eksen yazıları
    C_TITLE   = "#cfd8dc"   # Başlık rengi
    C_KUTU    = "#f59e0b"   # Kutu konsolidasyon (amber)
    C_GREEN   = "#30d158"   # Sinyal yeşili (geçmiş işaretler için)

    def __init__(self, parent=None):
        self.fig = Figure(facecolor=self.BG_FRAME)
        super().__init__(self.fig)
        self.setParent(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumHeight(300)

    def guncelle(self, df_g, destekler, direncler, hisse="", kutu=None, ema_goster=True,
                 ha_goster=False, vp_goster=False, gecmis_sinyaller=None, cizgiler=None):
        self.fig.clear()
        self.fig.patch.set_facecolor(self.BG_FRAME)

        # ── Boş veri ──────────────────────────────────
        if df_g is None or df_g.empty:
            ax = self.fig.add_axes([0.02, 0.08, 0.78, 0.84])
            ax.set_facecolor(self.BG_CHART)
            for s in ax.spines.values(): s.set_visible(False)
            ax.text(0.5, 0.5, "Veri yok", transform=ax.transAxes,
                    ha='center', va='center', color=self.C_AXIS, fontsize=11)
            self._title(hisse, None)
            self.draw()
            return

        # ── Heikin Ashi dönüşümü ──────────────────────
        if ha_goster:
            try:
                from tarayici import heikin_ashi
                df_g = heikin_ashi(df_g)
            except Exception:
                pass

        # ── Layout: fiyat / hacim ─────────────────────
        ax     = self.fig.add_axes([0.02, 0.18, 0.78, 0.76])   # fiyat — geniş
        ax_vol = self.fig.add_axes([0.02, 0.04, 0.78, 0.12])   # hacim

        for a in (ax, ax_vol):
            a.set_facecolor(self.BG_CHART)
            for side in ('top', 'left', 'bottom'):
                a.spines[side].set_visible(False)
            a.spines['right'].set_color(self.C_GRID)
            a.yaxis.set_label_position('right')
            a.yaxis.tick_right()
            a.set_axisbelow(True)

        ax.tick_params(axis='y', colors=self.C_AXIS, labelsize=8, length=0, pad=4)
        ax.tick_params(axis='x', bottom=False, labelbottom=False)
        ax_vol.tick_params(axis='y', colors=self.C_AXIS, labelsize=6, length=0, pad=3)
        ax_vol.tick_params(axis='x', colors=self.C_AXIS, labelsize=7, length=0, pad=3)

        ax.yaxis.grid(True,     color=self.C_GRID, linewidth=0.35, linestyle='--', alpha=0.8)
        ax_vol.yaxis.grid(True, color=self.C_GRID, linewidth=0.2,  linestyle='--', alpha=0.4)

        n = len(df_g)
        tum_fiyatlar = []
        vol_data     = []

        # ── Mumlar ────────────────────────────────────
        for i, (_, row) in enumerate(df_g.iterrows()):
            try:
                o = float(row['Open']);  c = float(row['Close'])
                h = float(row['High']);  l = float(row['Low'])
            except Exception:
                continue
            tum_fiyatlar.extend([h, l])
            yukari = c >= o
            renk   = self.C_UP if yukari else self.C_DOWN
            bot    = min(o, c)
            yuk    = max(abs(c - o), (h - l) * 0.003)

            # Gövde
            ax.add_patch(mpatches.Rectangle(
                (i - 0.38, bot), 0.76, yuk,
                linewidth=0.4, edgecolor=renk, facecolor=renk,
                alpha=0.88, zorder=3
            ))
            # Fitiller
            ax.plot([i, i], [max(o, c), h], color=renk, lw=0.7, zorder=2, solid_capstyle='round')
            ax.plot([i, i], [l, bot],       color=renk, lw=0.7, zorder=2, solid_capstyle='round')

            try:
                vol_data.append((i, float(row['Volume']), renk))
            except Exception:
                vol_data.append((i, 0, renk))

        # ── EMA 5 / 8 / 13 / 21 / 50 ─────────────────
        if ema_goster:
            for period, renk, kalinlik in self.EMA_STILLER:
                col = f'EMA{period}'
                if col not in df_g.columns:
                    continue
                vals = df_g[col].values.astype(float)
                mask = ~np.isnan(vals)
                if mask.sum() < 2:
                    continue
                xs = np.where(mask)[0]
                ax.plot(xs, vals[mask], color=renk, lw=kalinlik * 2.5, alpha=0.12, zorder=3)
                ax.plot(xs, vals[mask], color=renk, lw=kalinlik,        alpha=0.88, zorder=4,
                        label=f"EMA{period}")

        # ── Hacim barları ─────────────────────────────
        if vol_data:
            vols = [v for _, v, _ in vol_data]
            max_v = max(vols) or 1
            for iv, v, rk in vol_data:
                ax_vol.add_patch(mpatches.Rectangle(
                    (iv - 0.38, 0), 0.76, v,
                    linewidth=0, facecolor=rk, alpha=0.45, zorder=2
                ))
            ax_vol.set_ylim(0, max_v * 1.35)
            ax_vol.set_xlim(-0.8, n + 4)
            ax_vol.yaxis.set_major_locator(mticker.MaxNLocator(2, integer=False))
            ax_vol.yaxis.set_major_formatter(
                mticker.FuncFormatter(
                    lambda x, _: f"{x/1e6:.1f}M" if x >= 1e6 else f"{x/1e3:.0f}K"
                )
            )
            ax_vol.annotate(
                " Vol ",
                xy=(0.005, 0.92), xycoords='axes fraction',
                color='#7ba8c0', fontsize=6.5, fontweight='600', va='top',
                annotation_clip=False,
                bbox=dict(boxstyle='round,pad=0.28', facecolor='#0a1e2e',
                          edgecolor=self.C_GRID, alpha=0.85, linewidth=0.5),
            )


        # ── Fiyat aralığı ─────────────────────────────
        if not tum_fiyatlar:
            self.draw()
            return
        pmin, pmax = min(tum_fiyatlar), max(tum_fiyatlar)
        pad  = (pmax - pmin) * 0.07 or pmin * 0.02
        lvls = destekler + direncler
        if kutu:
            lvls += [kutu['destek'], kutu['direnc']]
        y_lo = min(pmin - pad, (min(lvls) - pad * 0.5) if lvls else pmin - pad)
        y_hi = max(pmax + pad * 3.0, (max(lvls) + pad) if lvls else pmax + pad)
        ax.set_xlim(-0.8, n + 4)
        ax.set_ylim(y_lo, y_hi)

        def _frac(price):
            return (price - y_lo) / (y_hi - y_lo)

        try:
            son_k = float(df_g['Close'].iloc[-1])
            son_o = float(df_g['Open'].iloc[-1])
        except Exception:
            son_k = son_o = 0.0

        # ── Etiket çakışma önleme ─────────────────────
        _lbls = []  # [(frac, metin, renk, badge_fc, kalin)]
        _MIN_GAP = 0.058

        def _etiket_ekle(frac, metin, renk, badge_fc=None, kalin=True):
            # Her geçişte yalnızca ilk çakışmayı çöz; max 15 iterasyon
            # (iki yakın etiket arasına sıkışınca sonsuz titreşimi önler)
            for _ in range(15):
                conflict = next((f for f, *_ in _lbls if abs(frac - f) < _MIN_GAP), None)
                if conflict is None:
                    break
                frac = conflict - _MIN_GAP if frac < conflict else conflict + _MIN_GAP
            _lbls.append((max(0.02, min(0.97, frac)), metin, renk, badge_fc, kalin))

        # ── Destek çizgileri ──────────────────────────
        _low_vals  = df_g['Low'].values.astype(float)  if df_g is not None else np.array([])
        _high_vals = df_g['High'].values.astype(float) if df_g is not None else np.array([])

        for idx, d in enumerate(destekler):
            guc    = 1.0 - idx * 0.20
            lw     = 1.6 - idx * 0.25
            mesafe = (son_k - d) / son_k * 100 if son_k > 0 else 0
            stil   = '-' if idx == 0 else '--'
            test_n = int(np.sum(np.abs(_low_vals - d) / (d + 1e-10) < 0.020)) if len(_low_vals) else 0

            # Tek ince zon (gürültüsüz)
            ax.axhspan(d*0.993, d*1.007, alpha=max(0.03, 0.08-idx*0.02), color=self.C_DESTEK, zorder=1)
            ax.axhline(d, color=self.C_DESTEK, lw=lw, linestyle=stil, alpha=guc*0.85, zorder=5)

            if len(_low_vals):
                touch_idx = np.where(np.abs(_low_vals - d) / (d + 1e-10) < 0.015)[0]
                for ti in touch_idx:
                    ax.plot(ti, _low_vals[ti], 'v', color=self.C_DESTEK,
                            ms=3.5, alpha=0.55*guc, zorder=7, markeredgewidth=0)

            ax.plot(n-1, d, 'o', color=self.C_DESTEK, ms=4.0-idx*0.4, alpha=guc*0.85, zorder=8)
            test_str = f" {test_n}×" if test_n >= 2 else ""
            _etiket_ekle(_frac(d),
                         f" D{idx+1}  {d:.2f}  ↓{mesafe:.1f}%{test_str} ",
                         self.C_DESTEK, self.BG_CHART)

        # ── Direnç çizgileri ─────────────────────────
        for idx, rv in enumerate(direncler):
            guc    = 1.0 - idx * 0.20
            lw     = 1.6 - idx * 0.25
            mesafe = (rv - son_k) / son_k * 100 if son_k > 0 else 0
            stil   = '-' if idx == 0 else '--'
            test_n = int(np.sum(np.abs(_high_vals - rv) / (rv + 1e-10) < 0.020)) if len(_high_vals) else 0

            ax.axhspan(rv*0.993, rv*1.007, alpha=max(0.03, 0.08-idx*0.02), color=self.C_DIRENC, zorder=1)
            ax.axhline(rv, color=self.C_DIRENC, lw=lw, linestyle=stil, alpha=guc*0.85, zorder=5)

            if len(_high_vals):
                touch_idx = np.where(np.abs(_high_vals - rv) / (rv + 1e-10) < 0.015)[0]
                for ti in touch_idx:
                    ax.plot(ti, _high_vals[ti], '^', color=self.C_DIRENC,
                            ms=3.5, alpha=0.55*guc, zorder=7, markeredgewidth=0)

            ax.plot(n-1, rv, 'o', color=self.C_DIRENC, ms=4.0-idx*0.4, alpha=guc*0.85, zorder=8)
            test_str = f" {test_n}×" if test_n >= 2 else ""
            _etiket_ekle(_frac(rv),
                         f" R{idx+1}  {rv:.2f}  ↑{mesafe:.1f}%{test_str} ",
                         self.C_DIRENC, self.BG_CHART)

        # ── Kutu konsolidasyon ────────────────────────
        if kutu:
            k_d   = kutu['destek']
            k_r   = kutu['direnc']
            k_pct = kutu['aralik_pct']
            k_doc = kutu.get('dokunma', 0)
            k_bar = kutu.get('gun_sayisi', 50)
            # Konsolidasyon başlangıcı; sola biraz bağlam ekle
            x0    = max(0, n - k_bar - 1 - k_bar // 5)

            xs = list(range(x0, n))
            ax.fill_between(xs, k_d, k_r,
                            alpha=0.13, color=self.C_KUTU, zorder=1)
            # Sol kenar — konsolidasyon başlangıcını işaret eder
            x_start = max(0, n - k_bar - 1)
            ax.plot([x_start, x_start], [k_d, k_r],
                    color=self.C_KUTU, lw=1.0, alpha=0.45, zorder=4)
            # Alt çizgi (destek) — solid, tam genişlik
            ax.plot([x0, n + 3], [k_d, k_d],
                    color=self.C_KUTU, lw=2.0, alpha=0.88, zorder=6)
            # Üst çizgi (hedef/kırılım) — dashed, tam genişlik
            ax.plot([x0, n + 3], [k_r, k_r],
                    color=self.C_KUTU, lw=1.4, linestyle='--', alpha=0.82, zorder=6)
            _etiket_ekle(_frac(k_r),
                         f" KUTU ▸ {k_r:.2f}  %{k_pct} ",
                         self.C_KUTU, "#2d1e00")
            _etiket_ekle(_frac(k_d),
                         f" KUTU ▸ {k_d:.2f}  {k_doc}x ",
                         self.C_KUTU, "#2d1e00")

        # ── Hacim Profili (VP) ────────────────────────
        if vp_goster and vol_data and len(df_g) > 0:
            try:
                bins = 24
                fiyatlar_b = np.linspace(y_lo, y_hi, bins + 1)
                close_arr  = df_g['Close'].values.astype(float)
                open_arr   = df_g['Open'].values.astype(float)
                vol_arr    = np.array([v for _, v, _ in vol_data], dtype=float)
                max_vol_vp = max(float(vol_arr.max()), 1.0)
                for b in range(bins):
                    alt_f, ust_f = fiyatlar_b[b], fiyatlar_b[b + 1]
                    mask_b = (close_arr >= alt_f) & (close_arr < ust_f)
                    vol_b  = vol_arr[mask_b].sum() if mask_b.any() else 0
                    if vol_b <= 0:
                        continue
                    vol_norm = vol_b / (max_vol_vp * bins)
                    yukari_b = (close_arr[mask_b] >= open_arr[mask_b]).sum() > mask_b.sum() / 2
                    renk_vp  = self.C_UP if yukari_b else self.C_DOWN
                    mid_f = (alt_f + ust_f) / 2
                    genislik = vol_norm * n * 0.12
                    ax.barh(mid_f, genislik, height=(ust_f - alt_f) * 0.85,
                            left=n - genislik - 0.5, color=renk_vp, alpha=0.28, zorder=2)
            except Exception:
                pass

        # ── Geçmiş sinyal işaretleri ─────────────────
        if gecmis_sinyaller:
            for g_idx, g_sinyal in gecmis_sinyaller:
                if not (0 <= g_idx < n):
                    continue
                if any(k in g_sinyal for k in ('SAT', 'ÖLÜ', 'KIRILDI')):
                    ax.plot(g_idx, float(df_g['High'].iloc[g_idx]) * 1.012,
                            'v', color=self.C_DOWN, ms=5, zorder=9, alpha=0.7,
                            markeredgewidth=0)
                else:
                    ax.plot(g_idx, float(df_g['Low'].iloc[g_idx]) * 0.988,
                            '^', color=self.C_GREEN, ms=5, zorder=9, alpha=0.7,
                            markeredgewidth=0)

        # ── Manuel trend çizgileri ────────────────────
        if cizgiler:
            for c in cizgiler:
                try:
                    ax.plot([c['x1'], c['x2']], [c['y1'], c['y2']],
                            color='#fbbf24', lw=1.3, alpha=0.85,
                            linestyle='--', zorder=10)
                except Exception:
                    pass

        # ── Son fiyat etiketi ─────────────────────────
        if son_k > 0:
            f_renk = self.C_UP if son_k >= son_o else self.C_DOWN
            ax.axhline(son_k, color=f_renk, lw=0.6,
                       linestyle='--', alpha=0.45, zorder=4)
            _etiket_ekle(_frac(son_k), f" {son_k:.2f} ", 'white', f_renk)

        # ── Tüm etiketleri çiz ───────────────────────
        for frac, metin, renk, badge_fc, kalin in _lbls:
            fc   = badge_fc if badge_fc else self.BG_CHART
            ec   = renk
            lw_b = 0.0 if badge_fc == renk else 0.7
            ax.annotate(
                metin,
                xy=(1.0, frac), xycoords='axes fraction',
                color=renk, fontsize=7.5,
                fontweight='bold' if kalin else 'normal',
                va='center', ha='left', annotation_clip=False,
                bbox=dict(boxstyle='round,pad=0.28',
                          facecolor=fc, edgecolor=ec,
                          alpha=0.92, linewidth=lw_b),
            )

        # ── X ekseni tarihleri (hacim paneli) ────────
        adim   = max(1, n // 8)
        ticks  = list(range(0, n, adim))
        labels = [df_g.index[i].strftime('%d/%m') for i in ticks if i < n]
        ax_vol.set_xticks(ticks[:len(labels)])
        ax_vol.set_xticklabels(labels, fontsize=7, color=self.C_AXIS)
        ax.set_xticks([])

        # ── EMA legend (sol üst) ──────────────────────
        if ema_goster:
            leg = ax.legend(
                loc='upper left', fontsize=7, framealpha=0.25,
                facecolor=self.BG_CHART, edgecolor=self.C_GRID,
                handlelength=1.5, handletextpad=0.5,
                borderpad=0.4, labelspacing=0.25,
            )
            for txt, (_, renk, _) in zip(leg.get_texts(), self.EMA_STILLER):
                txt.set_color(renk)

        self._title(hisse, df_g)
        self.draw()

    def _title(self, hisse, df_g):
        if not hisse:
            return
        self.fig.text(0.02, 0.975, hisse, color='#e2e8f0',
                      fontsize=13, fontweight='bold', va='top', ha='left')
        if df_g is not None and not df_g.empty:
            try:
                ilk = float(df_g['Close'].iloc[0])
                son = float(df_g['Close'].iloc[-1])
                deg = (son - ilk) / ilk * 100
                d_renk = self.C_UP if deg >= 0 else self.C_DOWN
                d_txt  = (f"+{deg:.2f}%" if deg >= 0 else f"{deg:.2f}%")
                self.fig.text(0.02 + len(hisse) * 0.012, 0.975,
                              f"   {d_txt}", color=d_renk,
                              fontsize=10, fontweight='bold', va='top', ha='left')
            except Exception:
                pass

# ═══════════════════════════════════════════════════════════
# Detay Paneli (Sağ Taraf)
# ═══════════════════════════════════════════════════════════
class DetayPanel(QWidget):
    def __init__(self):
        super().__init__()
        self._kur_ui()

    def _kur_ui(self):
        self.setStyleSheet(f"background:{C_BG};")
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 16, 20, 16)
        root.setSpacing(14)

        # ── Hisse Başlık ──────────────────────
        baslik_layout = QHBoxLayout()
        self.lbl_hisse = QLabel("—")
        self.lbl_hisse.setObjectName("hisseAd")
        self.lbl_fiyat = QLabel("")
        self.lbl_fiyat.setObjectName("fiyatLbl")
        self.lbl_sinyal_btn = QLabel("")
        self.lbl_sinyal_btn.setFixedWidth(130)
        self.lbl_sinyal_btn.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_sinyal_btn.setStyleSheet(
            f"border-radius:8px; padding:6px 10px; font-weight:700; font-size:14px;")

        self.lbl_perf = QLabel("")
        self.lbl_perf.setStyleSheet(f"font-size:13px; font-weight:700;")

        self.btn_favori = QPushButton("☆")
        self.btn_favori.setFixedSize(38, 38)
        self.btn_favori.setToolTip("Favorilere ekle / çıkar")
        self.btn_favori.setStyleSheet(
            f"QPushButton{{background:{C_CARD2};border:none;"
            f"border-radius:10px;font-size:18px;padding:0;color:{C_MUTED};}}"
            f"QPushButton:hover{{background:#3a2e00;color:#ffd60a;}}")
        self.btn_favori.clicked.connect(self._favori_toggle)

        self.btn_alarm = QPushButton("🔔")
        self.btn_alarm.setFixedSize(38, 38)
        self.btn_alarm.setToolTip("Fiyat alarmı kur")
        self.btn_alarm.setStyleSheet(
            f"QPushButton{{background:{C_CARD2};border:none;"
            f"border-radius:10px;font-size:15px;padding:0;color:{C_MUTED};}}"
            f"QPushButton:hover{{background:#1a3a5c;color:#5b9cf6;}}")
        self.btn_alarm.clicked.connect(self._alarm_toggle)

        self.btn_portfoy = QPushButton("📈")
        self.btn_portfoy.setFixedSize(38, 38)
        self.btn_portfoy.setToolTip("Pozisyon aç")
        self.btn_portfoy.setStyleSheet(
            f"QPushButton{{background:{C_CARD2};border:none;"
            f"border-radius:10px;font-size:15px;padding:0;color:{C_MUTED};}}"
            f"QPushButton:hover{{background:#0a3d1f;color:{C_GREEN};}}")
        self.btn_portfoy.clicked.connect(self._portfoy_toggle)

        self.btn_neden = QPushButton("🔍")
        self.btn_neden.setFixedSize(38, 38)
        self.btn_neden.setToolTip("Neden bu sinyal?")
        self.btn_neden.setStyleSheet(
            f"QPushButton{{background:{C_CARD2};border:none;"
            f"border-radius:10px;font-size:15px;padding:0;color:{C_MUTED};}}"
            f"QPushButton:hover{{background:#1a1a2e;color:#a78bfa;}}")
        self.btn_neden.clicked.connect(self._neden_ac)

        self.btn_kap = QPushButton("🏛")
        self.btn_kap.setFixedSize(38, 38)
        self.btn_kap.setToolTip("KAP Duyuruları")
        self.btn_kap.setStyleSheet(
            f"QPushButton{{background:{C_CARD2};border:none;"
            f"border-radius:10px;font-size:15px;padding:0;color:{C_MUTED};}}"
            f"QPushButton:hover{{background:#0a3d1f;color:{C_GREEN};}}")
        self.btn_kap.clicked.connect(self._kap_ac)

        self.btn_kopyala = QPushButton("📋")
        self.btn_kopyala.setFixedSize(38, 38)
        self.btn_kopyala.setToolTip("Bildirim metnini kopyala")
        self.btn_kopyala.setObjectName("copyBtn")
        self.btn_kopyala.setStyleSheet(
            f"QPushButton{{background:{C_CARD2};border:none;"
            f"border-radius:10px;font-size:15px;padding:0;}}"
            f"QPushButton:hover{{background:{C_BLUE};}}")
        self.btn_kopyala.clicked.connect(self._kopyala)

        self.btn_not = QPushButton("📝")
        self.btn_not.setFixedSize(38, 38)
        self.btn_not.setToolTip("Hisse notu ekle / düzenle")
        self.btn_not.setStyleSheet(
            f"QPushButton{{background:{C_CARD2};border:none;"
            f"border-radius:10px;font-size:15px;padding:0;color:{C_MUTED};}}"
            f"QPushButton:hover{{background:#3a2e00;color:#ffd60a;}}")
        self.btn_not.clicked.connect(self._not_ac)

        self.btn_fvt = QPushButton("FVT")
        self.btn_fvt.setFixedSize(42, 38)
        self.btn_fvt.setToolTip("FVT — Temel Analiz sayfasını aç")
        self.btn_fvt.setStyleSheet(
            f"QPushButton{{background:{C_CARD2};border:none;"
            f"border-radius:10px;font-size:11px;font-weight:700;"
            f"padding:0;color:#34d399;}}"
            f"QPushButton:hover{{background:#064e3b;color:#6ee7b7;}}"
            f"QPushButton:disabled{{color:#555;}}")
        self.btn_fvt.clicked.connect(self._fvt_ac)

        self.btn_tv = QPushButton("TV")
        self.btn_tv.setFixedSize(38, 38)
        self.btn_tv.setToolTip("TradingView — Grafik sayfasını aç")
        self.btn_tv.setStyleSheet(
            f"QPushButton{{background:{C_CARD2};border:none;"
            f"border-radius:10px;font-size:12px;font-weight:700;"
            f"padding:0;color:#5b9cf6;}}"
            f"QPushButton:hover{{background:#1e3a5f;color:#93c5fd;}}"
            f"QPushButton:disabled{{color:#555;}}")
        self.btn_tv.clicked.connect(self._tv_ac)

        baslik_layout.addWidget(self.lbl_hisse)
        baslik_layout.addSpacing(16)
        baslik_layout.addWidget(self.lbl_fiyat)
        baslik_layout.addSpacing(8)
        baslik_layout.addWidget(self.lbl_perf)
        baslik_layout.addStretch()
        baslik_layout.addWidget(self.lbl_sinyal_btn)
        baslik_layout.addSpacing(8)
        baslik_layout.addWidget(self.btn_favori)
        baslik_layout.addSpacing(4)
        baslik_layout.addWidget(self.btn_alarm)
        baslik_layout.addSpacing(4)
        baslik_layout.addWidget(self.btn_portfoy)
        baslik_layout.addSpacing(4)
        baslik_layout.addWidget(self.btn_neden)
        baslik_layout.addSpacing(4)
        baslik_layout.addWidget(self.btn_kap)
        baslik_layout.addSpacing(4)
        baslik_layout.addWidget(self.btn_kopyala)
        baslik_layout.addSpacing(4)
        baslik_layout.addWidget(self.btn_not)
        baslik_layout.addSpacing(8)
        # Separator line
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setFixedHeight(24)
        sep.setStyleSheet(f"color:{C_BORDER};")
        baslik_layout.addWidget(sep)
        baslik_layout.addSpacing(8)
        baslik_layout.addWidget(self.btn_fvt)
        baslik_layout.addSpacing(4)
        baslik_layout.addWidget(self.btn_tv)
        root.addLayout(baslik_layout)

        # ── Alt başlık: tarih + periyot segmented control ──
        alt_layout = QHBoxLayout()
        self.lbl_tarih = QLabel("")
        self.lbl_tarih.setObjectName("gecikme")
        alt_layout.addWidget(self.lbl_tarih)
        alt_layout.addStretch()

        # EMA / HA / VP / SIG / ✏ toggle butonları
        self._ema_goster = True
        self._ha_goster  = False
        self._vp_goster  = False
        self._sig_goster = False
        self._cizgi_modu = False
        self._cizgi_c1   = None
        self._cizgi_cid_press   = None
        self._cizgi_cid_motion  = None
        self._cizgi_cid_release = None

        def _tog_btn(etiket, tooltip, aktif=False):
            b = QPushButton(etiket)
            b.setCheckable(True)
            b.setChecked(aktif)
            b.setFixedSize(46, 28)
            b.setToolTip(tooltip)
            b.setStyleSheet(self._ema_btn_stili(aktif))
            return b

        self.btn_ema = _tog_btn("EMA", "EMA çizgilerini göster/gizle", True)
        self.btn_ema.clicked.connect(self._ema_toggle)
        alt_layout.addWidget(self.btn_ema)
        alt_layout.addSpacing(4)

        self.btn_ha = _tog_btn("HA", "Heikin Ashi mumları")
        self.btn_ha.clicked.connect(self._ha_toggle)
        alt_layout.addWidget(self.btn_ha)
        alt_layout.addSpacing(4)

        self.btn_vp = _tog_btn("VP", "Hacim Profili")
        self.btn_vp.clicked.connect(self._vp_toggle)
        alt_layout.addWidget(self.btn_vp)
        alt_layout.addSpacing(4)

        self.btn_sig = _tog_btn("SIG", "Geçmiş sinyal işaretleri")
        self.btn_sig.clicked.connect(self._sig_toggle)
        alt_layout.addWidget(self.btn_sig)
        alt_layout.addSpacing(4)

        self.btn_cizgi = _tog_btn("✏", "Trend çizgisi çiz")
        self.btn_cizgi.clicked.connect(self._cizgi_toggle)
        alt_layout.addWidget(self.btn_cizgi)
        alt_layout.addSpacing(6)

        # Periyot seçici (detay paneline özel)
        self._detay_periyot = "1d"
        self._detay_fetch   = None
        self._detay_per_btn = {}

        seg = QWidget()
        seg.setFixedHeight(28)
        seg.setStyleSheet(f"background:{C_CARD2}; border-radius:9px;")
        seg_lay = QHBoxLayout(seg)
        seg_lay.setContentsMargins(3, 3, 3, 3)
        seg_lay.setSpacing(2)
        for etiket, kod in [("1S","1h"), ("4S","4h"), ("Gün","1d"), ("Haf","1w"), ("Ay","1mo")]:
            btn = QPushButton(etiket)
            btn.setCheckable(True)
            btn.setChecked(kod == "1d")
            btn.setFixedSize(46, 22)
            btn.setStyleSheet(_seg_btn_stili(kod == "1d"))
            btn.clicked.connect(lambda _, k=kod: self._detay_periyot_degistir(k))
            self._detay_per_btn[kod] = btn
            seg_lay.addWidget(btn)
        alt_layout.addWidget(seg)
        root.addLayout(alt_layout)

        # Kartlar: gizli container widget içinde tutulur (parent olması gerekiyor)
        self._kart_container = QWidget()
        self._kart_container.setVisible(False)
        self.grid = QGridLayout(self._kart_container)
        self.kartlar = {}
        pozisyonlar = {
            'rsi':        (0, 0, "RSI"),
            'trend':      (0, 1, "Trend (SMA)"),
            'macd':       (0, 2, "MACD"),
            'bollinger':  (1, 0, "Bollinger"),
            'stokastik':  (1, 1, "Stokastik"),
            'momentum':   (1, 2, "Momentum"),
        }
        for anahtar, (satir, sutun, baslik) in pozisyonlar.items():
            kart = GostergekKart(baslik, "—", "NÖTR", "—")
            self.kartlar[anahtar] = kart
            self.grid.addWidget(kart, satir, sutun)
        self._ozet_rsi  = QLabel()
        self._ozet_macd = QLabel()
        self._ozet_ema  = QLabel()
        self._ozet_vol  = QLabel()

        # ── Skor Kırılımı ────────────────────
        skor_frame = QFrame()
        skor_frame.setStyleSheet(f"background:{C_CARD}; border-radius:10px; border:none;")
        skor_frame.setMinimumHeight(36)
        skor_hor = QHBoxLayout(skor_frame)
        skor_hor.setContentsMargins(10, 5, 10, 5)
        skor_hor.setSpacing(8)

        self.lbl_skor_sayi = QLabel("—")
        self.lbl_skor_sayi.setFixedWidth(28)
        self.lbl_skor_sayi.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_skor_sayi.setStyleSheet(
            f"font-size:16px; font-weight:800; background:transparent; color:{C_TEXT};")
        skor_hor.addWidget(self.lbl_skor_sayi)

        sep_s = QFrame()
        sep_s.setFixedWidth(1)
        sep_s.setMinimumHeight(20)
        sep_s.setStyleSheet(f"background:{C_BORDER}; border:none;")
        skor_hor.addWidget(sep_s)

        self._skor_pills_lay = QHBoxLayout()
        self._skor_pills_lay.setSpacing(4)
        self._skor_pills_lay.setContentsMargins(0, 0, 0, 0)
        skor_hor.addLayout(self._skor_pills_lay)
        skor_hor.addStretch()

        btn_skor_detay = QPushButton("?")
        btn_skor_detay.setFixedSize(22, 22)
        btn_skor_detay.setToolTip("Skor nasıl hesaplanır? — Strateji Rehberini aç")
        btn_skor_detay.setStyleSheet(
            f"QPushButton{{background:{C_CARD2};color:{C_MUTED};border:none;"
            f"border-radius:11px;font-size:11px;font-weight:700;padding:0;}}"
            f"QPushButton:hover{{background:{C_BORDER};color:{C_TEXT};}}")
        btn_skor_detay.clicked.connect(self._skor_rehber_ac)
        skor_hor.addWidget(btn_skor_detay)
        root.addWidget(skor_frame)

        # ── Risk/Ödül Şeridi ─────────────────
        rr_frame = QFrame()
        rr_frame.setFixedHeight(38)
        rr_frame.setStyleSheet(f"background:{C_CARD}; border-radius:10px; border:none;")
        rr_lay = QHBoxLayout(rr_frame)
        rr_lay.setContentsMargins(12, 0, 12, 0)
        rr_lay.setSpacing(4)

        def _rr_pill(txt):
            l = QLabel(txt)
            l.setAlignment(Qt.AlignmentFlag.AlignCenter)
            l.setStyleSheet(
                f"color:{C_MUTED}; font-size:11px; font-weight:600; "
                f"background:{C_CARD2}; border-radius:6px; padding:2px 9px; border:none;")
            return l

        self._rr_stop  = _rr_pill("Stop —")
        self._rr_hedef = _rr_pill("Hedef —")
        self._rr_oran  = _rr_pill("R:R —")
        self._rr_risk  = _rr_pill("Risk —")
        self._rr_lot   = _rr_pill("Lot —")
        self._rr_bt    = _rr_pill("")
        self._rr_bt.setVisible(False)

        btn_risk_ayar = QPushButton("⚙")
        btn_risk_ayar.setFixedSize(26, 26)
        btn_risk_ayar.setToolTip("Risk Ayarları")
        btn_risk_ayar.setStyleSheet(
            f"QPushButton{{background:{C_CARD2};border:none;border-radius:6px;"
            f"font-size:12px;padding:0;color:{C_MUTED};}}"
            f"QPushButton:hover{{background:#48484a;color:{C_TEXT};}}")
        btn_risk_ayar.clicked.connect(self._risk_ayar_ac)

        for w in (self._rr_stop, self._rr_hedef, self._rr_oran, self._rr_risk, self._rr_lot):
            rr_lay.addWidget(w)
        rr_lay.addSpacing(6)
        rr_lay.addWidget(self._rr_bt)
        rr_lay.addStretch()
        rr_lay.addWidget(btn_risk_ayar)
        root.addWidget(rr_frame)

        # ── Mum Grafiği (tam alan) ────────────
        self.grafik = GrafikWidget(self)
        root.addWidget(self.grafik, stretch=1)

        # ── Hisse Notu Etiketi ────────────────
        self.lbl_not_goster = QLabel("")
        self.lbl_not_goster.setWordWrap(True)
        self.lbl_not_goster.setVisible(False)
        self.lbl_not_goster.setStyleSheet(
            f"background:#2d2600; color:#ffd60a; border-radius:8px; "
            f"padding:6px 10px; font-size:12px; border:1px solid #665500;")
        root.addWidget(self.lbl_not_goster)

        self._sonuc = None
        self._kap_thread = None
        self.btn_fvt.setEnabled(False)
        self.btn_tv.setEnabled(False)

    @staticmethod
    def _ema_btn_stili(aktif: bool) -> str:
        if aktif:
            bg, fg = "#1c3a5c", "#5b9cf6"
            border = "1px solid #5b9cf6"
        else:
            bg, fg = C_CARD2, C_MUTED
            border = "none"
        return (f"QPushButton{{background:{bg};color:{fg};border:{border};"
                f"border-radius:8px;font-size:11px;font-weight:{'600' if aktif else '400'};"
                f"padding:0;}}"
                f"QPushButton:hover{{background:#1e3a5c;color:#7cb9ff;}}")

    def _grafik_yenile(self):
        if not self._sonuc:
            return
        hisse   = self._sonuc.get('hisse', '')
        periyot = self._sonuc.get('periyot', self._detay_periyot)
        gecmis_sinyaller = None
        if self._sig_goster:
            gecmis_sinyaller = self._gecmis_isaretleri_hesapla(
                hisse, periyot, self._sonuc.get('df_grafik'))
        cizgiler = CIZGILER.yukle(hisse, periyot) if not self._cizgi_modu else None
        self.grafik.guncelle(
            self._sonuc.get('df_grafik'),
            self._sonuc.get('destekler', [])[:3],
            self._sonuc.get('direncler', [])[:3],
            hisse,
            self._sonuc.get('kutu'),
            ema_goster=self._ema_goster,
            ha_goster=self._ha_goster,
            vp_goster=self._vp_goster,
            gecmis_sinyaller=gecmis_sinyaller,
            cizgiler=CIZGILER.yukle(hisse, periyot),
        )

    def _gecmis_isaretleri_hesapla(self, hisse, periyot, df_g):
        if df_g is None or df_g.empty:
            return []
        try:
            import pandas as pd
            gecmis = GECMIS.yukle(600)
            sonuclar = []
            for kayit in gecmis:
                if kayit.get('hisse') != hisse or kayit.get('periyot') != periyot:
                    continue
                try:
                    tarih = pd.to_datetime(kayit['tarih'])
                    idx = df_g.index.get_indexer([tarih], method='nearest')[0]
                    if 0 <= idx < len(df_g):
                        sonuclar.append((idx, kayit.get('sinyal', '')))
                except Exception:
                    pass
            return sonuclar
        except Exception:
            return []

    def _ema_toggle(self):
        self._ema_goster = not self._ema_goster
        self.btn_ema.setChecked(self._ema_goster)
        self.btn_ema.setStyleSheet(self._ema_btn_stili(self._ema_goster))
        self._grafik_yenile()

    def _ha_toggle(self):
        self._ha_goster = not self._ha_goster
        self.btn_ha.setChecked(self._ha_goster)
        self.btn_ha.setStyleSheet(self._ema_btn_stili(self._ha_goster))
        self._grafik_yenile()

    def _vp_toggle(self):
        self._vp_goster = not self._vp_goster
        self.btn_vp.setChecked(self._vp_goster)
        self.btn_vp.setStyleSheet(self._ema_btn_stili(self._vp_goster))
        self._grafik_yenile()

    def _sig_toggle(self):
        self._sig_goster = not self._sig_goster
        self.btn_sig.setChecked(self._sig_goster)
        self.btn_sig.setStyleSheet(self._ema_btn_stili(self._sig_goster))
        self._grafik_yenile()

    def _cizgi_toggle(self):
        self._cizgi_modu = not self._cizgi_modu
        self.btn_cizgi.setChecked(self._cizgi_modu)
        self.btn_cizgi.setStyleSheet(self._ema_btn_stili(self._cizgi_modu))
        if self._cizgi_modu:
            self._kur_cizgi_events(True)
        else:
            self._kur_cizgi_events(False)
            self._grafik_yenile()

    def _kur_cizgi_events(self, aktif: bool):
        if aktif:
            self._cizgi_c1 = None
            self._cizgi_cid_press   = self.grafik.mpl_connect(
                'button_press_event',   self._cizgi_tikla)
            self._cizgi_cid_motion  = self.grafik.mpl_connect(
                'motion_notify_event',  self._cizgi_sur)
            self._cizgi_cid_release = self.grafik.mpl_connect(
                'button_release_event', self._cizgi_birak)
        else:
            for attr in ('_cizgi_cid_press', '_cizgi_cid_motion', '_cizgi_cid_release'):
                cid = getattr(self, attr, None)
                if cid is not None:
                    try:
                        self.grafik.mpl_disconnect(cid)
                    except Exception:
                        pass
                    setattr(self, attr, None)
            self._cizgi_c1 = None

    def _cizgi_tikla(self, event):
        if event.inaxes is None or event.xdata is None:
            return
        if event.button == 3:
            # Sağ tık → en yakın çizgiyi sil
            if not self._sonuc:
                return
            hisse   = self._sonuc.get('hisse', '')
            periyot = self._sonuc.get('periyot', self._detay_periyot)
            cizgiler = CIZGILER.yukle(hisse, periyot)
            if not cizgiler:
                return
            min_d, min_i = float('inf'), -1
            for i, c in enumerate(cizgiler):
                try:
                    d = abs(event.xdata - (c['x1'] + c['x2']) / 2) + \
                        abs(event.ydata - (c['y1'] + c['y2']) / 2) / (event.ydata or 1)
                    if d < min_d:
                        min_d, min_i = d, i
                except Exception:
                    pass
            if min_i >= 0:
                CIZGILER.sil(hisse, periyot, min_i)
                self._grafik_yenile()
            return
        if self._cizgi_c1 is None:
            self._cizgi_c1 = (event.xdata, event.ydata)
        else:
            x1, y1 = self._cizgi_c1
            x2, y2 = event.xdata, event.ydata
            if self._sonuc:
                hisse   = self._sonuc.get('hisse', '')
                periyot = self._sonuc.get('periyot', self._detay_periyot)
                CIZGILER.ekle(hisse, periyot, x1, y1, x2, y2)
            self._cizgi_c1 = None
            self._grafik_yenile()

    def _cizgi_sur(self, event):
        if self._cizgi_c1 is None or event.inaxes is None or event.xdata is None:
            return
        # Geçici önizleme: tam yeniden çizim yerine sadece hafif refresh
        try:
            self.grafik.draw_idle()
        except Exception:
            pass

    def _cizgi_birak(self, event):
        pass   # sol tık release'i tikla ile birlikte yönetiliyor

    def _not_ac(self):
        if not self._sonuc:
            return
        hisse = self._sonuc.get('hisse', '')
        if not hisse:
            return
        dlg = NotDialog(hisse, NOTLAR.al(hisse), self)
        dlg.exec()
        # Not kaydedilmiş veya silinmiş olabilir; etiketi güncelle
        metin = NOTLAR.al(hisse)
        self.lbl_not_goster.setVisible(bool(metin))
        self.lbl_not_goster.setText(f"📝  {metin}" if metin else "")
        # btn_not rengini güncelle
        if NOTLAR.var_mi(hisse):
            self.btn_not.setStyleSheet(
                f"QPushButton{{background:#3a2e00;border:none;"
                f"border-radius:10px;font-size:15px;padding:0;color:#ffd60a;}}"
                f"QPushButton:hover{{background:#4a3a00;color:#ffe066;}}")
        else:
            self.btn_not.setStyleSheet(
                f"QPushButton{{background:{C_CARD2};border:none;"
                f"border-radius:10px;font-size:15px;padding:0;color:{C_MUTED};}}"
                f"QPushButton:hover{{background:#3a2e00;color:#ffd60a;}}")

    @staticmethod
    def _thread_kapat(t):
        """Çalışan bir TekHisseFetchThread'i güvenli şekilde keser."""
        if t is None:
            return
        try:
            t.bitti.disconnect()
        except Exception:
            pass
        try:
            t.hata.disconnect()
        except Exception:
            pass
        t.finished.connect(t.deleteLater)   # Qt tarafı bitince belleği temizle

    def _detay_periyot_degistir(self, kod: str):
        if not self._sonuc or kod == self._detay_periyot:
            self._detay_per_btn[kod].setChecked(kod == self._detay_periyot)
            return
        self._detay_periyot = kod
        for k, btn in self._detay_per_btn.items():
            btn.setChecked(k == kod)
            btn.setStyleSheet(_seg_btn_stili(k == kod))
        hisse = self._sonuc.get('hisse', '')
        self.lbl_tarih.setText("Yükleniyor…")
        self._thread_kapat(self._detay_fetch)   # eski thread'i kes
        self._detay_fetch = TekHisseFetchThread(hisse, kod)
        self._detay_fetch.bitti.connect(self.guncelle)
        self._detay_fetch.hata.connect(
            lambda h, s: self.lbl_tarih.setText(f"{h} — {s}"))
        self._detay_fetch.start()

    def _alarm_toggle(self):
        if not self._sonuc:
            return
        hisse = self._sonuc.get('hisse', '')
        if ALARMLAR.alarm_var_mi(hisse):
            ALARMLAR.kaldir(hisse)
            self._alarm_guncelle(hisse)
        else:
            fiyat = self._sonuc.get('fiyat', 0)
            hedef, ok = QInputDialog.getDouble(
                self, "Fiyat Alarmı",
                f"{hisse} için hedef fiyat girin (₺):",
                value=round(fiyat * 1.05, 2), min=0.01, max=999999.99, decimals=2,
            )
            if ok:
                ALARMLAR.ekle(hisse, hedef)
                self._alarm_guncelle(hisse)

    def _alarm_guncelle(self, hisse):
        if ALARMLAR.alarm_var_mi(hisse):
            hedef = ALARMLAR.hedef(hisse)
            self.btn_alarm.setStyleSheet(
                f"QPushButton{{background:#0c3547;border:1px solid {C_BLUE};"
                f"border-radius:10px;font-size:15px;padding:0;color:{C_BLUE};}}"
                f"QPushButton:hover{{background:#0a84ff33;}}")
            self.btn_alarm.setToolTip(f"Alarm: ₺{hedef:.2f} — kaldırmak için tıkla")
        else:
            self.btn_alarm.setStyleSheet(
                f"QPushButton{{background:{C_CARD2};border:none;"
                f"border-radius:10px;font-size:15px;padding:0;color:{C_MUTED};}}"
                f"QPushButton:hover{{background:#1a3a5c;color:#5b9cf6;}}")
            self.btn_alarm.setToolTip("Fiyat alarmı kur")

    def _portfoy_toggle(self):
        if not self._sonuc:
            return
        hisse = self._sonuc.get('hisse', '')
        fiyat = self._sonuc.get('fiyat', 0)
        if PORTFOY.pozisyon_var_mi(hisse):
            p    = PORTFOY.pozisyon(hisse)
            cevap = QMessageBox.question(
                self, f"{hisse} — Pozisyon Kapat",
                f"Güncel fiyat (₺{fiyat:.2f}) ile kapat?",
                QMessageBox.StandardButton.Yes |
                QMessageBox.StandardButton.No  |
                QMessageBox.StandardButton.Cancel,
            )
            if cevap == QMessageBox.StandardButton.Yes:
                PORTFOY.pozisyon_kapat(hisse, fiyat)
                self._portfoy_guncelle(hisse)
            elif cevap == QMessageBox.StandardButton.No:
                cikis, ok = QInputDialog.getDouble(
                    self, "Çıkış Fiyatı", f"{hisse} çıkış fiyatı (₺):",
                    value=round(fiyat, 2), min=0.01, max=999999.99, decimals=2)
                if ok:
                    PORTFOY.pozisyon_kapat(hisse, cikis)
                    self._portfoy_guncelle(hisse)
        else:
            lot, ok = QInputDialog.getInt(
                self, f"{hisse} — Pozisyon Aç",
                f"Giriş fiyatı: ₺{fiyat:.2f}\nLot / Adet sayısı:",
                value=1, min=1, max=1_000_000)
            if ok:
                PORTFOY.pozisyon_ac(hisse, fiyat, lot)
                self._portfoy_guncelle(hisse)

    def _portfoy_guncelle(self, hisse: str):
        if PORTFOY.pozisyon_var_mi(hisse):
            p = PORTFOY.pozisyon(hisse)
            self.btn_portfoy.setStyleSheet(
                f"QPushButton{{background:#0a3d1f;border:1px solid {C_GREEN};"
                f"border-radius:10px;font-size:15px;padding:0;color:{C_GREEN};}}"
                f"QPushButton:hover{{background:#0d4f28;}}")
            self.btn_portfoy.setToolTip(
                f"Pozisyon açık — ₺{p['giris']:.2f} · {p['lot']} lot")
        else:
            self.btn_portfoy.setStyleSheet(
                f"QPushButton{{background:{C_CARD2};border:none;"
                f"border-radius:10px;font-size:15px;padding:0;color:{C_MUTED};}}"
                f"QPushButton:hover{{background:#0a3d1f;color:{C_GREEN};}}")
            self.btn_portfoy.setToolTip("Pozisyon aç")

    def _rr_guncelle(self, sonuc: dict):
        fiyat = sonuc.get('fiyat', 0)
        if fiyat <= 0:
            return
        kutu      = sonuc.get('kutu')
        destekler = sonuc.get('destekler', [])
        direncler = sonuc.get('direncler', [])

        stop  = kutu['destek']  if kutu      else (destekler[0] if destekler else fiyat * 0.95)
        hedef = kutu['direnc']  if kutu      else (direncler[0] if direncler else fiyat * 1.10)
        stop_mesafe  = max(fiyat - stop, fiyat * 0.005)
        hedef_mesafe = hedef - fiyat
        rr           = hedef_mesafe / stop_mesafe if stop_mesafe > 0 else 0
        max_risk_tl  = RISK_AYAR.sermaye * RISK_AYAR.max_risk_pct / 100
        lot          = int(max_risk_tl / stop_mesafe) if stop_mesafe > 0 else 0
        rr_renk      = C_GREEN if rr >= 2 else C_ORANGE if rr >= 1.5 else C_RED

        def _sp(lbl, txt, renk=C_MUTED):
            lbl.setText(txt)
            lbl.setStyleSheet(
                f"color:{renk}; font-size:11px; font-weight:600; "
                f"background:{C_CARD2}; border-radius:6px; padding:2px 9px; border:none;")

        _sp(self._rr_stop,  f"Stop ₺{stop:.2f}",    C_RED)
        _sp(self._rr_hedef, f"Hedef ₺{hedef:.2f}",  C_GREEN)
        _sp(self._rr_oran,  f"R:R  1:{rr:.1f}",     rr_renk)
        _sp(self._rr_risk,  f"Risk ₺{max_risk_tl:.0f}", C_ORANGE)
        _sp(self._rr_lot,   f"Lot {lot:,}",          C_TEXT)

        hisse   = sonuc.get('hisse', '')
        periyot = sonuc.get('periyot', '1d')
        bt = BACKTEST_SONUCLARI.al(hisse, periyot)
        if bt:
            oran   = bt.get('oran', 0)
            toplam = bt.get('toplam', 0)
            bt_renk = C_GREEN if oran >= 60 else C_ORANGE if oran >= 40 else C_RED
            _sp(self._rr_bt, f"BT %{oran:.0f}  ·  {toplam} sin.", bt_renk)
            self._rr_bt.setVisible(True)
        else:
            self._rr_bt.setVisible(False)

    def _neden_ac(self):
        if self._sonuc:
            NedenDialog(self._sonuc, self).exec()

    def _kap_ac(self):
        if not self._sonuc:
            return
        hisse = self._sonuc.get('hisse', '')
        if self._kap_thread and self._kap_thread.isRunning():
            return
        self.btn_kap.setText("⏳")
        self.btn_kap.setEnabled(False)
        self._kap_thread = KapFetchThread(hisse)
        self._kap_thread.bitti.connect(lambda d, h=hisse: self._kap_gosterdi(h, d))
        self._kap_thread.hata.connect(lambda _: self._kap_gosterdi(hisse, []))
        self._kap_thread.start()

    def _kap_gosterdi(self, hisse: str, duyurular: list):
        self.btn_kap.setText("🏛")
        self.btn_kap.setEnabled(True)
        KapDuyuruDialog(hisse, duyurular, self).exec()

    def _fvt_ac(self):
        if not self._sonuc:
            return
        hisse = self._sonuc.get('hisse', '')
        if not hisse:
            return
        url = f"https://fvt.com.tr/hisseler/yerli/{hisse}"
        QDesktopServices.openUrl(QUrl(url))

    def _tv_ac(self):
        if not self._sonuc:
            return
        hisse = self._sonuc.get('hisse', '')
        if not hisse:
            return
        from urllib.parse import quote
        url = f"https://tr.tradingview.com/chart/nYqyB7GQ/?symbol=BIST%3A{hisse}"
        QDesktopServices.openUrl(QUrl(url))

    def _risk_ayar_ac(self):
        RiskAyarDialog(self).exec()
        if self._sonuc:
            self._rr_guncelle(self._sonuc)

    def _skor_rehber_ac(self):
        StratejilerDialog(self).exec()

    def _kopyala(self):
        if self._sonuc:
            metin = bildirim_metni(self._sonuc)
            QApplication.clipboard().setText(metin)
            self.btn_kopyala.setText("✅")
            QTimer.singleShot(2000, lambda: self.btn_kopyala.setText("📋"))

    def _favori_toggle(self):
        if not self._sonuc:
            return
        hisse  = self._sonuc.get('hisse', '')
        fiyat  = self._sonuc.get('fiyat', 0)
        periyot = self._sonuc.get('periyot', '1d')
        sinyal  = self._sonuc.get('genel_sinyal', '')
        eklendi = FAVORILER.toggle(hisse, fiyat, periyot, sinyal)
        self._star_guncelle(hisse, fiyat)

    def _star_guncelle(self, hisse: str, fiyat: float):
        fav = FAVORILER.al(hisse)
        if fav:
            self.btn_favori.setText("★")
            self.btn_favori.setStyleSheet(
                f"QPushButton{{background:#3a2c00;border:none;"
                f"border-radius:10px;font-size:18px;padding:0;color:#ffd60a;}}"
                f"QPushButton:hover{{background:#4a3a00;}}")
            giren = fav.get('fiyat', fiyat)
            perf  = (fiyat - giren) / giren * 100 if giren else 0
            p_renk = C_GREEN if perf >= 0 else C_RED
            p_txt  = f"+{perf:.1f}%" if perf >= 0 else f"{perf:.1f}%"
            self.lbl_perf.setText(p_txt)
            self.lbl_perf.setStyleSheet(f"font-size:13px; font-weight:600; color:{p_renk};")
        else:
            self.btn_favori.setText("☆")
            self.btn_favori.setStyleSheet(
                f"QPushButton{{background:{C_CARD2};border:none;"
                f"border-radius:10px;font-size:18px;padding:0;color:{C_MUTED};}}"
                f"QPushButton:hover{{background:#3a2e00;color:#ffd60a;}}")
            self.lbl_perf.setText("")

    def guncelle(self, sonuc: dict):
        self._sonuc = sonuc
        hisse   = sonuc.get('hisse', '?')
        fiyat   = sonuc.get('fiyat', 0)
        genel   = sonuc.get('genel_sinyal', 'NÖTR')
        periyot = sonuc.get('periyot', '1d')
        periyot_ad = PERIYOT_ADLARI.get(periyot, '')

        # Periyot butonlarını senkronize et
        self._detay_periyot = periyot
        for k, btn in self._detay_per_btn.items():
            btn.setChecked(k == periyot)
            btn.setStyleSheet(_seg_btn_stili(k == periyot))

        self.lbl_hisse.setText(hisse)
        self.lbl_fiyat.setText(f"₺ {fiyat:,.2f}")
        self.lbl_tarih.setText(
            f"{periyot_ad}  ·  {datetime.now().strftime('%d.%m.%Y %H:%M')}")
        self._star_guncelle(hisse, fiyat)
        self._alarm_guncelle(hisse)
        self._portfoy_guncelle(hisse)
        self.btn_fvt.setEnabled(True)
        self.btn_tv.setEnabled(True)

        renk = SINYAL_RENK.get(genel, C_MUTED)
        bg   = sinyal_bg(genel)
        mum_form = sonuc.get('mum_formasyon', '')
        if genel == "YÜKSELİŞ FORMASYONU" and mum_form:
            self.lbl_sinyal_btn.setText(f"{genel}\n{mum_form}")
            self.lbl_sinyal_btn.setFixedWidth(180)
        else:
            self.lbl_sinyal_btn.setText(genel)
            self.lbl_sinyal_btn.setFixedWidth(155)
        self.lbl_sinyal_btn.setStyleSheet(
            f"background-color:{bg}; color:{renk}; border-radius:8px; "
            f"padding:4px 10px; font-weight:700; font-size:12px;")

        # Gösterge kartlarını güncelle
        tanim = [
            ('rsi',       f"{sonuc.get('rsi',0):.0f}", 'rsi_sinyal',       'rsi_yorum'),
            ('trend',     sonuc.get('trend_yorum',''), 'trend_sinyal',      'trend_yorum'),
            ('macd',      f"{sonuc.get('macd',0):.3f}",'macd_sinyal',      'macd_yorum'),
            ('bollinger', sonuc.get('bollinger_yorum',''), 'bollinger_sinyal','bollinger_yorum'),
            ('stokastik', f"{sonuc.get('stokastik',0):.0f}", 'stokastik_sinyal','stokastik_yorum'),
            ('momentum',  f"%{sonuc.get('momentum',0):.1f}", 'momentum_sinyal', 'momentum_yorum'),
        ]
        basliklar = {
            'rsi':'RSI  14 Periyot', 'trend':'Trend (SMA)  50/200 Gün',
            'macd':'MACD  12,26,9',  'bollinger':'Bollinger  20, 2',
            'stokastik':'Stokastik  %K(14), %D(3)', 'momentum':'Momentum  10 Günlük',
        }
        pozisyonlar = {
            'rsi':(0,0),'trend':(0,1),'macd':(0,2),
            'bollinger':(1,0),'stokastik':(1,1),'momentum':(1,2),
        }
        for anahtar, deger, sinyal_k, yorum_k in tanim:
            sinyal = sonuc.get(sinyal_k, 'NÖTR')
            yorum  = sonuc.get(yorum_k, '')
            yeni_kart = GostergekKart(basliklar[anahtar], deger, sinyal, yorum)
            satir, sutun = pozisyonlar[anahtar]
            eski = self.grid.itemAtPosition(satir, sutun)
            if eski:
                eski.widget().deleteLater()
            self.grid.addWidget(yeni_kart, satir, sutun)

        # ── Teknik özet satırı (pill badge'ler) ──
        rsi_val  = sonuc.get('rsi', 0)
        macd_val = sonuc.get('macd', 0)
        ema_sir  = sonuc.get('ema_sir')
        hacim    = sonuc.get('hacim')

        def _pill(fg, bg, text):
            return (f"color:{fg}; font-size:11px; font-weight:600; background:{bg}; "
                    f"border-radius:6px; padding:2px 9px; border:none;")

        rsi_c, rsi_bg = ((C_RED, "#2d0f0f") if rsi_val >= 70 else
                         (C_GREEN, C_GREEN_DIM) if rsi_val <= 30 else
                         (C_MUTED, C_CARD2))
        macd_c, macd_bg = ((C_GREEN, C_GREEN_DIM) if macd_val > 0 else
                           (C_RED, C_RED_DIM) if macd_val < 0 else
                           (C_MUTED, C_CARD2))
        ema_c,  ema_bg  = (C_GREEN, C_GREEN_DIM) if ema_sir else (C_MUTED, C_CARD2)
        vol_c,  vol_bg  = (C_GREEN, C_GREEN_DIM) if hacim else (C_MUTED, C_CARD2)

        self._ozet_rsi.setText(f"RSI  {rsi_val:.0f}")
        self._ozet_rsi.setStyleSheet(_pill(rsi_c, rsi_bg, ''))
        self._ozet_macd.setText(f"MACD  {macd_val:+.3f}")
        self._ozet_macd.setStyleSheet(_pill(macd_c, macd_bg, ''))
        self._ozet_ema.setText("EMA  ✓" if ema_sir else "EMA  —")
        self._ozet_ema.setStyleSheet(_pill(ema_c, ema_bg, ''))
        vol_txt = f"Vol  {hacim['hacim_orani']:.1f}×" if hacim else "Vol  —"
        self._ozet_vol.setText(vol_txt)
        self._ozet_vol.setStyleSheet(_pill(vol_c, vol_bg, ''))

        # Skor kırılımı
        skor_val = sonuc.get('sinyal_gucu', 0)
        skor_renk = C_GREEN if skor_val >= 8 else C_ORANGE if skor_val >= 5 else C_MUTED
        self.lbl_skor_sayi.setText(str(skor_val))
        self.lbl_skor_sayi.setStyleSheet(
            f"font-size:16px; font-weight:800; background:transparent; color:{skor_renk};")
        while self._skor_pills_lay.count():
            it = self._skor_pills_lay.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        for etiket, puan, renk in skor_kirilim(sonuc):
            isaret = f"+{puan}" if puan > 0 else str(puan)
            pill = QLabel(f"{etiket} {isaret}")
            pill.setStyleSheet(
                f"color:{renk}; font-size:10px; font-weight:600; "
                f"background:{C_CARD2}; border-radius:5px; padding:1px 6px; border:none;")
            self._skor_pills_lay.addWidget(pill)

        # Risk/Ödül şeridini güncelle
        self._rr_guncelle(sonuc)

        # MTF badge
        mtf_sayi = sonuc.get('mtf_sayi', 0)
        # MTF pill → skor kırılımı alanına ekle
        if mtf_sayi >= 2:
            mtf_pill = QLabel(f"🔀 {mtf_sayi}× Periyot")
            mtf_pill.setStyleSheet(
                f"color:#f97316; font-size:10px; font-weight:700; "
                f"background:#3a1800; border-radius:5px; padding:1px 8px; border:none;")
            self._skor_pills_lay.addWidget(mtf_pill)

        # Not butonu rengini ve notu güncelle
        metin = NOTLAR.al(hisse)
        self.lbl_not_goster.setVisible(bool(metin))
        self.lbl_not_goster.setText(f"📝  {metin}" if metin else "")
        if NOTLAR.var_mi(hisse):
            self.btn_not.setStyleSheet(
                f"QPushButton{{background:#3a2e00;border:none;"
                f"border-radius:10px;font-size:15px;padding:0;color:#ffd60a;}}"
                f"QPushButton:hover{{background:#4a3a00;color:#ffe066;}}")
        else:
            self.btn_not.setStyleSheet(
                f"QPushButton{{background:{C_CARD2};border:none;"
                f"border-radius:10px;font-size:15px;padding:0;color:{C_MUTED};}}"
                f"QPushButton:hover{{background:#3a2e00;color:#ffd60a;}}")

        # Grafik
        df_g = sonuc.get('df_grafik')
        gecmis_sinyaller = None
        if self._sig_goster:
            gecmis_sinyaller = self._gecmis_isaretleri_hesapla(hisse, periyot, df_g)
        self.grafik.guncelle(
            df_g,
            sonuc.get('destekler', [])[:3],
            sonuc.get('direncler', [])[:3],
            hisse,
            sonuc.get('kutu'),
            ema_goster=self._ema_goster,
            ha_goster=self._ha_goster,
            vp_goster=self._vp_goster,
            gecmis_sinyaller=gecmis_sinyaller,
            cizgiler=CIZGILER.yukle(hisse, periyot),
        )

    def temizle(self):
        self.lbl_hisse.setText("—")
        self.lbl_fiyat.setText("")
        self.lbl_tarih.setText("")
        self.lbl_sinyal_btn.setText("")
        _muted = f"color:{C_MUTED}; font-size:11px; font-weight:500; background:transparent; border:none;"
        for lbl in (self._ozet_rsi, self._ozet_macd, self._ozet_ema, self._ozet_vol):
            lbl.setText(lbl.text().split(':')[0] + ': —')
            lbl.setStyleSheet(_muted)
        self._sonuc = None

# ═══════════════════════════════════════════════════════════
# Tarama İş Parçacığı
# ═══════════════════════════════════════════════════════════
class TaramaThread(QThread):
    ilerleme     = pyqtSignal(int, int, str)
    sinyal_buldu = pyqtSignal(dict)
    bitti        = pyqtSignal(int, int)

    def __init__(self, hisseler, periyotlar):
        super().__init__()
        self.hisseler  = hisseler
        self.periyotlar = periyotlar
        self._dur      = False

    def dur(self):
        self._dur = True

    def run(self):
        gun_sayilari = {"1h": 3, "4h": 18, "1d": 3, "1w": 3, "1mo": 3}
        al_n = sat_n = 0
        toplam = len(self.hisseler) * len(self.periyotlar)
        say = 0
        _mtf_sayac: dict = {}   # hisse → al sinyal periyot sayısı

        for periyot in self.periyotlar:
            if self._dur:
                break
            # Tüm hisseleri tek seferde indir
            self.ilerleme.emit(say, toplam, f"İndiriliyor ({periyot})…")
            veri_map = veri_cek_toplu(self.hisseler, periyot)

            for hisse in self.hisseler:
                if self._dur:
                    break
                say += 1
                self.ilerleme.emit(say, toplam, hisse)
                df = veri_map.get(hisse)
                if df is not None:
                    sonuc = sinyal_hesapla(df, periyot, gun_sayilari[periyot])
                    if sonuc and sonuc.get('genel_sinyal') != 'NÖTR':
                        sonuc['hisse'] = hisse
                        genel_s = sonuc['genel_sinyal']
                        if genel_s in SINYAL_RENK and genel_s not in (
                                "GÜÇLÜ SAT", "SAT", "NÖTR", "MACD ÖLÜ", "DESTEK KIRILDI"):
                            al_n += 1
                            _mtf_sayac[hisse] = _mtf_sayac.get(hisse, 0) + 1
                            GECMIS.kaydet(hisse, genel_s, sonuc['fiyat'], periyot)
                        else:
                            sat_n += 1
                        sonuc['mtf_sayi'] = _mtf_sayac.get(hisse, 0)
                        self.sinyal_buldu.emit(sonuc)

        self.bitti.emit(al_n, sat_n)


class TekHisseFetchThread(QThread):
    """Tek bir hisse için arka planda veri çeker (favoriler için)."""
    bitti = pyqtSignal(dict)
    hata  = pyqtSignal(str, str)   # (hisse, sebep)

    def __init__(self, hisse: str, periyot: str):
        super().__init__()
        self.hisse   = hisse
        self.periyot = periyot

    def run(self):
        gun_sayilari = {"1h": 3, "4h": 18, "1d": 3, "1w": 3, "1mo": 1}
        try:
            df = veri_cek(self.hisse, self.periyot)
        except Exception as e:
            self.hata.emit(self.hisse, f"Veri indirilemedi: {e}")
            return
        if df is None:
            self.hata.emit(self.hisse,
                "Yahoo Finance'den veri alınamadı. "
                "Hisse sembolü yanlış veya hisse işlem dışı olabilir.")
            return
        # Günlük olmayan periyotlarda EMAlar için günlük close çek
        close_gunluk = None
        if self.periyot != "1d":
            df_gun = veri_cek(self.hisse, "1d")
            if df_gun is not None and 'Close' in df_gun.columns:
                close_gunluk = df_gun['Close']
        try:
            sonuc = sinyal_hesapla(df, self.periyot, gun_sayilari.get(self.periyot, 3),
                                   close_gunluk=close_gunluk)
        except Exception as e:
            self.hata.emit(self.hisse, f"Sinyal hesaplama hatası: {e}")
            return
        if sonuc:
            sonuc['hisse'] = self.hisse
            self.bitti.emit(sonuc)
        else:
            self.hata.emit(self.hisse,
                f"Bu periyotta ({self.periyot}) yeterli veri yok veya sinyal üretilemedi.")

# ═══════════════════════════════════════════════════════════
# Backtest Thread
# ═══════════════════════════════════════════════════════════
class BacktestThread(QThread):
    ilerleme = pyqtSignal(int, int)
    bitti    = pyqtSignal(list, dict)

    # periyot → (yf period, yf interval, resample?, bekleme bar, tarih fmt)
    _CFG = {
        '1h': ('730d', '1h', False, 20,  '%d.%m.%Y %H:%M'),
        '4h': ('730d', '1h', True,  10,  '%d.%m.%Y %H:%M'),
        '1d': ('2y',   '1d', False, 10,  '%d.%m.%Y'),
    }

    def __init__(self, hisse: str, periyot: str = '1d', hedef_pct: float = 5.0):
        super().__init__()
        self.hisse     = hisse
        self.periyot   = periyot
        self.hedef_pct = hedef_pct
        self._dur      = False

    def dur(self):
        self._dur = True

    def run(self):
        import yfinance as yf
        from tarayici import _sutunlari_duzenle, sinyal_hesapla as _sh

        yf_per, yf_int, resample, bekleme, tarih_fmt = self._CFG.get(
            self.periyot, ('2y', '1d', False, 10, '%d.%m.%Y'))

        df_ham = yf.download(f"{self.hisse}.IS", period=yf_per, interval=yf_int,
                             auto_adjust=True, progress=False)
        if df_ham is None or df_ham.empty:
            self.bitti.emit([], {})
            return

        df_ham = _sutunlari_duzenle(df_ham).dropna()

        if resample:
            df_ham = df_ham.resample('4h').agg({
                'Open': 'first', 'High': 'max',
                'Low': 'min', 'Close': 'last', 'Volume': 'sum',
            }).dropna()

        n = len(df_ham)
        if n < 60:
            self.bitti.emit([], {})
            return

        HEDEF_PCT = self.hedef_pct
        kayitlar  = []

        for i in range(50, n - bekleme):
            if self._dur:
                break
            self.ilerleme.emit(i - 50, n - 50 - bekleme)
            try:
                pencere = df_ham.iloc[:i + 1]          # copy() gereksiz — _sh df'yi değiştirmiyor
                sonuc   = _sh(pencere, self.periyot, 3, grafik=False)
                if sonuc is None:
                    continue
                genel = sonuc.get('genel_sinyal', 'NÖTR')
                if genel in ('NÖTR', 'SAT', 'GÜÇLÜ SAT'):
                    continue

                giris   = float(df_ham['Close'].iloc[i])
                h_yuk   = df_ham['High'].iloc[i + 1: i + 1 + bekleme]
                h_dus   = df_ham['Low'].iloc[i + 1: i + 1 + bekleme]
                max_yuk = float(h_yuk.max())
                min_dus = float(h_dus.min())
                kar_pct = (max_yuk - giris) / giris * 100
                dd_pct  = (min_dus - giris) / giris * 100

                kayitlar.append({
                    'tarih':     df_ham.index[i].strftime(tarih_fmt),
                    'sinyal':    genel,
                    'giris':     round(giris, 2),
                    'max_cikis': round(max_yuk, 2),
                    'kar_pct':   round(kar_pct, 2),
                    'max_dd':    round(dd_pct, 2),
                    'basari':    kar_pct >= HEDEF_PCT,
                    'skor':      sonuc.get('sinyal_gucu', 0),
                })
            except Exception:
                continue

        if not kayitlar:
            self.bitti.emit([], {})
            return

        toplam   = len(kayitlar)
        basarili = sum(1 for k in kayitlar if k['basari'])
        kar_list = [k['kar_pct'] for k in kayitlar]

        istatistik = {
            'toplam':   toplam,
            'basarili': basarili,
            'oran':     round(basarili / toplam * 100, 1) if toplam else 0,
            'ort_kar':  round(sum(kar_list) / toplam, 2) if toplam else 0,
            'en_iyi':   round(max(kar_list), 2) if kar_list else 0,
            'en_kotu':  round(min(kar_list), 2) if kar_list else 0,
        }

        self.bitti.emit(list(reversed(kayitlar)), istatistik)


# ═══════════════════════════════════════════════════════════
# Portföy Fiyat Güncelleme Thread
# ═══════════════════════════════════════════════════════════
class PortfoyGuncellemeThread(QThread):
    bitti = pyqtSignal(dict)

    def run(self):
        import yfinance as yf
        from tarayici import _sutunlari_duzenle
        hisseler = list(PORTFOY.aktif_listesi().keys())
        fiyatlar = {}
        for h in hisseler:
            try:
                df = yf.download(f"{h}.IS", period="2d", interval="1d",
                                 auto_adjust=True, progress=False)
                if df is not None and not df.empty:
                    df = _sutunlari_duzenle(df)
                    fiyatlar[h] = float(df['Close'].iloc[-1])
            except Exception:
                pass
        self.bitti.emit(fiyatlar)


# ═══════════════════════════════════════════════════════════
# KAP Duyuru Thread
# ═══════════════════════════════════════════════════════════
class KapFetchThread(QThread):
    bitti = pyqtSignal(list)
    hata  = pyqtSignal(str)

    def __init__(self, hisse: str):
        super().__init__()
        self.hisse = hisse

    def run(self):
        import requests as _req
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0',
                'Accept': 'application/json',
                'Referer': 'https://www.kap.org.tr/',
            }
            url = 'https://www.kap.org.tr/tr/api/memberDisclosureQuery'
            r = _req.get(url, params={'memberCode': self.hisse, 'isLast': '1'},
                        headers=headers, timeout=12)
            if r.status_code == 200:
                data = r.json()
                duyurular = []
                for item in (data if isinstance(data, list) else [])[:15]:
                    duyurular.append({
                        'baslik': item.get('title') or item.get('disclosureType', '—'),
                        'tarih':  item.get('publishDate', ''),
                        'tur':    item.get('disclosureType', ''),
                        'ozet':   item.get('summary', ''),
                    })
                self.bitti.emit(duyurular)
                return
        except Exception:
            pass
        self.hata.emit(self.hisse)


# ═══════════════════════════════════════════════════════════
# Sinyal Liste Satırı
# ═══════════════════════════════════════════════════════════
def _liste_satiri_olustur(sonuc: dict, pin_cb=None) -> QListWidgetItem:
    hisse   = sonuc.get('hisse', '?')
    genel   = sonuc.get('genel_sinyal', 'NÖTR')
    fiyat   = sonuc.get('fiyat', 0)
    periyot = PERIYOT_ADLARI.get(sonuc.get('periyot', '1d'), '')
    fav_ek  = sonuc.get('_fav_ek', False)   # taramada yok, favoriden eklendi
    sabitlenen = SABITLENMIS.sabitlenen(hisse)

    item = QListWidgetItem(f"  {hisse}   {fiyat:.2f} ₺")

    widget = QWidget()
    if sabitlenen:
        widget.setStyleSheet("background:#1a1300; border-radius:8px;")
    layout = QHBoxLayout(widget)
    layout.setContentsMargins(8, 4, 8, 4)

    fav = FAVORILER.al(hisse)
    star_txt  = "★ " if fav else ""
    star_renk = "#f59e0b" if fav else C_TEXT
    lbl_h = QLabel(f"{star_txt}{hisse}")
    lbl_h.setStyleSheet(f"color:{star_renk}; font-weight:600; font-size:13px; background:transparent;")

    lbl_p = QLabel(periyot)
    lbl_p.setStyleSheet(f"color:{C_MUTED}; font-size:11px; background:transparent;")

    renk = SINYAL_RENK.get(genel, C_MUTED)
    sb   = sinyal_bg(genel)
    lbl_s = QLabel(genel if not fav_ek else f"★ {genel}")
    lbl_s.setStyleSheet(
        f"background-color:{sb}; color:{renk}; border-radius:4px; "
        f"padding:1px 7px; font-weight:700; font-size:11px;")

    fiyat_txt = f"giriş ₺{fiyat:,.2f}" if fav_ek else f"₺{fiyat:,.2f}"
    lbl_f = QLabel(fiyat_txt)
    lbl_f.setStyleSheet(f"color:{C_MUTED}; font-size:11px; background:transparent;")

    layout.addWidget(lbl_h)
    layout.addSpacing(4)
    layout.addWidget(lbl_p)
    layout.addStretch()

    if fav:
        tarih = fav.get('tarih', '')
        giren = fav.get('fiyat', fiyat)
        if fav_ek:
            # Taramada yok — sadece kayıt tarihi
            lbl_tarih_fav = QLabel(tarih)
            lbl_tarih_fav.setStyleSheet(f"color:{C_MUTED}; font-size:10px; background:transparent;")
            layout.addWidget(lbl_tarih_fav)
            layout.addSpacing(4)
        else:
            # Taramada var — % performans + tarih
            perf   = (fiyat - giren) / giren * 100 if giren else 0
            p_renk = C_GREEN if perf >= 0 else C_RED
            p_txt  = f"+{perf:.1f}%" if perf >= 0 else f"{perf:.1f}%"
            lbl_perf = QLabel(p_txt)
            lbl_perf.setStyleSheet(f"color:{p_renk}; font-size:11px; font-weight:700; background:transparent;")
            layout.addWidget(lbl_perf)
            layout.addSpacing(2)
            lbl_tarih_fav = QLabel(tarih)
            lbl_tarih_fav.setStyleSheet(f"color:{C_MUTED}; font-size:10px; background:transparent;")
            layout.addWidget(lbl_tarih_fav)
            layout.addSpacing(4)

    layout.addWidget(lbl_f)
    layout.addSpacing(4)

    # Sinyal gücü skoru badge
    skor = sonuc.get('sinyal_gucu', 0)
    if skor > 0:
        skor_renk = C_GREEN  if skor >= 8 else C_ORANGE if skor >= 5 else C_MUTED
        skor_bg   = C_GREEN_DIM if skor >= 8 else "#2d1a00" if skor >= 5 else C_CARD2
        lbl_skor  = QLabel(str(skor))
        lbl_skor.setFixedSize(22, 22)
        lbl_skor.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_skor.setStyleSheet(
            f"background:{skor_bg}; color:{skor_renk}; border-radius:11px; "
            f"font-size:10px; font-weight:700; border:none;")
        layout.addWidget(lbl_skor)
        layout.addSpacing(2)

    # Pin butonu
    btn_pin = QPushButton("📌")
    btn_pin.setFixedSize(24, 24)
    btn_pin.setToolTip("Sabitle" if not sabitlenen else "Sabitlemeyi kaldır")
    _pin_aktif_qss = (
        f"QPushButton{{background:#3d2a00;border:none;border-radius:6px;"
        f"font-size:11px;padding:0;color:#f59e0b;}}"
        f"QPushButton:hover{{background:#4d3500;color:#fbbf24;}}"
    )
    _pin_pasif_qss = (
        f"QPushButton{{background:transparent;border:none;border-radius:6px;"
        f"font-size:11px;padding:0;color:#48484a;}}"
        f"QPushButton:hover{{background:#3d2a00;color:#f59e0b;}}"
    )
    btn_pin.setStyleSheet(_pin_aktif_qss if sabitlenen else _pin_pasif_qss)
    if pin_cb:
        btn_pin.clicked.connect(lambda _=False, h=hisse: pin_cb(h))
    layout.addWidget(btn_pin)
    layout.addSpacing(4)

    # MTF badge
    mtf_sayi = sonuc.get('mtf_sayi', 0)
    if mtf_sayi >= 2:
        lbl_mtf = QLabel(f"🔀{mtf_sayi}×")
        lbl_mtf.setStyleSheet(
            f"background:#3a1800; color:#f97316; border-radius:4px; "
            f"padding:1px 5px; font-size:10px; font-weight:700;")
        layout.addWidget(lbl_mtf)
        layout.addSpacing(2)

    # Not varsa küçük nokta
    if NOTLAR.var_mi(hisse):
        lbl_not_dot = QLabel("●")
        lbl_not_dot.setStyleSheet(f"color:#ffd60a; font-size:8px; background:transparent;")
        lbl_not_dot.setToolTip("Bu hisse için not mevcut")
        layout.addWidget(lbl_not_dot)
        layout.addSpacing(2)

    layout.addWidget(lbl_s)

    # Formasyon alt badge (YÜKSELİŞ FORMASYONU sinyalinde spesifik adı göster)
    mum_form = sonuc.get('mum_formasyon', '')
    if genel == "YÜKSELİŞ FORMASYONU" and mum_form:
        lbl_form = QLabel(mum_form)
        lbl_form.setStyleSheet(
            f"background:#2d1200; color:#fb923c; border-radius:4px; "
            f"padding:1px 6px; font-size:9px; font-weight:600; border:none;")
        layout.addSpacing(3)
        layout.addWidget(lbl_form)

    item.setSizeHint(QSize(0, 48))
    item.setData(Qt.ItemDataRole.UserRole, sonuc)
    return item, widget

# ═══════════════════════════════════════════════════════════
# Alarm Yönetim Diyaloğu
# ═══════════════════════════════════════════════════════════
_ALARM_MENU_QSS = f"""
QMenu {{
    background-color: {C_CARD};
    color: {C_TEXT};
    border: 1px solid {C_BORDER};
    border-radius: 10px;
    padding: 6px 4px;
    font-size: 13px;
}}
QMenu::item {{
    padding: 8px 20px 8px 14px;
    border-radius: 6px;
    margin: 1px 2px;
}}
QMenu::item:selected {{
    background-color: {C_CARD2};
    color: {C_TEXT};
}}
QMenu::separator {{
    height: 1px;
    background: {C_BORDER};
    margin: 4px 8px;
}}
"""


class AlarmYonetimDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Alarm Yönetimi")
        self.resize(500, 420)
        self.setStyleSheet(f"background:{C_BG}; color:{C_TEXT};")

        root = QVBoxLayout(self)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(12)

        # ── Başlık ──────────────────────────────
        hdr = QHBoxLayout()
        lbl_baslik = QLabel("🔔  Aktif Alarmlar")
        lbl_baslik.setStyleSheet(
            f"color:{C_TEXT}; font-size:15px; font-weight:700; background:transparent;")
        self.lbl_sayi = QLabel("")
        self.lbl_sayi.setStyleSheet(
            f"color:{C_MUTED}; font-size:11px; background:transparent;")
        hdr.addWidget(lbl_baslik)
        hdr.addStretch()
        hdr.addWidget(self.lbl_sayi)
        root.addLayout(hdr)

        # ── Tablo ───────────────────────────────
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Hisse", "Hedef Fiyat", "Eklenme", ""])
        self.table.setStyleSheet(f"""
            QTableWidget {{
                background:{C_CARD}; color:{C_TEXT}; border:none; border-radius:10px;
                gridline-color:{C_BORDER}; font-size:12px;
            }}
            QHeaderView::section {{
                background:{C_CARD2}; color:{C_MUTED}; border:none;
                padding:5px 8px; font-size:11px; font-weight:600;
            }}
            QTableWidget::item {{ padding:4px 10px; border:none; }}
            QTableWidget::item:selected {{ background:#0a84ff22; }}
        """)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(3, 70)
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setShowGrid(True)
        root.addWidget(self.table)

        # ── Alt butonlar ─────────────────────────
        alt = QHBoxLayout()
        self.btn_ekle = QPushButton("＋  Yeni Alarm")
        self.btn_ekle.setStyleSheet(
            f"QPushButton{{background:{C_BLUE};color:#fff;border:none;"
            f"border-radius:8px;font-size:12px;font-weight:600;padding:0 16px;}}"
            f"QPushButton:hover{{background:#1a8fff;}}")
        self.btn_ekle.setFixedHeight(32)
        self.btn_ekle.clicked.connect(self._yeni_ekle)

        self.btn_tumunu_sil = QPushButton("Tümünü Sil")
        self.btn_tumunu_sil.setStyleSheet(
            f"QPushButton{{background:{C_RED_DIM};color:{C_RED};border:none;"
            f"border-radius:8px;font-size:12px;font-weight:500;padding:0 14px;}}"
            f"QPushButton:hover{{background:#3d1010;}}")
        self.btn_tumunu_sil.setFixedHeight(32)
        self.btn_tumunu_sil.clicked.connect(self._tumunu_sil)

        btn_kapat = QPushButton("Kapat")
        btn_kapat.setFixedSize(80, 32)
        btn_kapat.setStyleSheet(
            f"QPushButton{{background:{C_CARD2};color:{C_MUTED};border:none;"
            f"border-radius:8px;font-size:12px;padding:0;}}"
            f"QPushButton:hover{{background:#48484a;color:{C_TEXT};}}")
        btn_kapat.clicked.connect(self.close)

        alt.addWidget(self.btn_ekle)
        alt.addSpacing(8)
        alt.addWidget(self.btn_tumunu_sil)
        alt.addStretch()
        alt.addWidget(btn_kapat)
        root.addLayout(alt)

        self._listele()

    def _listele(self):
        alarmlar = ALARMLAR.listesi()
        self.table.setRowCount(len(alarmlar))
        self.lbl_sayi.setText(f"{len(alarmlar)} alarm kurulu")

        for row, (hisse, hedef) in enumerate(alarmlar.items()):
            fav = FAVORILER.al(hisse)
            giris = fav.get('tarih', '—') if fav else '—'

            it_hisse = QTableWidgetItem(hisse)
            it_hisse.setForeground(QColor(C_TEXT))
            it_hisse.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))

            it_hedef = QTableWidgetItem(f"₺ {hedef:,.2f}")
            it_hedef.setForeground(QColor(C_ORANGE))
            it_hedef.setTextAlignment(
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight)

            it_tarih = QTableWidgetItem(giris)
            it_tarih.setForeground(QColor(C_MUTED))

            self.table.setItem(row, 0, it_hisse)
            self.table.setItem(row, 1, it_hedef)
            self.table.setItem(row, 2, it_tarih)
            self.table.setRowHeight(row, 36)

            # Sil butonu
            btn_sil = QPushButton("Sil")
            btn_sil.setStyleSheet(
                f"QPushButton{{background:{C_RED_DIM};color:{C_RED};border:none;"
                f"border-radius:6px;font-size:11px;font-weight:600;margin:4px;}}"
                f"QPushButton:hover{{background:{C_RED};color:#fff;}}")
            btn_sil.clicked.connect(lambda _, h=hisse: self._sil(h))
            self.table.setCellWidget(row, 3, btn_sil)

        tumunu_gorunum = len(alarmlar) > 1
        self.btn_tumunu_sil.setVisible(tumunu_gorunum)

    def _sil(self, hisse):
        ALARMLAR.kaldir(hisse)
        self._listele()

    def _tumunu_sil(self):
        cevap = QMessageBox.question(
            self, "Tümünü Sil",
            "Tüm alarmlar silinecek. Emin misiniz?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if cevap == QMessageBox.StandardButton.Yes:
            for h in list(ALARMLAR.listesi().keys()):
                ALARMLAR.kaldir(h)
            self._listele()

    def _yeni_ekle(self):
        hisse, ok = QInputDialog.getText(
            self, "Yeni Alarm", "Hisse kodu girin  (örn: THYAO):",
        )
        if not ok or not hisse.strip():
            return
        hisse = hisse.strip().upper()
        hedef, ok = QInputDialog.getDouble(
            self, "Hedef Fiyat",
            f"{hisse} için hedef fiyat girin (₺):",
            value=0.0, min=0.01, max=999999.99, decimals=2,
        )
        if ok:
            ALARMLAR.ekle(hisse, hedef)
            self._listele()


# ═══════════════════════════════════════════════════════════
# Sinyal Geçmişi Diyaloğu
# ═══════════════════════════════════════════════════════════
class GecmisDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Sinyal Geçmişi")
        self.resize(700, 500)
        self.setStyleSheet(f"background:{C_BG}; color:{C_TEXT};")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        lbl = QLabel("Son 200 Sinyal")
        lbl.setStyleSheet(f"color:{C_TEXT}; font-size:15px; font-weight:700;")
        layout.addWidget(lbl)

        table = QTableWidget()
        table.setColumnCount(5)
        table.setHorizontalHeaderLabels(["Tarih", "Hisse", "Sinyal", "Fiyat", "Periyot"])
        table.setStyleSheet(f"""
            QTableWidget {{
                background:{C_CARD}; color:{C_TEXT}; border:none; border-radius:10px;
                gridline-color:{C_BORDER}; font-size:12px;
            }}
            QHeaderView::section {{
                background:{C_CARD2}; color:{C_MUTED}; border:none; padding:4px 8px;
                font-size:11px; font-weight:600;
            }}
            QTableWidget::item {{ padding:4px 8px; border:none; }}
            QTableWidget::item:selected {{ background:#0a84ff22; }}
        """)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        table.verticalHeader().setVisible(False)
        table.setAlternatingRowColors(False)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setShowGrid(True)

        kayitlar = GECMIS.yukle(200)
        table.setRowCount(len(kayitlar))
        for row, k in enumerate(kayitlar):
            genel = k.get('sinyal', '')
            renk  = SINYAL_RENK.get(genel, C_MUTED)
            items = [
                QTableWidgetItem(k.get('tarih', '')),
                QTableWidgetItem(k.get('hisse', '')),
                QTableWidgetItem(genel),
                QTableWidgetItem(f"₺{k.get('fiyat', 0):,.2f}"),
                QTableWidgetItem(PERIYOT_ADLARI.get(k.get('periyot', ''), k.get('periyot', ''))),
            ]
            for col, it in enumerate(items):
                it.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
                if col == 2:
                    it.setForeground(QColor(renk))
                table.setItem(row, col, it)
            table.setRowHeight(row, 30)

        layout.addWidget(table)

        btn_kapat = QPushButton("Kapat")
        btn_kapat.setFixedWidth(100)
        btn_kapat.clicked.connect(self.close)
        hbox = QHBoxLayout()
        hbox.addStretch()
        hbox.addWidget(btn_kapat)
        layout.addLayout(hbox)


# ═══════════════════════════════════════════════════════════
# Skor Açıklama Diyaloğu
# ═══════════════════════════════════════════════════════════
_SKOR_TABLOSU = [
    # (Bileşen, Puan, Açıklama)
    ("MACD Kesişim  —  bu mumda",  "+3", "Histogram tam şu an sıfırı kesti. En taze sinyal."),
    ("MACD Kesişim  —  1 mum önce","+2", "Geçen mumda kesti, momentum devam ediyor."),
    ("MACD Yaklaşım",               "+1", "Histogram negatif ama ~1-2 bar içinde kesecek."),
    ("Hacim Kırılımı  1.5–2×",     "+1", "Hacim normalin 1.5-2 katı + zirve kırıldı."),
    ("Hacim Kırılımı  2–3×",       "+2", "Hacim 2-3 katı. Kurumsal alım izleri."),
    ("Hacim Kırılımı  3×+",        "+3", "Hacim 3 katı üstü. Güçlü kurumsal katılım."),
    ("Kutu Konsolidasyon",         "+2", "30 günlük dar bant, destek çoklu test edilmiş."),
    ("Destek / Dip Sıçrama",       "+1", "Pivot destekte ya da 30 günlük dipten sekiyor."),
    ("EMA Sıralama  (eski)",       "+1", "EMA5>8>13>21 tam hizalı ama yeni değil."),
    ("EMA Sıralama  (yeni ✨)",    "+2", "Hizalama son 5 barda oluştu. Erken giriş fırsatı."),
    ("RSI < 35",                   "+1", "Aşırı satım bölgesi. Dönüş olasılığı artar."),
    ("RSI Diverjans",              "+1", "Fiyat dip yaparken RSI yapmıyor."),
    ("RSI Diverjans  (RSI < 45)",  "+2", "Oversold'da diverjans. Daha güçlü dönüş sinyali."),
    ("EMA21 Pullback",             "+1", "Yükselen trende EMA21'e geri gelip döndü."),
    ("Bollinger Sıkışma",          "+1", "60 günlük en dar bant. Patlama yakın."),
    ("Mum Formasyonu",             "+1", "Çekiç veya Yutan mum oluştu."),
    ("Mum Formasyonu  (destek)",   "+2", "Çekiç/Yutan destek bölgesinde oluştu."),
    ("Trend (SMA50) AL",           "+1", "Fiyat 50 günlük ortalama üstünde."),
    ("RSI > 65",                   "−1", "Aşırı alıma yaklaşıyor. Uyarı."),
    ("MACD Ölüm Kesişimi",        "−2", "Histogram pozitiften negatife döndü."),
    ("Destek Kırıldı",             "−2", "Fiyat en yakın desteğin %1 altına geçti."),
]

class SkorAciklamaDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Skor Nasıl Hesaplanır?")
        self.resize(600, 520)
        self.setStyleSheet(f"background:{C_BG}; color:{C_TEXT};")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)

        baslik = QLabel("🔢  Sinyal Skoru Hesaplama  (1–10)")
        baslik.setStyleSheet(f"font-size:15px; font-weight:700; color:{C_TEXT};")
        layout.addWidget(baslik)

        acik = QLabel(
            "Her aktif bileşen puana katkı sağlar. Toplam 1–10 arasına sıkıştırılır.\n"
            "Aynı anda birden fazla bileşen aktifse puanlar toplanır."
        )
        acik.setStyleSheet(
            f"color:{C_MUTED}; font-size:11px; background:{C_CARD}; "
            f"border-radius:8px; padding:8px;")
        acik.setWordWrap(True)
        layout.addWidget(acik)

        tablo = QTableWidget(len(_SKOR_TABLOSU), 3)
        tablo.setHorizontalHeaderLabels(["Bileşen", "Puan", "Açıklama"])
        tablo.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        tablo.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        tablo.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        tablo.verticalHeader().setVisible(False)
        tablo.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        tablo.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        tablo.setShowGrid(False)
        tablo.setStyleSheet(f"""
            QTableWidget {{background:{C_CARD};color:{C_TEXT};border:none;
                border-radius:10px;font-size:12px;}}
            QHeaderView::section {{background:{C_CARD2};color:{C_MUTED};border:none;
                padding:5px 8px;font-size:11px;font-weight:600;}}
            QTableWidget::item {{padding:5px 8px;border-bottom:1px solid {C_BORDER};}}
        """)

        for satir, (bilesen, puan, aciklama) in enumerate(_SKOR_TABLOSU):
            tablo.setItem(satir, 0, QTableWidgetItem(bilesen))
            puan_item = QTableWidgetItem(puan)
            puan_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            renk = C_GREEN if puan.startswith("+") else C_RED
            puan_item.setForeground(QColor(renk))
            tablo.setItem(satir, 1, puan_item)
            tablo.setItem(satir, 2, QTableWidgetItem(aciklama))

        layout.addWidget(tablo)

        kapat = QPushButton("Kapat")
        kapat.setFixedHeight(36)
        kapat.setStyleSheet(
            f"QPushButton{{background:{C_CARD2};color:{C_TEXT};border:none;"
            f"border-radius:8px;font-size:13px;}}"
            f"QPushButton:hover{{background:{C_BORDER};}}")
        kapat.clicked.connect(self.accept)
        layout.addWidget(kapat)


# ═══════════════════════════════════════════════════════════
# Strateji Rehberi Diyaloğu
# ═══════════════════════════════════════════════════════════
_STRATEJILER = [
    ("KUTU+MACD",      "#fbbf24", "En güçlü kombinasyon",
     "Fiyat yatay konsolidasyon kutusunda sıkışmış ve aynı anda MACD histogramı "
     "sıfırı yukarı kesiyor. Kurumsal birikim + ivme kırılımı bir arada. "
     "Çıkış yönü genellikle yukarı. Hedef: kutunun en az 1× genişliği kadar hareket."),

    ("HACİM+MACD",     "#4ade80", "Kurumsal alım + momentum",
     "Son N barın zirvesi kırılırken hacim ortalamanın 1.5× üstünde ve MACD kesişimi "
     "de eşzamanlı gerçekleşiyor. 'Akıllı para' devreye girmiş gibi düşünülebilir. "
     "Stop: kırılan direnç seviyesinin biraz altı."),

    ("KUTU AL",        "#f59e0b", "Yatay konsolidasyon",
     "Fiyat 30 günlük dar bir bantta hareket etmiş, alt desteğe en az 2 kez "
     "dokunmuş ve son 3 kapanış desteğin üstünde. MACD henüz kesişmedi ama "
     "bant sıkışması kırılım beklentisi yaratıyor."),

    ("HACİM KIRILIM",  "#fcd34d", "Hacim destekli kırılım",
     "Fiyat son 20 barın yüksek seviyesini kırıyor, hacim normalin 1.5× üstünde, "
     "ve son mum yükseliş mumu. MACD teyidi yok ama hacim güçlü katılımı işaret ediyor. "
     "Yanıltıcı kırılım riskine karşı dar stop kullan."),

    ("MACD KESİŞİM",   "#38bdf8", "Taze momentum başlangıcı",
     "MACD histogramı son 1-2 mumda negatiften pozitife geçti. Momentum yeni döndü. "
     "Tek başına orta güç; RSI aşırı alımda değilse ve destek yakınındaysa daha sağlam."),

    ("DESTEK+MACD",    "#2dd4bf", "Destek + momentum onayı",
     "Fiyat pivot-point destekten sekiyor ve MACD aynı anda kesişiyor. "
     "Destek bölgesinde alım baskısı + histogram dönüşü çift teyit sağlıyor. "
     "Stop: destek seviyesinin %1 altı."),

    ("DIV+MACD",       "#a855f7", "Güçlü dönüş sinyali",
     "Fiyat daha düşük dip yaparken RSI daha yüksek dip yapıyor (bullish diverjans) "
     "ve MACD da aynı anda kesişiyor. Genellikle trend dönümünün en erken habercisi. "
     "RSI < 45 iken daha güçlü."),

    ("EMA SIRALANMA",  "#86efac", "Boğa trendi dizilimi",
     "EMA5 > EMA8 > EMA13 > EMA21 tam sıralaması yeni oluştu. "
     "Fiyat EMA21'den %8'den fazla uzaklaşmamış. 'Yeni' bayraklı sinyaller daha erken yakalanmış. "
     "Bu sıralama bozulmadıkça trend canlı kalır."),

    ("RSI DİVERJANS",  "#c084fc", "Gizli dönüş işareti",
     "Fiyat yeni dip yaparken RSI yapmıyor — satış baskısı zayıflıyor. "
     "MACD teyidi olmadan tek başına sinyaldir; 'DIV+MACD' daha güvenilirdir. "
     "RSI 30-45 aralığında iken en anlamlı."),

    ("EMA PULLBACK",   "#67e8f9", "Yükselen trendde geri çekilme",
     "EMA21 yükseliyor, fiyat son 5 barda EMA21'e ±%3 mesafeye gelip geri döndü. "
     "Trende geri katılım noktası. Fiyat EMA21'den %8 fazla primli değil. "
     "Klasik 'dip almak' stratejisinin objektif versiyonu."),

    ("MACD YAKLAŞIM",  "#818cf8", "Erken pozisyon fırsatı",
     "MACD histogramı hâlâ negatif ama 2 ardışık barda hızla yükseliyor; "
     "doğrusal ekstrapolasyonla ~1-2 bar içinde kesişecek. "
     "Erken girişe izin verir; kesişim olmadan stop daha geniş tutulmalı."),

    ("BOL. SIKIŞMA",   "#eab308", "Patlama öncesi bant daralması",
     "Bollinger Bantları son 60 günün en dar noktasında. Düşük volatilite her zaman "
     "yüksek volatiliteyle sonuçlanır. MACD > 0 ise yukarı patlama olasılığı daha yüksek. "
     "Yön teyidi olmadan pozisyon büyütme."),

    ("YÜKSELİŞ FORMASYONU", "#fb923c", "Mum formasyonu dönüş sinyali",
     "Onaylanmış bullish mum formasyonu tespit edildi. "
     "Olası alt formasyonlar: Çekiç, Dragonfly Doji, Doji, Ters Çekiç (tek mum); "
     "Yutan Mum, Piercing, Harami (iki mum); Sabah Yıldızı, 3 Beyaz Asker (üç mum). "
     "Tüm formasyonlar: düşüş trendi bağlamı + ATR filtresi + onay mumu (3-bar hariç) ile doğrulanır. "
     "Destek bölgesinde oluşursa 'güçlü' ve daha güvenilir."),

    ("DESTEK AL",      "#34d399", "Destekte tutunma",
     "Fiyat pivot-point desteğinin %8 yakınında, son günlerde desteğin altına "
     "inmemiş ve son 20 barda destek test edilmiş. Tek başına orta güç; "
     "MACD veya hacim teyidi ile güçlenir."),

    ("MACD ÖLÜ",       "#ff453a", "Ölüm kesişimi — zayıflama",
     "MACD histogramı son 1-2 mumda pozitiften negatife geçti. "
     "Momentum sona erdi. Açık pozisyon varsa trailing stop sıkıştırılmalı."),

    ("DESTEK KIRILDI", "#ef4444", "Destek kırılımı — dikkat",
     "Fiyat en yakın destek seviyesinin %1 altına geçti. "
     "Mevcut desteğin artık direnç olması ihtimali yüksek. "
     "Pozisyon varsa çıkış değerlendirilmeli."),
]

class StratejilerDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Strateji Rehberi")
        self.resize(720, 640)
        self.setStyleSheet(f"background:{C_BG}; color:{C_TEXT};")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)

        lbl = QLabel("📖  Sinyal Stratejileri")
        lbl.setStyleSheet(f"font-size:16px; font-weight:700; color:{C_TEXT};")
        layout.addWidget(lbl)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet(f"QScrollArea{{border:none;background:{C_BG};}}"
                             f"QScrollBar:vertical{{background:{C_CARD};width:6px;border-radius:3px;}}"
                             f"QScrollBar::handle:vertical{{background:{C_BORDER};border-radius:3px;}}")
        inner = QWidget(); inner.setStyleSheet(f"background:{C_BG};")
        inner_layout = QVBoxLayout(inner)
        inner_layout.setSpacing(8)
        inner_layout.setContentsMargins(0, 0, 8, 0)

        for sinyal, renk, baslik, aciklama in _STRATEJILER:
            card = QFrame()
            card.setStyleSheet(
                f"QFrame{{background:{C_CARD};border:none;border-left:3px solid {renk};"
                f"border-radius:8px;padding:2px;}}")
            cl = QVBoxLayout(card); cl.setContentsMargins(12, 8, 12, 8); cl.setSpacing(3)

            badge_row = QHBoxLayout(); badge_row.setSpacing(8)
            badge = QLabel(sinyal)
            badge.setStyleSheet(
                f"background:{renk};color:#000;border-radius:5px;"
                f"padding:2px 8px;font-size:11px;font-weight:700;")
            baslik_lbl = QLabel(baslik)
            baslik_lbl.setStyleSheet(f"font-size:12px;font-weight:600;color:{C_TEXT2};")
            badge_row.addWidget(badge)
            badge_row.addWidget(baslik_lbl)
            badge_row.addStretch()
            cl.addLayout(badge_row)

            acikl_lbl = QLabel(aciklama)
            acikl_lbl.setWordWrap(True)
            acikl_lbl.setStyleSheet(f"font-size:12px;color:{C_MUTED};line-height:1.4;")
            cl.addWidget(acikl_lbl)
            inner_layout.addWidget(card)

        inner_layout.addStretch()
        scroll.setWidget(inner)
        layout.addWidget(scroll)

        kapat = QPushButton("Kapat")
        kapat.setFixedHeight(36)
        kapat.setStyleSheet(
            f"QPushButton{{background:{C_CARD2};color:{C_TEXT};border:none;"
            f"border-radius:8px;font-size:13px;}}"
            f"QPushButton:hover{{background:{C_BORDER};}}")
        kapat.clicked.connect(self.accept)
        layout.addWidget(kapat)


# ═══════════════════════════════════════════════════════════
# Telegram Ayar Diyaloğu
# ═══════════════════════════════════════════════════════════
class TelegramAyarDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Telegram Bildirimleri")
        self.resize(480, 400)
        self.setStyleSheet(f"background:{C_BG}; color:{C_TEXT};")

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(10)

        lbl = QLabel("🤖  Telegram Bot Ayarları")
        lbl.setStyleSheet(f"color:{C_TEXT}; font-size:15px; font-weight:700;")
        root.addWidget(lbl)

        acik = QLabel(
            "1. Telegram'da @BotFather'a /newbot yaz → Token'ı kopyala\n"
            "2. Oluşturduğun bota /start mesajını gönder\n"
            "3. Token'ı girdikten sonra 'Chat ID Bul' butonuna bas")
        acik.setStyleSheet(
            f"color:{C_MUTED}; font-size:11px; background:{C_CARD}; "
            f"border-radius:8px; padding:8px;")
        acik.setWordWrap(True)
        root.addWidget(acik)

        form = QGridLayout()
        form.setSpacing(8)
        form.setColumnMinimumWidth(0, 90)

        def _lbl(t):
            l = QLabel(t)
            l.setStyleSheet(f"color:{C_MUTED}; font-size:12px;")
            return l

        self.txt_token = QLineEdit(TELEGRAM.token)
        self.txt_token.setPlaceholderText("1234567890:ABCdefGHIjklMNOpqrSTU…")
        self.txt_token.setFixedHeight(34)

        # Chat ID satırı: input + "Otomatik Bul" butonu yan yana
        self.txt_chat = QLineEdit(TELEGRAM.chat_id)
        self.txt_chat.setPlaceholderText("123456789")
        self.txt_chat.setFixedHeight(34)
        btn_bul = QPushButton("Chat ID Bul")
        btn_bul.setFixedHeight(34)
        btn_bul.setStyleSheet(
            f"QPushButton{{background:{C_CARD2};color:{C_TEXT};border:none;"
            f"border-radius:8px;font-size:11px;padding:0 10px;}}"
            f"QPushButton:hover{{background:#48484a;}}")
        btn_bul.clicked.connect(self._chat_id_bul)

        chat_row = QHBoxLayout()
        chat_row.setSpacing(6)
        chat_row.addWidget(self.txt_chat)
        chat_row.addWidget(btn_bul)

        form.addWidget(_lbl("Bot Token:"), 0, 0)
        form.addWidget(self.txt_token,     0, 1)
        form.addWidget(_lbl("Chat ID:"),   1, 0)
        form.addLayout(chat_row,           1, 1)
        root.addLayout(form)

        self.chk_aktif = QCheckBox("Bildirimleri etkinleştir")
        self.chk_aktif.setChecked(TELEGRAM.aktif)
        self.chk_aktif.setStyleSheet(f"color:{C_TEXT}; font-size:13px;")
        root.addWidget(self.chk_aktif)

        sinyal_lay = QHBoxLayout()
        self.chk_sinyal = QCheckBox("Güçlü sinyal gelince bildir  —  min. skor:")
        self.chk_sinyal.setChecked(TELEGRAM.guclu_sinyal)
        self.chk_sinyal.setStyleSheet(f"color:{C_TEXT}; font-size:13px;")
        self.cmb_skor = QComboBox()
        for i in range(5, 11):
            self.cmb_skor.addItem(str(i))
        self.cmb_skor.setCurrentText(str(TELEGRAM.min_guc))
        self.cmb_skor.setFixedWidth(60)
        self.cmb_skor.setFixedHeight(28)
        sinyal_lay.addWidget(self.chk_sinyal)
        sinyal_lay.addWidget(self.cmb_skor)
        sinyal_lay.addStretch()
        root.addLayout(sinyal_lay)

        tekrar_lay = QHBoxLayout()
        lbl_tekrar = QLabel("Aynı sinyal tekrar gönderilmesin:")
        lbl_tekrar.setStyleSheet(f"color:{C_MUTED}; font-size:12px;")
        self.cmb_tekrar = QComboBox()
        self.cmb_tekrar.addItems(["1 saat", "2 saat", "4 saat", "8 saat", "24 saat"])
        _tekrar_map = {1: "1 saat", 2: "2 saat", 4: "4 saat", 8: "8 saat", 24: "24 saat"}
        self.cmb_tekrar.setCurrentText(_tekrar_map.get(TELEGRAM.tekrar_saat, "4 saat"))
        self.cmb_tekrar.setFixedWidth(90)
        self.cmb_tekrar.setFixedHeight(28)
        tekrar_lay.addWidget(lbl_tekrar)
        tekrar_lay.addWidget(self.cmb_tekrar)
        tekrar_lay.addStretch()
        root.addLayout(tekrar_lay)

        lnk = QLabel('<a href="#" style="color:#0a84ff;font-size:11px;">'
                     'ℹ️  Skor nasıl hesaplanır? →</a>')
        lnk.setStyleSheet("background:transparent; border:none;")
        lnk.setCursor(Qt.CursorShape.PointingHandCursor)
        lnk.linkActivated.connect(lambda _: SkorAciklamaDialog(self).exec())
        root.addWidget(lnk)

        root.addStretch()

        alt = QHBoxLayout()
        self.btn_test = QPushButton("Test Gönder")
        self.btn_test.setFixedHeight(34)
        self.btn_test.setStyleSheet(
            f"QPushButton{{background:{C_CARD2};color:{C_TEXT};border:none;"
            f"border-radius:8px;font-size:12px;padding:0 14px;}}"
            f"QPushButton:hover{{background:#48484a;}}")
        self.btn_test.clicked.connect(self._test)

        btn_k = QPushButton("Kaydet")
        btn_k.setFixedSize(80, 34)
        btn_k.setStyleSheet(
            f"QPushButton{{background:{C_BLUE};color:#fff;border:none;"
            f"border-radius:8px;font-size:12px;font-weight:600;padding:0;}}"
            f"QPushButton:hover{{background:#1a8fff;}}")
        btn_k.clicked.connect(self._kaydet)

        btn_c = QPushButton("Kapat")
        btn_c.setFixedSize(70, 34)
        btn_c.setStyleSheet(
            f"QPushButton{{background:{C_CARD2};color:{C_MUTED};border:none;"
            f"border-radius:8px;font-size:12px;padding:0;}}"
            f"QPushButton:hover{{background:#48484a;color:{C_TEXT};}}")
        btn_c.clicked.connect(self.close)

        alt.addWidget(self.btn_test)
        alt.addStretch()
        alt.addWidget(btn_k)
        alt.addSpacing(6)
        alt.addWidget(btn_c)
        root.addLayout(alt)

    def _kaydet(self):
        _saat_map = {"1 saat": 1, "2 saat": 2, "4 saat": 4, "8 saat": 8, "24 saat": 24}
        TELEGRAM.set(
            token=self.txt_token.text().strip(),
            chat_id=self.txt_chat.text().strip(),
            aktif=self.chk_aktif.isChecked(),
            guclu_sinyal=self.chk_sinyal.isChecked(),
            min_guc=int(self.cmb_skor.currentText()),
            tekrar_saat=_saat_map.get(self.cmb_tekrar.currentText(), 4),
        )
        durum = "etkin" if self.chk_aktif.isChecked() else "devre dışı"
        QMessageBox.information(self, "Kaydedildi",
            f"Telegram ayarları kaydedildi.\nBildirimler: {durum}")

    def _chat_id_bul(self):
        """Token ile getUpdates çağırır, son mesajı gönderen kullanıcının chat_id'sini doldurur."""
        token = self.txt_token.text().strip()
        if not token:
            QMessageBox.warning(self, "Eksik", "Önce Bot Token'ı gir.")
            return
        try:
            import requests as _req
            r = _req.get(
                f"https://api.telegram.org/bot{token}/getUpdates",
                timeout=8)
            data = r.json()
            if not data.get('ok'):
                hata = data.get('description', 'Bilinmeyen hata')
                QMessageBox.warning(self, "Telegram Hatası",
                    f"API yanıtı:\n{hata}\n\n"
                    "Token'ı kontrol et. @BotFather'dan kopyaladığın tam token olmalı.")
                return
            updates = data.get('result', [])
            if not updates:
                QMessageBox.warning(self, "Mesaj Bulunamadı",
                    "Bot henüz hiç mesaj almamış.\n\n"
                    "Telegram'da botunu aç ve /start yaz,\nsonra tekrar dene.")
                return
            # En son mesajdaki chat_id'yi al
            son = updates[-1]
            chat = (son.get('message') or son.get('channel_post') or {}).get('chat', {})
            cid  = str(chat.get('id', ''))
            ad   = chat.get('first_name') or chat.get('title') or ''
            if cid:
                self.txt_chat.setText(cid)
                QMessageBox.information(self, "Chat ID Bulundu",
                    f"Chat ID: {cid}  ({ad})\nAlana otomatik girildi.")
            else:
                QMessageBox.warning(self, "Bulunamadı",
                    "Güncelleme var ama chat_id çıkarılamadı.\nManuel gir.")
        except Exception as e:
            QMessageBox.warning(self, "Bağlantı Hatası", f"İnternet bağlantısını kontrol et.\n\n{e}")

    def _test(self):
        """Token+Chat ID ile doğrudan API çağrısı yapar, hata varsa tam mesajı gösterir."""
        self._kaydet()
        token   = self.txt_token.text().strip()
        chat_id = self.txt_chat.text().strip()

        if not token:
            QMessageBox.warning(self, "Eksik", "Bot Token boş.")
            return
        if not chat_id:
            QMessageBox.warning(self, "Eksik", "Chat ID boş.\n'Chat ID Bul' butonunu kullan.")
            return

        try:
            import requests as _req
            r = _req.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json={'chat_id': chat_id,
                      'text': "🧪 <b>BIST Sinyal Tarayıcısı</b>\nBağlantı testi başarılı ✓",
                      'parse_mode': 'HTML'},
                timeout=8)
            data = r.json()
            if data.get('ok'):
                QMessageBox.information(self, "Başarılı", "Mesaj gönderildi ✓\nTelegram bağlantısı çalışıyor.")
            else:
                kod   = data.get('error_code', '')
                acikl = data.get('description', '')
                ipucu = ""
                if kod == 401:
                    ipucu = "\n\nToken yanlış. @BotFather'dan kopyaladığın tam token olmalı."
                elif "chat not found" in acikl.lower():
                    ipucu = "\n\nChat ID yanlış veya bota hiç mesaj gönderilmemiş.\n'Chat ID Bul' butonunu kullan."
                elif "blocked" in acikl.lower():
                    ipucu = "\n\nKullanıcı botu engellemiş."
                QMessageBox.warning(self, f"Telegram Hatası ({kod})",
                    f"{acikl}{ipucu}")
        except Exception as e:
            QMessageBox.warning(self, "Bağlantı Hatası",
                f"Sunucuya ulaşılamadı.\nİnternet bağlantısını kontrol et.\n\n{e}")


# ═══════════════════════════════════════════════════════════
# Portföy Diyaloğu
# ═══════════════════════════════════════════════════════════
_TBL_QSS = f"""
QTableWidget {{
    background:{C_CARD}; color:{C_TEXT}; border:none; border-radius:10px;
    gridline-color:{C_BORDER}; font-size:12px;
}}
QHeaderView::section {{
    background:{C_CARD2}; color:{C_MUTED}; border:none;
    padding:5px 8px; font-size:11px; font-weight:600;
}}
QTableWidget::item {{ padding:4px 8px; border:none; }}
QTableWidget::item:selected {{ background:#0a84ff22; }}
"""

class PortfoyDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Portföy Takibi")
        self.resize(740, 520)
        self.setStyleSheet(f"background:{C_BG}; color:{C_TEXT};")
        self._gun_thread  = None
        self._gun_fiyatlar = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(10)

        hdr = QHBoxLayout()
        lbl = QLabel("📊  Portföy Takibi")
        lbl.setStyleSheet(f"color:{C_TEXT}; font-size:15px; font-weight:700;")
        hdr.addWidget(lbl)
        hdr.addStretch()

        self.lbl_ozet = QLabel("")
        self.lbl_ozet.setStyleSheet(f"color:{C_MUTED}; font-size:11px;")
        hdr.addWidget(self.lbl_ozet)
        hdr.addSpacing(8)

        self.btn_gun = QPushButton("↻  Fiyat Güncelle")
        self.btn_gun.setFixedHeight(30)
        self.btn_gun.setStyleSheet(
            f"QPushButton{{background:{C_CARD2};color:{C_MUTED};border:none;"
            f"border-radius:8px;font-size:11px;padding:0 12px;}}"
            f"QPushButton:hover{{background:#48484a;color:{C_TEXT};}}")
        self.btn_gun.clicked.connect(self._fiyat_guncelle)
        hdr.addWidget(self.btn_gun)

        btn_yeni = QPushButton("＋  Yeni Pozisyon")
        btn_yeni.setFixedHeight(30)
        btn_yeni.setStyleSheet(
            f"QPushButton{{background:{C_BLUE};color:#fff;border:none;"
            f"border-radius:8px;font-size:11px;font-weight:600;padding:0 12px;}}"
            f"QPushButton:hover{{background:#1a8fff;}}")
        btn_yeni.clicked.connect(self._yeni_pozisyon)
        hdr.addWidget(btn_yeni)
        root.addLayout(hdr)

        # Tabs
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet(f"""
            QTabWidget::pane {{ border:none; background:{C_BG}; }}
            QTabBar::tab {{ background:{C_CARD2}; color:{C_MUTED}; border:none;
                border-radius:6px; padding:6px 16px; margin-right:4px; font-size:12px; }}
            QTabBar::tab:selected {{ background:{C_CARD}; color:{C_TEXT}; font-weight:600; }}
        """)

        # Tab 1 — Açık pozisyonlar
        t1 = QWidget()
        t1l = QVBoxLayout(t1)
        t1l.setContentsMargins(0, 8, 0, 0)
        self.tbl_aktif = QTableWidget()
        self.tbl_aktif.setColumnCount(9)
        self.tbl_aktif.setHorizontalHeaderLabels(
            ["Hisse", "Giriş ₺", "Güncel ₺", "K/Z %", "Lot", "Stop %", "Hedef %", "Tarih", ""])
        self.tbl_aktif.setStyleSheet(_TBL_QSS)
        h1 = self.tbl_aktif.horizontalHeader()
        for c in range(8):
            h1.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents
                                    if c != 7 else QHeaderView.ResizeMode.Stretch)
        h1.setSectionResizeMode(8, QHeaderView.ResizeMode.Fixed)
        self.tbl_aktif.setColumnWidth(8, 80)
        self.tbl_aktif.verticalHeader().setVisible(False)
        self.tbl_aktif.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tbl_aktif.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        t1l.addWidget(self.tbl_aktif)

        # Tab 2 — Geçmiş
        t2 = QWidget()
        t2l = QVBoxLayout(t2)
        t2l.setContentsMargins(0, 8, 0, 0)
        self.tbl_gecmis = QTableWidget()
        self.tbl_gecmis.setColumnCount(6)
        self.tbl_gecmis.setHorizontalHeaderLabels(
            ["Hisse", "Giriş ₺", "Çıkış ₺", "K/Z %", "Lot", "Tarih"])
        self.tbl_gecmis.setStyleSheet(_TBL_QSS)
        h2 = self.tbl_gecmis.horizontalHeader()
        for c in range(6):
            h2.setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents
                                    if c < 5 else QHeaderView.ResizeMode.Stretch)
        self.tbl_gecmis.verticalHeader().setVisible(False)
        self.tbl_gecmis.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        t2l.addWidget(self.tbl_gecmis)

        self.tabs.addTab(t1, "Açık Pozisyonlar")
        self.tabs.addTab(t2, "Geçmiş")
        root.addWidget(self.tabs)

        alt = QHBoxLayout()
        btn_c = QPushButton("Kapat")
        btn_c.setFixedSize(80, 32)
        btn_c.setStyleSheet(
            f"QPushButton{{background:{C_CARD2};color:{C_MUTED};border:none;"
            f"border-radius:8px;font-size:12px;padding:0;}}"
            f"QPushButton:hover{{background:#48484a;color:{C_TEXT};}}")
        btn_c.clicked.connect(self.close)
        alt.addStretch()
        alt.addWidget(btn_c)
        root.addLayout(alt)

        self._listele()

    def _listele(self):
        aktif = PORTFOY.aktif_listesi()
        self.tbl_aktif.setRowCount(len(aktif))
        for row, (hisse, p) in enumerate(aktif.items()):
            giris  = p['giris']
            guncel = self._gun_fiyatlar.get(hisse, giris)
            kz     = (guncel - giris) / giris * 100
            kz_r   = C_GREEN if kz >= 0 else C_RED
            stop_pct  = p.get('stop_pct', 0.0)
            hedef_pct = p.get('hedef_pct', 0.0)
            vals   = [
                (hisse,                        C_TEXT,  True),
                (f"₺{giris:,.2f}",             C_MUTED, False),
                (f"₺{guncel:,.2f}",            C_TEXT,  False),
                (f"{'+' if kz>=0 else ''}{kz:.2f}%", kz_r, True),
                (str(p['lot']),                C_MUTED, False),
                (f"%{stop_pct:.1f}" if stop_pct else "—",  C_RED,   False),
                (f"%{hedef_pct:.1f}" if hedef_pct else "—", C_GREEN, False),
                (p['tarih'],                   C_MUTED, False),
            ]
            for col, (txt, renk, bold) in enumerate(vals):
                it = QTableWidgetItem(txt)
                it.setForeground(QColor(renk))
                if bold:
                    it.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
                self.tbl_aktif.setItem(row, col, it)
            self.tbl_aktif.setRowHeight(row, 36)

            # Stop/Hedef ayar butonu
            btn_sh = QPushButton("Stop/Hedef")
            btn_sh.setStyleSheet(
                f"QPushButton{{background:{C_CARD2};color:{C_MUTED};border:none;"
                f"border-radius:6px;font-size:10px;margin:4px;}}"
                f"QPushButton:hover{{background:#2a3a5c;color:{C_TEXT};}}")
            btn_sh.clicked.connect(lambda _, h=hisse: self._stop_hedef_ayarla(h))
            # Kapatma butonu widget olarak koy (eski 6 → yeni 8)
            btn_kapat = QPushButton("Kapat")
            btn_kapat.setStyleSheet(
                f"QPushButton{{background:{C_RED_DIM};color:{C_RED};border:none;"
                f"border-radius:6px;font-size:11px;font-weight:600;margin:4px;}}"
                f"QPushButton:hover{{background:{C_RED};color:#fff;}}")
            btn_kapat.clicked.connect(lambda _, h=hisse: self._kapat_dialog(h))
            # Birden fazla widget için container
            cont = QWidget()
            cont_lay = QHBoxLayout(cont)
            cont_lay.setContentsMargins(2, 2, 2, 2)
            cont_lay.setSpacing(2)
            cont_lay.addWidget(btn_sh)
            cont_lay.addWidget(btn_kapat)
            self.tbl_aktif.setCellWidget(row, 8, cont)

        self.lbl_ozet.setText(f"{len(aktif)} açık pozisyon")

        gecmis = PORTFOY.gecmis_listesi()
        self.tbl_gecmis.setRowCount(len(gecmis))
        for row, k in enumerate(gecmis):
            kz_r = C_GREEN if k['kar_yuzde'] >= 0 else C_RED
            kz   = k['kar_yuzde']
            vals = [
                (k['hisse'],                         C_TEXT,  True),
                (f"₺{k['giris']:,.2f}",              C_MUTED, False),
                (f"₺{k['cikis']:,.2f}",              C_MUTED, False),
                (f"{'+' if kz>=0 else ''}{kz:.2f}%", kz_r,   True),
                (str(k['lot']),                      C_MUTED, False),
                (k['tarih_cikis'],                   C_MUTED, False),
            ]
            for col, (txt, renk, bold) in enumerate(vals):
                it = QTableWidgetItem(txt)
                it.setForeground(QColor(renk))
                if bold:
                    it.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
                self.tbl_gecmis.setItem(row, col, it)
            self.tbl_gecmis.setRowHeight(row, 30)

    def _stop_hedef_ayarla(self, hisse: str):
        p = PORTFOY.pozisyon(hisse)
        if not p:
            return
        mevcut_stop  = p.get('stop_pct', 5.0)
        mevcut_hedef = p.get('hedef_pct', 10.0)
        stop_pct, ok = QInputDialog.getDouble(
            self, f"{hisse} — Stop Seviyesi",
            "Stop yüzdesi (giriş fiyatından aşağı %):",
            value=mevcut_stop, min=0.1, max=50.0, decimals=1)
        if not ok:
            return
        hedef_pct, ok = QInputDialog.getDouble(
            self, f"{hisse} — Hedef Seviyesi",
            "Hedef yüzdesi (giriş fiyatından yukarı %):",
            value=mevcut_hedef, min=0.1, max=200.0, decimals=1)
        if ok:
            PORTFOY.stop_hedef_ayarla(hisse, stop_pct, hedef_pct)
            self._listele()

    def _kapat_dialog(self, hisse):
        p      = PORTFOY.pozisyon(hisse)
        guncel = self._gun_fiyatlar.get(hisse, p['giris'] if p else 0)
        cikis, ok = QInputDialog.getDouble(
            self, f"{hisse} — Pozisyon Kapat", "Çıkış fiyatı (₺):",
            value=round(guncel, 2), min=0.01, max=999999.99, decimals=2)
        if ok:
            PORTFOY.pozisyon_kapat(hisse, cikis)
            self._listele()

    def _yeni_pozisyon(self):
        hisse, ok = QInputDialog.getText(self, "Yeni Pozisyon", "Hisse kodu:")
        if not ok or not hisse.strip():
            return
        hisse = hisse.strip().upper()
        giris, ok = QInputDialog.getDouble(
            self, "Giriş Fiyatı", f"{hisse} — giriş fiyatı (₺):",
            value=0.0, min=0.01, max=999999.99, decimals=2)
        if not ok:
            return
        lot, ok = QInputDialog.getInt(
            self, "Lot Sayısı", f"{hisse} — lot / adet:", value=1, min=1, max=1_000_000)
        if ok:
            PORTFOY.pozisyon_ac(hisse, giris, lot)
            self._listele()

    def _fiyat_guncelle(self):
        self.btn_gun.setText("↻  Güncelleniyor…")
        self.btn_gun.setEnabled(False)
        self._gun_thread = PortfoyGuncellemeThread()
        self._gun_thread.bitti.connect(self._guncelleme_bitti)
        self._gun_thread.start()

    def _guncelleme_bitti(self, fiyatlar):
        self._gun_fiyatlar = fiyatlar
        self.btn_gun.setText("↻  Fiyat Güncelle")
        self.btn_gun.setEnabled(True)
        self._listele()


# ═══════════════════════════════════════════════════════════
# Backtest Diyaloğu
# ═══════════════════════════════════════════════════════════
class BacktestDialog(QDialog):
    def __init__(self, parent=None, hisse=''):
        super().__init__(parent)
        self.setWindowTitle("Backtest")
        self.resize(820, 580)
        self.setStyleSheet(f"background:{C_BG}; color:{C_TEXT};")
        self._bt_thread = None

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(10)

        self.lbl_baslik = QLabel("🧪  Strateji Backtest  —  Günlük  ·  Hedef: %5 kâr / 10 bar")
        self.lbl_baslik.setObjectName("btBaslik")
        self.lbl_baslik.setStyleSheet(f"color:{C_TEXT}; font-size:14px; font-weight:700;")
        root.addWidget(self.lbl_baslik)

        # Giriş satırı
        gir = QHBoxLayout()
        lbl_h = QLabel("Hisse:")
        lbl_h.setStyleSheet(f"color:{C_MUTED}; font-size:12px;")
        self.txt_h = QLineEdit(hisse)
        self.txt_h.setPlaceholderText("THYAO")
        self.txt_h.setFixedSize(120, 36)

        # Periyot seçici
        self._bt_periyot = '1d'
        self._bt_per_ad  = 'Günlük'
        self._bt_per_btns = {}
        seg = QWidget()
        seg.setFixedHeight(36)
        seg.setStyleSheet(f"background:{C_CARD2}; border-radius:10px;")
        seg_l = QHBoxLayout(seg)
        seg_l.setContentsMargins(3, 3, 3, 3)
        seg_l.setSpacing(2)
        _PER_BT_CFG = [('1S', '1h', '730g  ·  Hedef: %5 / 20 bar'),
                       ('4S', '4h', '730g  ·  Hedef: %5 / 10 bar'),
                       ('Gün', '1d', '2 Yıl  ·  Hedef: %5 / 10 bar')]
        for etiket, kod, _ in _PER_BT_CFG:
            btn = QPushButton(etiket)
            btn.setCheckable(True)
            btn.setChecked(kod == '1d')
            btn.setFixedSize(42, 30)
            btn.setStyleSheet(_seg_btn_stili(kod == '1d'))
            btn.clicked.connect(lambda _, k=kod: self._bt_per_sec(k))
            self._bt_per_btns[kod] = btn
            seg_l.addWidget(btn)
        self._bt_per_captions = {k: c for _, k, c in _PER_BT_CFG}

        from PyQt6.QtWidgets import QDoubleSpinBox
        lbl_hedef = QLabel("Hedef %:")
        lbl_hedef.setStyleSheet(f"color:{C_MUTED}; font-size:12px;")
        self.spn_hedef = QDoubleSpinBox()
        self.spn_hedef.setRange(1.0, 30.0)
        self.spn_hedef.setSingleStep(0.5)
        self.spn_hedef.setValue(5.0)
        self.spn_hedef.setSuffix(" %")
        self.spn_hedef.setFixedSize(80, 36)
        self.spn_hedef.setStyleSheet(
            f"QDoubleSpinBox{{background:{C_CARD2};color:{C_TEXT};border:none;"
            f"border-radius:8px;padding:4px 6px;font-size:12px;}}")
        self.spn_hedef.valueChanged.connect(lambda _: self._baslik_guncelle())

        self.btn_bas = QPushButton("▶  Başlat")
        self.btn_bas.setFixedSize(100, 36)
        self.btn_bas.setStyleSheet(
            f"QPushButton{{background:{C_GREEN};color:#fff;border:none;"
            f"border-radius:10px;font-size:13px;font-weight:600;padding:0;}}"
            f"QPushButton:hover{{background:#34e35e;}}")
        self.btn_bas.clicked.connect(self._baslat)
        self.prog = QProgressBar()
        self.prog.setValue(0)
        self.prog.setFixedHeight(4)
        self.prog.setTextVisible(False)
        gir.addWidget(lbl_h)
        gir.addWidget(self.txt_h)
        gir.addSpacing(8)
        gir.addWidget(seg)
        gir.addSpacing(8)
        gir.addWidget(lbl_hedef)
        gir.addWidget(self.spn_hedef)
        gir.addSpacing(8)
        gir.addWidget(self.btn_bas)
        gir.addSpacing(10)
        gir.addWidget(self.prog, stretch=1)
        root.addLayout(gir)

        # Özet strip
        ozet_f = QFrame()
        ozet_f.setFixedHeight(62)
        ozet_f.setStyleSheet(f"background:{C_CARD}; border-radius:10px;")
        ozet_l = QHBoxLayout(ozet_f)
        ozet_l.setContentsMargins(16, 8, 16, 8)
        self._ozlbl = {}
        for key, cap in [('toplam','Toplam Sinyal'), ('oran','Başarı Oranı'),
                         ('ort_kar','Ort. Max K/Z'), ('en_iyi','En İyi'), ('en_kotu','En Kötü')]:
            frm = QFrame()
            fl  = QVBoxLayout(frm)
            fl.setContentsMargins(0,0,0,0)
            fl.setSpacing(2)
            lk  = QLabel(cap)
            lk.setStyleSheet(f"color:{C_MUTED}; font-size:10px; font-weight:500;")
            lv  = QLabel("—")
            lv.setStyleSheet(f"color:{C_TEXT}; font-size:14px; font-weight:700;")
            fl.addWidget(lk)
            fl.addWidget(lv)
            self._ozlbl[key] = lv
            ozet_l.addWidget(frm)
            if key != 'en_kotu':
                sep = QFrame()
                sep.setFrameShape(QFrame.Shape.VLine)
                sep.setStyleSheet(f"color:{C_BORDER};")
                ozet_l.addWidget(sep)
        root.addWidget(ozet_f)

        # Tablo
        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels(
            ["Tarih", "Sinyal", "Skor", "Giriş ₺", "Maks ₺", "Max K/Z %", "✓"])
        self.table.setStyleSheet(_TBL_QSS)
        th = self.table.horizontalHeader()
        th.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        th.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        th.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(2, 44)
        th.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        th.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        th.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        th.setSectionResizeMode(6, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(6, 30)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        root.addWidget(self.table)

        alt = QHBoxLayout()
        btn_c = QPushButton("Kapat")
        btn_c.setFixedSize(80, 32)
        btn_c.setStyleSheet(
            f"QPushButton{{background:{C_CARD2};color:{C_MUTED};border:none;"
            f"border-radius:8px;font-size:12px;padding:0;}}"
            f"QPushButton:hover{{background:#48484a;color:{C_TEXT};}}")
        btn_c.clicked.connect(self.close)
        alt.addStretch()
        alt.addWidget(btn_c)
        root.addLayout(alt)

    def _bt_per_sec(self, kod: str):
        self._bt_periyot = kod
        for k, btn in self._bt_per_btns.items():
            btn.setChecked(k == kod)
            btn.setStyleSheet(_seg_btn_stili(k == kod))
        per_ad = {'1h': '1 Saatlik', '4h': '4 Saatlik', '1d': 'Günlük'}.get(kod, '')
        self._bt_per_ad = per_ad
        self._baslik_guncelle()

    def _baslik_guncelle(self):
        per_ad  = getattr(self, '_bt_per_ad', 'Günlük')
        hedef   = self.spn_hedef.value() if hasattr(self, 'spn_hedef') else 5.0
        bekleme = {'1h': 20, '4h': 10, '1d': 10}.get(self._bt_periyot, 10)
        self.lbl_baslik.setText(
            f"🧪  Strateji Backtest  —  {per_ad}  ·  Hedef: %{hedef:.1f} kâr / {bekleme} bar")

    def _baslat(self):
        hisse = self.txt_h.text().strip().upper()
        if not hisse:
            return
        if self._bt_thread and self._bt_thread.isRunning():
            self._bt_thread.dur()
            self.btn_bas.setText("▶  Başlat")
            return
        self.table.setRowCount(0)
        for v in self._ozlbl.values():
            v.setText("—")
            v.setStyleSheet(f"color:{C_TEXT}; font-size:14px; font-weight:700;")
        self.prog.setValue(0)
        self.btn_bas.setText("■  Durdur")

        self._bt_thread = BacktestThread(hisse, self._bt_periyot, self.spn_hedef.value())
        self._bt_thread.ilerleme.connect(
            lambda m, t: self.prog.setValue(int(m / t * 100) if t else 0))
        self._bt_thread.bitti.connect(self._bitti)
        self._bt_thread.start()

    def _bitti(self, kayitlar, ist):
        self.btn_bas.setText("▶  Başlat")
        self.prog.setValue(100)
        if not kayitlar:
            QMessageBox.information(self, "Backtest", "Yeterli sinyal bulunamadı.")
            return

        hisse = self.txt_h.text().strip().upper()
        if hisse:
            BACKTEST_SONUCLARI.kaydet_sonuc(hisse, self._bt_periyot, ist)

        def _renk_set(lbl, txt, renk):
            lbl.setText(txt)
            lbl.setStyleSheet(f"color:{renk}; font-size:14px; font-weight:700;")

        self._ozlbl['toplam'].setText(str(ist['toplam']))
        oran = ist['oran']
        _renk_set(self._ozlbl['oran'], f"%{oran}",
                  C_GREEN if oran >= 60 else C_ORANGE if oran >= 40 else C_RED)
        ok  = ist['ort_kar']
        _renk_set(self._ozlbl['ort_kar'], f"{'+' if ok>=0 else ''}{ok:.1f}%",
                  C_GREEN if ok >= 0 else C_RED)
        _renk_set(self._ozlbl['en_iyi'],  f"+{ist['en_iyi']:.1f}%",  C_GREEN)
        _renk_set(self._ozlbl['en_kotu'], f"{ist['en_kotu']:.1f}%",  C_RED)

        self.table.setRowCount(len(kayitlar))
        for row, k in enumerate(kayitlar):
            s_renk = SINYAL_RENK.get(k['sinyal'], C_MUTED)
            k_renk = C_GREEN if k['kar_pct'] >= 0 else C_RED
            skor   = k['skor']
            s_bg   = C_GREEN_DIM if skor >= 8 else "#2d1a00" if skor >= 5 else C_CARD2
            s_cr   = C_GREEN if skor >= 8 else C_ORANGE if skor >= 5 else C_MUTED

            cols = [
                (k['tarih'],          C_MUTED,  False),
                (k['sinyal'],         s_renk,   True),
                (str(skor),           s_cr,     True),
                (f"₺{k['giris']:,.2f}", C_TEXT, False),
                (f"₺{k['max_cikis']:,.2f}", C_TEXT, False),
                (f"{'+' if k['kar_pct']>=0 else ''}{k['kar_pct']:.1f}%", k_renk, True),
                ("✓" if k['basari'] else "✗",
                 C_GREEN if k['basari'] else C_RED, True),
            ]
            for col, (txt, renk, bold) in enumerate(cols):
                it = QTableWidgetItem(txt)
                it.setForeground(QColor(renk))
                it.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
                if bold:
                    it.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
                self.table.setItem(row, col, it)
            self.table.setRowHeight(row, 28)


# ═══════════════════════════════════════════════════════════
# Risk Ayar Diyaloğu
# ═══════════════════════════════════════════════════════════
class RiskAyarDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Risk Ayarları")
        self.resize(360, 220)
        self.setStyleSheet(f"background:{C_BG}; color:{C_TEXT};")

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(12)

        lbl = QLabel("⚖  Risk Ayarları")
        lbl.setStyleSheet(f"color:{C_TEXT}; font-size:15px; font-weight:700;")
        root.addWidget(lbl)

        acik = QLabel("Pozisyon büyüklüğü hesaplamak için sermaye ve\nmaksimum risk oranını girin.")
        acik.setStyleSheet(f"color:{C_MUTED}; font-size:11px;")
        root.addWidget(acik)

        form = QGridLayout()
        form.setSpacing(8)
        form.setColumnMinimumWidth(0, 130)

        def _lbl(t):
            l = QLabel(t); l.setStyleSheet(f"color:{C_MUTED}; font-size:12px;"); return l

        self.txt_sermaye = QLineEdit(str(int(RISK_AYAR.sermaye)))
        self.txt_sermaye.setFixedHeight(34)
        self.txt_risk = QLineEdit(str(RISK_AYAR.max_risk_pct))
        self.txt_risk.setFixedHeight(34)
        form.addWidget(_lbl("Toplam Sermaye (₺):"), 0, 0)
        form.addWidget(self.txt_sermaye, 0, 1)
        form.addWidget(_lbl("Maks. Risk (%):"), 1, 0)
        form.addWidget(self.txt_risk, 1, 1)
        root.addLayout(form)
        root.addStretch()

        alt = QHBoxLayout()
        btn_k = QPushButton("Kaydet")
        btn_k.setFixedSize(80, 34)
        btn_k.setStyleSheet(
            f"QPushButton{{background:{C_BLUE};color:#fff;border:none;"
            f"border-radius:8px;font-size:12px;font-weight:600;padding:0;}}"
            f"QPushButton:hover{{background:#1a8fff;}}")
        btn_k.clicked.connect(self._kaydet)
        btn_c = QPushButton("Kapat")
        btn_c.setFixedSize(70, 34)
        btn_c.setStyleSheet(
            f"QPushButton{{background:{C_CARD2};color:{C_MUTED};border:none;"
            f"border-radius:8px;font-size:12px;padding:0;}}"
            f"QPushButton:hover{{background:#48484a;color:{C_TEXT};}}")
        btn_c.clicked.connect(self.close)
        alt.addStretch()
        alt.addWidget(btn_k)
        alt.addSpacing(6)
        alt.addWidget(btn_c)
        root.addLayout(alt)

    def _kaydet(self):
        try:
            s = float(self.txt_sermaye.text().replace(',', '.'))
            r = float(self.txt_risk.text().replace(',', '.'))
            RISK_AYAR.set(sermaye=s, max_risk_pct=r)
            self.close()
        except ValueError:
            QMessageBox.warning(self, "Hata", "Geçerli bir sayı girin.")


# ═══════════════════════════════════════════════════════════
# Neden Bu Sinyal Diyaloğu
# ═══════════════════════════════════════════════════════════
class NedenDialog(QDialog):
    def __init__(self, sonuc: dict, parent=None):
        super().__init__(parent)
        hisse = sonuc.get('hisse', '')
        self.setWindowTitle(f"Neden Bu Sinyal?  —  {hisse}")
        self.resize(420, 590)
        self.setStyleSheet(f"background:{C_BG}; color:{C_TEXT};")

        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(8)

        skor  = sonuc.get('sinyal_gucu', 0)
        genel = sonuc.get('genel_sinyal', 'NÖTR')
        skor_renk = C_GREEN if skor >= 8 else C_ORANGE if skor >= 5 else C_RED

        hdr = QHBoxLayout()
        lbl_h = QLabel(f"🔍  {hisse}  —  {genel}")
        lbl_h.setStyleSheet(f"color:{C_TEXT}; font-size:15px; font-weight:700;")
        lbl_s = QLabel(f"Skor {skor}/10")
        lbl_s.setStyleSheet(
            f"color:{skor_renk}; font-size:13px; font-weight:700; "
            f"background:{C_CARD2}; border-radius:8px; padding:4px 10px;")
        hdr.addWidget(lbl_h)
        hdr.addStretch()
        hdr.addWidget(lbl_s)
        root.addLayout(hdr)

        for baslik, aktif, aciklama in self._kriterler(sonuc):
            frm = QFrame()
            frm.setFixedHeight(38)
            frm.setStyleSheet(
                f"background:{C_CARD if aktif else C_BG}; border-radius:8px; border:none;")
            fl = QHBoxLayout(frm)
            fl.setContentsMargins(10, 0, 10, 0)
            fl.setSpacing(8)

            lbl_ikon = QLabel("✓" if aktif else "✗")
            lbl_ikon.setFixedWidth(16)
            lbl_ikon.setStyleSheet(
                f"color:{C_GREEN if aktif else C_RED}; font-size:14px; font-weight:700;")
            lbl_ad = QLabel(baslik)
            lbl_ad.setStyleSheet(
                f"color:{C_TEXT if aktif else C_MUTED}; font-size:13px; "
                f"font-weight:{'600' if aktif else '400'};")
            lbl_ac = QLabel(aciklama)
            lbl_ac.setStyleSheet(f"color:{C_MUTED}; font-size:11px;")
            lbl_ac.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

            fl.addWidget(lbl_ikon)
            fl.addWidget(lbl_ad)
            fl.addStretch()
            fl.addWidget(lbl_ac)
            root.addWidget(frm)

        root.addStretch()
        btn_c = QPushButton("Kapat")
        btn_c.setFixedSize(80, 32)
        btn_c.setStyleSheet(
            f"QPushButton{{background:{C_CARD2};color:{C_MUTED};border:none;"
            f"border-radius:8px;font-size:12px;padding:0;}}"
            f"QPushButton:hover{{background:#48484a;color:{C_TEXT};}}")
        btn_c.clicked.connect(self.close)
        hbox = QHBoxLayout()
        hbox.addStretch()
        hbox.addWidget(btn_c)
        root.addLayout(hbox)

    @staticmethod
    def _kriterler(s):
        rsi     = s.get('rsi', 50)
        macd_k  = s.get('macd_kesisim', False)
        kac     = s.get('macd_kesisim_kac_once', 99)
        macd_y  = s.get('macd_yaklasan', False)
        hacim   = s.get('hacim')
        kutu    = s.get('kutu')
        destek  = s.get('destek_uzeri') and s.get('destek_yakin') and s.get('destek_test')
        dip     = s.get('dip_sinyal', False)
        ema     = s.get('ema_sir')
        trend   = s.get('trend_sinyal', '')
        rsi_div = s.get('rsi_div')
        pull    = s.get('ema_pull')
        bol_sq  = s.get('bol_sq')
        mum     = s.get('mum')
        return [
            ("MACD Kesişim",  macd_k,
             ("Taze kesişim" if kac == 0 else f"{kac} bar önce") if macd_k else "Kesişim yok"),
            ("MACD Yaklaşım", macd_y and not macd_k,
             "Sıfıra yaklaşıyor" if (macd_y and not macd_k) else "—"),
            ("Hacim Artışı",  hacim is not None,
             f"{hacim['hacim_orani']:.1f}× ort." if hacim else "Normal hacim"),
            ("Kutu Kırılımı", kutu is not None,
             f"%{kutu['aralik_pct']:.1f} aralık" if kutu else "Kutu yok"),
            ("Destek Bölgesi", bool(destek or dip),
             "Destekte tutunuyor" if (destek or dip) else "Destek uzağı"),
            ("EMA Sıralanma", ema is not None,
             ("Yeni sıralama" if ema and ema.get('yeni') else "Sıralı") if ema else "Sıralama yok"),
            ("RSI Aşırı Satım", rsi < 35,
             f"RSI {rsi:.0f}" if rsi < 35 else f"RSI {rsi:.0f} — nötr"),
            ("Yükselen Trend", trend == 'AL',
             "Yükselen trend" if trend == 'AL' else "Nötr / düşen trend"),
            ("RSI Diverjans",  rsi_div is not None,
             (f"RSI {rsi_div['rsi_dip2']:.0f} vs {rsi_div['rsi_dip1']:.0f}"
              if rsi_div else "Diverjans yok")),
            ("EMA21 Pullback", pull is not None,
             f"EMA21 {pull['ema21']:.2f} (+%{pull['prime_pct']:.1f})" if pull else "Pullback yok"),
            ("Bollinger Sıkışma", bol_sq is not None,
             f"%{bol_sq['sikisma_pct']:.0f} sıkışma" if bol_sq else "Sıkışma yok"),
            ("Mum Formasyonu", mum is not None,
             (f"{mum['formasyon']}" + (" + destek" if mum and mum.get('destek_yakin') else ""))
             if mum else "Formasyon yok"),
        ]


# ═══════════════════════════════════════════════════════════
# KAP Duyuru Diyaloğu
# ═══════════════════════════════════════════════════════════
class KapDuyuruDialog(QDialog):
    def __init__(self, hisse: str, duyurular: list, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"KAP Duyuruları  —  {hisse}")
        self.resize(700, 460)
        self.setStyleSheet(f"background:{C_BG}; color:{C_TEXT};")

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(10)

        lbl = QLabel(f"🏛  {hisse}  —  Son KAP Bildirimleri")
        lbl.setStyleSheet(f"color:{C_TEXT}; font-size:15px; font-weight:700;")
        root.addWidget(lbl)

        if not duyurular:
            lbl_bos = QLabel(
                "Bildirim bulunamadı veya KAP API erişilemedi.\n"
                "kap.org.tr adresinden manuel kontrol edebilirsiniz.")
            lbl_bos.setStyleSheet(f"color:{C_MUTED}; font-size:12px;")
            lbl_bos.setWordWrap(True)
            root.addWidget(lbl_bos)
        else:
            table = QTableWidget()
            table.setColumnCount(3)
            table.setHorizontalHeaderLabels(["Tarih", "Tür", "Başlık"])
            table.setStyleSheet(_TBL_QSS)
            table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
            table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
            table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
            table.verticalHeader().setVisible(False)
            table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
            table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
            table.setRowCount(len(duyurular))
            for row, d in enumerate(duyurular):
                items = [
                    QTableWidgetItem(d.get('tarih', '')),
                    QTableWidgetItem(d.get('tur', '')),
                    QTableWidgetItem(d.get('baslik', '')),
                ]
                for col, it in enumerate(items):
                    it.setForeground(QColor(C_MUTED if col < 2 else C_TEXT))
                    table.setItem(row, col, it)
                table.setRowHeight(row, 30)
            root.addWidget(table)

        root.addStretch()
        btn_c = QPushButton("Kapat")
        btn_c.setFixedWidth(80)
        btn_c.setStyleSheet(
            f"QPushButton{{background:{C_CARD2};color:{C_MUTED};border:none;"
            f"border-radius:8px;font-size:12px;padding:6px 0;}}"
            f"QPushButton:hover{{background:#48484a;color:{C_TEXT};}}")
        btn_c.clicked.connect(self.close)
        hbox = QHBoxLayout()
        hbox.addStretch()
        hbox.addWidget(btn_c)
        root.addLayout(hbox)


# ═══════════════════════════════════════════════════════════
# Not Dialogu
# ═══════════════════════════════════════════════════════════
class NotDialog(QDialog):
    def __init__(self, hisse: str, mevcut_not: str = "", parent=None):
        super().__init__(parent)
        self._hisse = hisse
        self.setWindowTitle(f"Not  —  {hisse}")
        self.resize(440, 280)
        self.setStyleSheet(f"background:{C_BG}; color:{C_TEXT};")

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(10)

        lbl = QLabel(f"📝  {hisse}  —  Hisse Notu")
        lbl.setStyleSheet(f"color:{C_TEXT}; font-size:14px; font-weight:700;")
        root.addWidget(lbl)

        self._editor = QTextEdit()
        self._editor.setPlainText(mevcut_not)
        self._editor.setStyleSheet(
            f"background:{C_CARD}; color:{C_TEXT}; border:1px solid {C_BORDER}; "
            f"border-radius:8px; padding:8px; font-size:13px;")
        root.addWidget(self._editor, stretch=1)

        btn_row = QHBoxLayout()
        btn_sil = QPushButton("🗑 Notu Sil")
        btn_sil.setStyleSheet(
            f"QPushButton{{background:{C_RED_DIM};color:{C_RED};border:none;"
            f"border-radius:8px;padding:6px 14px;font-size:12px;}}"
            f"QPushButton:hover{{background:#4d1010;}}")
        btn_sil.clicked.connect(self._sil)

        btn_kaydet = QPushButton("💾 Kaydet")
        btn_kaydet.setDefault(True)
        btn_kaydet.setStyleSheet(
            f"QPushButton{{background:{C_BLUE};color:white;border:none;"
            f"border-radius:8px;padding:6px 18px;font-size:12px;font-weight:700;}}"
            f"QPushButton:hover{{background:#0a84ff;}}")
        btn_kaydet.clicked.connect(self._kaydet)

        btn_row.addWidget(btn_sil)
        btn_row.addStretch()
        btn_row.addWidget(btn_kaydet)
        root.addLayout(btn_row)

    def _kaydet(self):
        metin = self._editor.toPlainText().strip()
        if metin:
            NOTLAR.kaydet(self._hisse, metin)
        else:
            NOTLAR.sil(self._hisse)
        self.accept()

    def _sil(self):
        NOTLAR.sil(self._hisse)
        self.accept()


# ═══════════════════════════════════════════════════════════
# Ana Pencere
# ═══════════════════════════════════════════════════════════
class AnaPencere(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("BIST Sinyal Tarayıcısı")
        self.resize(1280, 820)
        self._thread           = None
        self._fav_fetch        = None
        self._analiz_bekleyen  = 0
        self._analiz_threads   = []
        self._ema_fetch = None
        self._sonuclar  = []
        self._pin_count = 0
        self._oto_timer = QTimer()
        self._oto_timer.timeout.connect(self._oto_tara)
        self._kur_ui()

        # Sistem tepsisi (alarm bildirimleri için)
        from PyQt6.QtGui import QPixmap
        _pix = QPixmap(16, 16)
        _pix.fill(QColor(C_BLUE))
        self._tray = QSystemTrayIcon(QIcon(_pix), self)
        self._tray.setVisible(True)

        # Alarm kontrol thread'i
        self._alarm_thread = AlarmThread()
        self._alarm_thread.tetiklendi.connect(self._alarm_bildir)
        self._alarm_thread.start()

    def closeEvent(self, event):
        self._alarm_thread.dur()
        self._alarm_thread.wait(2000)
        super().closeEvent(event)

    # ──────────────────────────────────────────────────────
    def _kur_ui(self):
        merkez = QWidget()
        self.setCentralWidget(merkez)
        ana = QVBoxLayout(merkez)
        ana.setContentsMargins(0, 0, 0, 0)
        ana.setSpacing(0)

        # ── Üst Araç Çubuğu  (macOS tarzı) ─────────
        toolbar = QWidget()
        toolbar.setFixedHeight(64)
        toolbar.setStyleSheet(
            f"background-color:{C_CARD};"
            f"border-bottom: 1px solid {C_BORDER};")
        tb = QHBoxLayout(toolbar)
        tb.setContentsMargins(20, 0, 20, 0)
        tb.setSpacing(10)

        lbl_logo = QLabel(
            f'<span style="color:{C_BLUE};font-weight:700;">BIST</span>'
            f'<span style="color:{C_TEXT};font-weight:700;"> Sinyal</span>'
        )
        lbl_logo.setStyleSheet("font-size:17px; letter-spacing:-0.3px;")
        tb.addWidget(lbl_logo)
        _vsep = QWidget()
        _vsep.setFixedSize(1, 20)
        _vsep.setStyleSheet(f"background:{C_BORDER};")
        tb.addWidget(_vsep)
        tb.addSpacing(6)

        # Periyot — segmented control görünümü
        seg_bg = QWidget()
        seg_bg.setFixedHeight(32)
        seg_bg.setStyleSheet(
            f"background:{C_CARD2}; border-radius:10px;")
        seg_lay = QHBoxLayout(seg_bg)
        seg_lay.setContentsMargins(3, 3, 3, 3)
        seg_lay.setSpacing(2)

        self._periyot_butonlar = {}
        _PER_BTN = [("1S", "1h"), ("4S", "4h"), ("Gün", "1d"), ("Haf", "1w"), ("Ay", "1mo")]
        _PER_VARSAYILAN = {"4h", "1d"}
        for etiket, kod in _PER_BTN:
            btn = QPushButton(etiket)
            btn.setCheckable(True)
            btn.setChecked(kod in _PER_VARSAYILAN)
            btn.setFixedSize(42, 26)
            btn.setStyleSheet(self._periyot_btn_stili(kod in _PER_VARSAYILAN))
            btn.clicked.connect(lambda checked, k=kod: self._periyot_toggle(k))
            self._periyot_butonlar[kod] = btn
            seg_lay.addWidget(btn)
        tb.addWidget(seg_bg)

        tb.addSpacing(10)

        # Endeks seçici — BIST30 / BIST100 / Tümü
        self._endeks_sec = "TÜM"
        endeks_bg = QWidget()
        endeks_bg.setFixedHeight(32)
        endeks_bg.setStyleSheet(f"background:{C_CARD2}; border-radius:10px;")
        endeks_lay = QHBoxLayout(endeks_bg)
        endeks_lay.setContentsMargins(3, 3, 3, 3)
        endeks_lay.setSpacing(2)
        self._endeks_butonlar = {}
        for etiket, kod in [("BIST30", "30"), ("BIST100", "100"), ("Tümü", "TÜM")]:
            btn = QPushButton(etiket)
            btn.setCheckable(True)
            btn.setChecked(kod == "TÜM")
            btn.setFixedHeight(26)
            btn.setStyleSheet(_seg_btn_stili(kod == "TÜM"))
            btn.clicked.connect(lambda checked, k=kod: self._endeks_degistir(k))
            self._endeks_butonlar[kod] = btn
            endeks_lay.addWidget(btn)
        tb.addWidget(endeks_bg)

        tb.addSpacing(10)

        # Ayarlar dropdown menüsü
        _ayar_btn_qss = (
            f"QPushButton{{background:{C_CARD2};color:{C_MUTED};border:none;"
            f"border-radius:10px;font-size:13px;font-weight:500;padding:0 12px;}}"
            f"QPushButton::menu-indicator{{width:0;}}"
            f"QPushButton:hover{{background:#48484a;color:{C_TEXT};}}"
        )
        self.btn_ayarlar = QPushButton("⚙  Ayarlar")
        self.btn_ayarlar.setFixedSize(100, 32)
        self.btn_ayarlar.setStyleSheet(_ayar_btn_qss)

        self._ayar_menu = QMenu(self.btn_ayarlar)
        self._ayar_menu.setStyleSheet(_ALARM_MENU_QSS)

        act_portfoy = QAction("📊   Portföy", self)
        act_portfoy.triggered.connect(self._portfoy_ac)
        self._ayar_menu.addAction(act_portfoy)

        self._ayar_menu.addSeparator()

        act_alarmlar = QAction("🔔   Alarmlar", self)
        act_alarmlar.triggered.connect(self._alarmlar_ac)
        self._ayar_menu.addAction(act_alarmlar)

        act_telegram = QAction("🤖   Telegram", self)
        act_telegram.triggered.connect(self._telegram_ac)
        self._ayar_menu.addAction(act_telegram)

        act_stratejiler = QAction("📖   Strateji Rehberi", self)
        act_stratejiler.triggered.connect(self._stratejiler_ac)
        self._ayar_menu.addAction(act_stratejiler)

        self._ayar_menu.addSeparator()

        act_gecmis = QAction("📋   Sinyal Geçmişi", self)
        act_gecmis.triggered.connect(self._gecmis_ac)
        self._ayar_menu.addAction(act_gecmis)

        act_backtest = QAction("🧪   Backtest", self)
        act_backtest.triggered.connect(self._backtest_ac)
        self._ayar_menu.addAction(act_backtest)

        self._ayar_menu.addSeparator()

        act_risk = QAction("⚖   Risk Ayarları", self)
        act_risk.triggered.connect(self._risk_ayar_menu_ac)
        self._ayar_menu.addAction(act_risk)

        self._ayar_menu.addSeparator()

        act_csv = QAction("📥   Taramayı Dışa Aktar (CSV)", self)
        act_csv.triggered.connect(self._csv_aktar)
        self._ayar_menu.addAction(act_csv)

        act_guncelle = QAction("🔄   Güncelleme Kontrol", self)
        act_guncelle.triggered.connect(self._guncelleme_kontrol)
        self._ayar_menu.addAction(act_guncelle)

        self.btn_ayarlar.setMenu(self._ayar_menu)
        tb.addWidget(self.btn_ayarlar)

        tb.addStretch()

        # Manuel hisse girişi
        self.txt_hisse = QLineEdit()
        self.txt_hisse.setPlaceholderText("Hisse ara…  THYAO")
        self.txt_hisse.setFixedSize(160, 34)
        self.txt_hisse.returnPressed.connect(self._hisse_ara)

        self.btn_hisse_ara = QPushButton("Analiz")
        self.btn_hisse_ara.setFixedHeight(34)
        self.btn_hisse_ara.setStyleSheet(
            f"QPushButton{{background:{C_BLUE};color:#fff;border:none;"
            f"border-radius:10px;font-size:13px;font-weight:600;padding:0 16px;}}"
            f"QPushButton:hover{{background:#1a8fff;}}")
        self.btn_hisse_ara.clicked.connect(self._hisse_ara)
        tb.addWidget(self.txt_hisse)
        tb.addWidget(self.btn_hisse_ara)

        tb.addSpacing(8)

        # Otomatik tarama
        lbl_oto = QLabel("Oto:")
        lbl_oto.setStyleSheet(f"color:{C_MUTED}; font-size:12px;")
        self.cmb_oto = QComboBox()
        self.cmb_oto.addItems(["Kapalı", "15 dk", "30 dk", "1 saat"])
        self.cmb_oto.setFixedHeight(34)
        self.cmb_oto.currentIndexChanged.connect(self._oto_ayarla)
        tb.addWidget(lbl_oto)
        tb.addWidget(self.cmb_oto)

        tb.addSpacing(8)

        self.btn_tara = QPushButton("▶  Tara")
        self.btn_tara.setFixedSize(100, 36)
        self.btn_tara.clicked.connect(self._baslat)

        self.btn_dur = QPushButton("■  Durdur")
        self.btn_dur.setObjectName("stopBtn")
        self.btn_dur.setFixedSize(110, 36)
        self.btn_dur.setEnabled(False)
        self.btn_dur.clicked.connect(self._durdur)
        tb.addWidget(self.btn_tara)
        tb.addWidget(self.btn_dur)

        ana.addWidget(toolbar)

        # ── İnce ilerleme çubuğu + durum ────────────
        prog_widget = QWidget()
        prog_widget.setFixedHeight(32)
        prog_widget.setStyleSheet(f"background-color:{C_BG};")
        prog_layout = QHBoxLayout(prog_widget)
        prog_layout.setContentsMargins(20, 6, 20, 6)
        prog_layout.setSpacing(10)

        self.prog_bar = QProgressBar()
        self.prog_bar.setValue(0)
        self.prog_bar.setFixedHeight(22)
        self.prog_bar.setTextVisible(True)
        self.prog_bar.setFormat("%p%")

        self.lbl_durum = QLabel("Tarama bekleniyor…")
        self.lbl_durum.setStyleSheet(f"color:{C_MUTED}; font-size:11px;")

        self.lbl_sayac = QLabel("AL: 0   SAT: 0")
        self.lbl_sayac.setStyleSheet(f"color:{C_MUTED}; font-size:11px;")

        prog_layout.addWidget(self.prog_bar, stretch=1)
        prog_layout.addWidget(self.lbl_durum)
        prog_layout.addStretch()
        prog_layout.addWidget(self.lbl_sayac)
        ana.addWidget(prog_widget)

        # ── İçerik Alanı ────────────────────────────
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        # Sol: Sinyal Listesi
        sol_widget = QWidget()
        sol_widget.setMinimumWidth(270)
        sol_widget.setMaximumWidth(360)
        sol_widget.setStyleSheet(f"background:{C_BG};")
        sol_layout = QVBoxLayout(sol_widget)
        sol_layout.setContentsMargins(12, 14, 8, 12)
        sol_layout.setSpacing(10)

        lbl_liste = QLabel("Sinyaller")
        lbl_liste.setStyleSheet(
            f"color:{C_TEXT}; font-size:15px; font-weight:700;")
        sol_layout.addWidget(lbl_liste)

        # Filtre butonları — tek segmented container
        self._filtre_aktif = "TÜM"
        self._filtre_butonlar = {}

        filtre_bar1 = QHBoxLayout()
        filtre_bar1.setSpacing(6)
        filtre_bar2 = QHBoxLayout()
        filtre_bar2.setSpacing(6)
        filtre_bar3 = QHBoxLayout()
        filtre_bar3.setSpacing(6)

        for etiket, kod, bar in [
            ("Tümü",    "TÜM",    filtre_bar1),
            ("AL",      "AL",     filtre_bar1),
            ("SAT",     "SAT",    filtre_bar1),
            ("MACD",    "MACD",   filtre_bar2),
            ("HACİM",   "HACİM",  filtre_bar2),
            ("⚡ 6+",   "GUCLU",  filtre_bar2),
            ("★ Favori","FAV",    filtre_bar2),
            ("KUTU",    "KUTU",   filtre_bar3),
            ("DESTEK",  "DESTEK", filtre_bar3),
            ("EMA",     "EMA",    filtre_bar3),
            ("DIV",     "DIV",    filtre_bar3),
            ("MUM",     "MUM",    filtre_bar3),
        ]:
            btn = QPushButton(etiket)
            btn.setCheckable(True)
            btn.setChecked(kod == "TÜM")
            btn.setFixedHeight(28)
            btn.setStyleSheet(self._filtre_btn_stili(kod == "TÜM", kod))
            btn.clicked.connect(lambda checked, k=kod: self._filtre_sec(k))
            self._filtre_butonlar[kod] = btn
            bar.addWidget(btn)

        sol_layout.addLayout(filtre_bar1)
        sol_layout.addLayout(filtre_bar2)
        sol_layout.addLayout(filtre_bar3)

        self.liste = QListWidget()
        self.liste.setSpacing(2)
        self.liste.currentItemChanged.connect(self._secildi)
        sol_layout.addWidget(self.liste)

        splitter.addWidget(sol_widget)

        # Sağ: Detay Paneli
        self.detay = DetayPanel()
        scroll = QScrollArea()
        scroll.setWidget(self.detay)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        splitter.addWidget(scroll)

        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([310, 970])

        ana.addWidget(splitter, stretch=1)
        self.setStatusBar(QStatusBar())

        self._al_n = 0
        self._sat_n = 0

    # ──────────────────────────────────────────────────────
    def _endeks_degistir(self, kod):
        self._endeks_sec = kod
        for k, btn in self._endeks_butonlar.items():
            aktif = (k == kod)
            btn.setChecked(aktif)
            btn.setStyleSheet(_seg_btn_stili(aktif))

    def _secilen_liste(self):
        if self._endeks_sec == "30":
            return BIST_30
        if self._endeks_sec == "100":
            return BIST_HISSELER
        return BIST_TUMHISSELER

    @staticmethod
    def _periyot_btn_stili(aktif: bool) -> str:
        return _seg_btn_stili(aktif)

    def _periyot_toggle(self, kod: str):
        aktif = [k for k, b in self._periyot_butonlar.items() if b.isChecked()]
        # En az 1 seçili kalsın
        if kod in aktif and len(aktif) == 1:
            self._periyot_butonlar[kod].setChecked(True)
            return
        yeni = kod in aktif  # toggle sonrası durum
        self._periyot_butonlar[kod].setStyleSheet(self._periyot_btn_stili(yeni))

    def _secilen_periyotlar(self):
        secili = [k for k, b in self._periyot_butonlar.items() if b.isChecked()]
        return secili if secili else ["4h", "1d"]

    def _baslat(self):
        if self._thread and self._thread.isRunning():
            return
        self.liste.clear()
        self._sonuclar.clear()
        self._al_n = self._sat_n = 0
        self._pin_count = 0
        self.lbl_sayac.setText("AL: 0   SAT: 0")
        self.btn_tara.setEnabled(False)
        self.btn_dur.setEnabled(True)
        self.prog_bar.setValue(0)

        self._thread = TaramaThread(self._secilen_liste(), self._secilen_periyotlar())
        self._thread.ilerleme.connect(self._ilerleme_guncelle)
        self._thread.sinyal_buldu.connect(self._sinyal_ekle)
        self._thread.bitti.connect(self._bitti)
        self._thread.start()

    def _durdur(self):
        if self._thread:
            self._thread.dur()
        self.btn_dur.setEnabled(False)

    def _ilerleme_guncelle(self, mevcut, toplam, hisse):
        self.prog_bar.setMaximum(toplam)
        self.prog_bar.setValue(mevcut)
        pct = int(mevcut / toplam * 100) if toplam else 0
        self.lbl_durum.setText(f"{hisse}  ·  {mevcut}/{toplam}  ·  %{pct}")
        self.statusBar().showMessage(f"{hisse} taraniyor…")

    def _sinyal_ekle(self, sonuc: dict):
        genel = sonuc.get('genel_sinyal', 'NÖTR')
        if 'AL' in genel:
            self._al_n += 1
            try:
                winsound.Beep(880, 120)
            except Exception:
                pass
        elif 'SAT' in genel:
            self._sat_n += 1
        self.lbl_sayac.setText(
            f"<span style='color:{C_GREEN}'>AL: {self._al_n}</span>"
            f"   <span style='color:{C_RED}'>SAT: {self._sat_n}</span>")

        # Telegram: güçlü sinyal bildirimi
        if (TELEGRAM.aktif and TELEGRAM.guclu_sinyal and
                sonuc.get('sinyal_gucu', 0) >= TELEGRAM.min_guc and
                genel not in ('SAT', 'GÜÇLÜ SAT', 'NÖTR')):
            hisse_t   = sonuc.get('hisse', '')
            periyot_r = sonuc.get('periyot', '1d')
            if not TELEGRAM.zaten_gonderildi(hisse_t, genel, periyot_r):
                fiyat_t   = sonuc.get('fiyat', 0)
                periyot_t = PERIYOT_ADLARI.get(periyot_r, '')
                skor_t    = sonuc.get('sinyal_gucu', 0)
                mesaj_t   = (f"📊 <b>{hisse_t}</b>  ·  {genel}  ·  Skor {skor_t}/10\n"
                             f"💸 ₺{fiyat_t:,.2f}  ·  {periyot_t}")
                foto = _telegram_grafik_png(sonuc)
                if foto:
                    TELEGRAM.gonder_foto(mesaj_t, foto)
                else:
                    TELEGRAM.gonder(mesaj_t)
                TELEGRAM.gonderim_kaydet(hisse_t, genel, periyot_r)

        item, widget = _liste_satiri_olustur(sonuc, pin_cb=lambda h: self._pin_toggle(h))
        hisse = sonuc.get('hisse', '')
        if SABITLENMIS.sabitlenen(hisse):
            self.liste.insertItem(self._pin_count, item)
            self._pin_count += 1
        else:
            self.liste.addItem(item)
        self.liste.setItemWidget(item, widget)
        self._sonuclar.append(sonuc)

    def _bitti(self, al_n, sat_n):
        self.btn_tara.setEnabled(True)
        self.btn_dur.setEnabled(False)
        self.prog_bar.setValue(self.prog_bar.maximum())
        self.lbl_durum.setText(
            f"Tamamlandı  ·  {datetime.now().strftime('%H:%M')}  ·  "
            f"AL: {al_n}  SAT: {sat_n}  sinyal bulundu")
        self.statusBar().showMessage(
            f"Tarama tamamlandı — AL: {al_n}  SAT: {sat_n}")
        if al_n + sat_n == 0:
            self.detay.temizle()

    def _secildi(self, item):
        if item is None:
            return
        sonuc = item.data(Qt.ItemDataRole.UserRole)
        if not sonuc:
            return
        if sonuc.get('_fav_ek'):
            hisse   = sonuc.get('hisse', '')
            periyot = sonuc.get('periyot', '1d')
            self.lbl_durum.setText(f"Yükleniyor: {hisse}…")
            DetayPanel._thread_kapat(self._fav_fetch)
            self._fav_fetch = TekHisseFetchThread(hisse, periyot)
            self._fav_fetch.bitti.connect(self.detay.guncelle)
            self._fav_fetch.bitti.connect(lambda _: self.lbl_durum.setText(""))
            self._fav_fetch.hata.connect(lambda h, s: self.lbl_durum.setText(f"{h} — {s}"))
            self._fav_fetch.start()
        else:
            self.detay.guncelle(sonuc)
            # Taramadan gelen non-daily sonuç → arka planda günlük EMA çek
            if sonuc.get('periyot', '1d') != '1d' and sonuc.get('hisse'):
                DetayPanel._thread_kapat(self._ema_fetch)
                self._ema_fetch = TekHisseFetchThread(sonuc['hisse'], '1d')
                self._ema_fetch.bitti.connect(
                    lambda s, orig=sonuc: self._guncelle_ema(s, orig))
                self._ema_fetch.start()

    def _guncelle_ema(self, sonuc_gun: dict, sonuc_orig: dict):
        """Scan sonucuna günlük EMAları ekleyip chart'ı yeniler."""
        if self.detay._sonuc is not sonuc_orig:
            return  # Kullanıcı başka hisse seçmiş
        df_g   = sonuc_orig.get('df_grafik')
        df_gun = sonuc_gun.get('df_grafik')
        if df_g is None or df_gun is None:
            return
        # df_gun'daki günlük EMA kolonlarını df_g'ye hizala (vectorized)
        import pandas as pd, numpy as np
        def _to_days(idx):
            return pd.DatetimeIndex(idx).asi8 // (86_400 * 10**9)
        g_days = _to_days(df_g.index)
        e_arr  = _to_days(df_gun.index)
        for p in (5, 8, 13, 21, 50):
            col = f'EMA{p}'
            if col not in df_gun.columns:
                continue
            e_vals = df_gun[col].values.astype(float)
            idxs   = np.searchsorted(e_arr, g_days, side='right') - 1
            valid  = idxs >= 0
            result = np.full(len(df_g), np.nan)
            result[valid] = e_vals[idxs[valid]]
            df_g[col] = result
        self.detay.grafik.guncelle(
            df_g,
            sonuc_orig.get('destekler', [])[:3],
            sonuc_orig.get('direncler', [])[:3],
            sonuc_orig.get('hisse', ''),
            sonuc_orig.get('kutu'),
            ema_goster=self.detay._ema_goster,
        )

    @staticmethod
    def _filtre_btn_stili(aktif: bool, kod: str) -> str:
        if aktif:
            renk_map = {
                "AL":     (C_GREEN,   "#000000"),
                "SAT":    (C_RED,     "#ffffff"),
                "MACD":   ("#0a84ff", "#ffffff"),
                "HACİM":  ("#ff9f0a", "#000000"),
                "FAV":    ("#ffd60a", "#000000"),
                "TÜM":    ("#ffffff", "#000000"),
                "KUTU":   ("#f59e0b", "#000000"),
                "DESTEK": ("#34d399", "#000000"),
                "EMA":    ("#5b9cf6", "#ffffff"),
                "DIV":    ("#c084fc", "#ffffff"),
                "MUM":    ("#fb923c", "#000000"),
                "GUCLU":  ("#ffd60a", "#000000"),
            }
            bg, fg = renk_map.get(kod, ("#ffffff", "#000000"))
        else:
            bg, fg = C_CARD2, C_MUTED
        return (f"QPushButton{{background:{bg};color:{fg};border:none;"
                f"border-radius:8px;font-weight:{'600' if aktif else '400'};"
                f"font-size:12px;padding:0 10px;}}"
                f"QPushButton:hover{{background:#48484a;color:{C_TEXT};}}")

    def _filtre_sec(self, kod: str):
        self._filtre_aktif = kod
        for k, btn in self._filtre_butonlar.items():
            btn.setChecked(k == kod)
            btn.setStyleSheet(self._filtre_btn_stili(k == kod, k))
        self._liste_filtrele()

    def _liste_filtrele(self):
        # 1. Önceki turda eklenen favori satırlarını kaldır
        to_remove = []
        for i in range(self.liste.count()):
            item = self.liste.item(i)
            sonuc = item.data(Qt.ItemDataRole.UserRole)
            if sonuc and sonuc.get('_fav_ek'):
                to_remove.append(i)
        for i in reversed(to_remove):
            self.liste.takeItem(i)

        # 2. Normal gizle/göster + taranan hisse setini topla
        taradaki = set()
        for i in range(self.liste.count()):
            item = self.liste.item(i)
            sonuc = item.data(Qt.ItemDataRole.UserRole)
            genel    = sonuc.get('genel_sinyal', 'NÖTR') if sonuc else 'NÖTR'
            hisse_ad = sonuc.get('hisse', '') if sonuc else ''
            if hisse_ad:
                taradaki.add(hisse_ad)
            al_sinyal     = genel in SINYAL_RENK and genel not in (
                "GÜÇLÜ SAT", "SAT", "NÖTR", "MACD ÖLÜ", "DESTEK KIRILDI")
            sat_sinyal    = genel in ("GÜÇLÜ SAT", "SAT", "MACD ÖLÜ", "DESTEK KIRILDI")
            macd_sinyal   = genel in (
                "MACD KESİŞİM", "MACD YAKLAŞIM", "DESTEK+MACD", "KUTU+MACD",
                "HACİM+MACD", "EMA+MACD", "DIV+MACD")
            hacim_sinyal  = genel in ("HACİM KIRILIM", "HACİM+MACD")
            kutu_sinyal   = genel in ("KUTU AL", "KUTU+MACD")
            destek_sinyal = genel in ("DESTEK AL", "DESTEK+MACD")
            ema_sinyal    = genel in ("EMA SIRALANMA", "EMA PULLBACK", "EMA+MACD")
            div_sinyal    = genel in ("RSI DİVERJANS", "DIV+MACD")
            mum_sinyal    = genel == "YÜKSELİŞ FORMASYONU"
            guclu_sinyal  = (sonuc.get('sinyal_gucu', 0) >= 6) if sonuc else False
            fav_sinyal    = FAVORILER.favori_mi(hisse_ad)
            goster = (self._filtre_aktif == "TÜM" or
                      (self._filtre_aktif == "AL"      and al_sinyal) or
                      (self._filtre_aktif == "SAT"     and sat_sinyal) or
                      (self._filtre_aktif == "MACD"    and macd_sinyal) or
                      (self._filtre_aktif == "HACİM"   and hacim_sinyal) or
                      (self._filtre_aktif == "GUCLU"   and guclu_sinyal) or
                      (self._filtre_aktif == "KUTU"    and kutu_sinyal) or
                      (self._filtre_aktif == "DESTEK"  and destek_sinyal) or
                      (self._filtre_aktif == "EMA"     and ema_sinyal) or
                      (self._filtre_aktif == "DIV"     and div_sinyal) or
                      (self._filtre_aktif == "MUM"     and mum_sinyal) or
                      (self._filtre_aktif == "FAV"     and fav_sinyal))
            item.setHidden(not goster)

        # 3. FAV filtresi aktifse — taramada olmayan favorileri listele
        if self._filtre_aktif == "FAV":
            for hisse, fav_data in FAVORILER.hepsi().items():
                if hisse not in taradaki:
                    sonuc_ek = {
                        'hisse':        hisse,
                        'fiyat':        fav_data.get('fiyat', 0),
                        'periyot':      fav_data.get('periyot', '1d'),
                        'genel_sinyal': fav_data.get('sinyal', 'NÖTR'),
                        '_fav_ek':      True,
                    }
                    item, widget = _liste_satiri_olustur(sonuc_ek, pin_cb=lambda h: self._pin_toggle(h))
                    self.liste.addItem(item)
                    self.liste.setItemWidget(item, widget)

    def _pin_toggle(self, hisse: str):
        SABITLENMIS.toggle(hisse)
        self._yeniden_sirala()

    def _yeniden_sirala(self):
        """Sabitlenen hisseleri üste taşı; listeyi _sonuclar'dan yeniden oluştur."""
        self.liste.clear()
        self._pin_count = 0
        pinned  = [s for s in self._sonuclar if SABITLENMIS.sabitlenen(s.get('hisse', ''))]
        diger   = [s for s in self._sonuclar if not SABITLENMIS.sabitlenen(s.get('hisse', ''))]
        for sonuc in pinned + diger:
            item, widget = _liste_satiri_olustur(sonuc, pin_cb=lambda h: self._pin_toggle(h))
            self.liste.addItem(item)
            self.liste.setItemWidget(item, widget)
            if SABITLENMIS.sabitlenen(sonuc.get('hisse', '')):
                self._pin_count += 1
        self._liste_filtrele()

    def _oto_ayarla(self):
        self._oto_timer.stop()
        DAKIKA = {"15 dk": 15, "30 dk": 30, "1 saat": 60}
        sec = self.cmb_oto.currentText()
        if sec in DAKIKA:
            self._oto_timer.start(DAKIKA[sec] * 60 * 1000)

    def _oto_tara(self):
        if not (self._thread and self._thread.isRunning()):
            self._baslat()

    def _gecmis_ac(self):
        dlg = GecmisDialog(self)
        dlg.exec()

    def _alarmlar_ac(self):
        dlg = AlarmYonetimDialog(self)
        dlg.exec()

    def _portfoy_ac(self):
        dlg = PortfoyDialog(self)
        dlg.exec()

    def _telegram_ac(self):
        dlg = TelegramAyarDialog(self)
        dlg.exec()

    def _stratejiler_ac(self):
        dlg = StratejilerDialog(self)
        dlg.exec()

    def _backtest_ac(self):
        hisse = ''
        if self.detay._sonuc:
            hisse = self.detay._sonuc.get('hisse', '')
        dlg = BacktestDialog(self, hisse=hisse)
        dlg.exec()

    def _risk_ayar_menu_ac(self):
        RiskAyarDialog(self).exec()

    def _alarm_bildir(self, hisse_raw: str, hedef: float, guncel: float):
        try:
            winsound.Beep(1200, 180)
            winsound.Beep(1400, 180)
        except Exception:
            pass
        # Portföy stop/hedef alarmları STOP:HİSSE veya HEDEF:HİSSE formatında gelir
        if hisse_raw.startswith("STOP:"):
            hisse = hisse_raw[5:]
            baslik = f"STOP Uyarısı: {hisse}"
            mesaj  = f"Stop ₺{hedef:.2f} kırıldı — güncel ₺{guncel:.2f}"
            telegram_mesaj = f"🔴 <b>STOP Uyarısı: {hisse}</b>\nStop ₺{hedef:.2f} kırıldı — güncel ₺{guncel:.2f}"
        elif hisse_raw.startswith("HEDEF:"):
            hisse = hisse_raw[6:]
            baslik = f"Hedef Yakalandı: {hisse}"
            mesaj  = f"Hedef ₺{hedef:.2f} aşıldı — güncel ₺{guncel:.2f}"
            telegram_mesaj = f"🟢 <b>Hedef Yakalandı: {hisse}</b>\nHedef ₺{hedef:.2f} aşıldı — güncel ₺{guncel:.2f}"
        else:
            hisse = hisse_raw
            baslik = f"Fiyat Alarmı: {hisse}"
            mesaj  = f"Hedef ₺{hedef:.2f} aşıldı — güncel ₺{guncel:.2f}"
            telegram_mesaj = f"🔔 <b>Fiyat Alarmı: {hisse}</b>\nHedef ₺{hedef:.2f} aşıldı — güncel ₺{guncel:.2f}"
            ALARMLAR.kaldir(hisse)
        self._tray.showMessage(baslik, mesaj, QSystemTrayIcon.MessageIcon.Information, 6000)
        self.statusBar().showMessage(f"{baslik}: {hisse} → ₺{guncel:.2f}  (₺{hedef:.2f})")
        TELEGRAM.gonder(telegram_mesaj)

    def _csv_aktar(self):
        if not self._sonuclar:
            QMessageBox.information(self, "CSV", "Dışa aktarılacak tarama sonucu yok.")
            return
        from PyQt6.QtWidgets import QFileDialog
        import csv
        yol, _ = QFileDialog.getSaveFileName(
            self, "CSV Kaydet", "tarama_sonuclari.csv", "CSV (*.csv)")
        if not yol:
            return
        try:
            guclu  = [s for s in self._sonuclar if s.get('sinyal_gucu', 0) >= 6]
            diger  = [s for s in self._sonuclar if s.get('sinyal_gucu', 0) <  6]
            tarih  = datetime.now().strftime('%d.%m.%Y %H:%M')
            baslik = ['Tarih', 'Hisse', 'Periyot', 'Sinyal', 'Fiyat', 'Skor']

            def _satir(s):
                return [tarih, s.get('hisse',''), s.get('periyot',''),
                        s.get('genel_sinyal',''), s.get('fiyat',''), s.get('sinyal_gucu','')]

            with open(yol, 'w', newline='', encoding='utf-8-sig') as f:
                w = csv.writer(f)
                w.writerow([f'=== GÜÇLÜ SİNYALLER (Skor 6+) — {len(guclu)} adet ==='])
                w.writerow(baslik)
                for s in sorted(guclu, key=lambda x: x.get('sinyal_gucu', 0), reverse=True):
                    w.writerow(_satir(s))
                if diger:
                    w.writerow([])
                    w.writerow([f'=== DİĞER SİNYALLER (Skor 1–5) — {len(diger)} adet ==='])
                    w.writerow(baslik)
                    for s in sorted(diger, key=lambda x: x.get('sinyal_gucu', 0), reverse=True):
                        w.writerow(_satir(s))
            QMessageBox.information(
                self, "Dışa Aktarıldı",
                f"Güçlü (6+): {len(guclu)} · Diğer: {len(diger)}\n{yol}")
        except Exception as e:
            QMessageBox.warning(self, "Hata", f"CSV kaydedilemedi:\n{e}")

    def _guncelleme_kontrol(self):
        self._gun_thread = GuncellemeFetchThread()
        self._gun_thread.sonuc.connect(self._guncelleme_goster)
        self._gun_thread.hata.connect(lambda: QMessageBox.information(
            self, "Güncelleme", "GitHub'a bağlanılamadı veya depo bulunamadı."))
        self._gun_thread.start()
        self.statusBar().showMessage("Güncelleme kontrol ediliyor…")

    def _guncelleme_goster(self, sha: str, mesaj: str):
        cevap = QMessageBox.question(
            self, "Güncelleme Mevcut",
            f"Yeni sürüm: {sha}\n\n{mesaj}\n\nGitHub sayfasını aç?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if cevap == QMessageBox.StandardButton.Yes:
            import webbrowser
            webbrowser.open("https://github.com/mehmettoplu-ship-it/hisseSinyal")
        dosya = os.path.join(os.path.dirname(__file__), "versiyon.json")
        try:
            with open(dosya, 'w', encoding='utf-8') as f:
                json.dump({"sha": sha}, f)
        except Exception:
            pass

    def _hisse_ara(self):
        giriş = self.txt_hisse.text().strip().upper()
        if not giriş:
            return
        periyotlar = self._secilen_periyotlar()
        self.txt_hisse.clear()
        self.btn_hisse_ara.setEnabled(False)
        self.btn_hisse_ara.setText("⏳")
        self.statusBar().showMessage(f"{giriş} analiz ediliyor…")

        self._analiz_hisse      = giriş
        self._analiz_bekleyen   = len(periyotlar)
        self._analiz_bulunan    = 0
        self._analiz_threads    = []
        for periyot in periyotlar:
            t = TekHisseFetchThread(giriş, periyot)
            t.bitti.connect(self._analiz_sonucu)
            t.hata.connect(self._analiz_hata)
            t.finished.connect(t.deleteLater)
            self._analiz_threads.append(t)
            t.start()

    def _analiz_sonucu(self, sonuc: dict):
        item, widget = _liste_satiri_olustur(sonuc, pin_cb=lambda h: self._pin_toggle(h))
        self.liste.insertItem(0, item)
        self.liste.setItemWidget(item, widget)
        self.liste.setCurrentItem(item)
        self._sonuclar.insert(0, sonuc)
        self._analiz_bulunan += 1
        self._analiz_bitti()

    def _analiz_hata(self, hisse: str, sebep: str = ""):
        self._analiz_bitti()
        if sebep:
            self.statusBar().showMessage(f"{hisse} — {sebep}", 8000)

    def _analiz_bitti(self):
        self._analiz_bekleyen -= 1
        if self._analiz_bekleyen > 0:
            return
        self.btn_hisse_ara.setEnabled(True)
        self.btn_hisse_ara.setText("Analiz")
        if self._analiz_bulunan == 0:
            hisse = getattr(self, '_analiz_hisse', '?')
            self.statusBar().showMessage(
                f"{hisse} — Yahoo Finance'de yeterli geçmiş veri bulunamadı")
            QMessageBox.warning(
                self, f"{hisse} — Veri Yok",
                f"<b>{hisse}</b> için Yahoo Finance'de yeterli geçmiş fiyat verisi bulunamadı.<br><br>"
                f"Bu hisse yakın zamanda listelenmiş veya Yahoo Finance'de veri eksik olabilir.<br>"
                f"BIST'te işlem görüyor olsa bile bazı hisseler için tarihsel veri mevcut değildir.")
        else:
            self.statusBar().showMessage(
                f"{getattr(self, '_analiz_hisse', '')} — {self._analiz_bulunan} periyot analiz edildi")

# ═══════════════════════════════════════════════════════════
# Başlangıç
# ═══════════════════════════════════════════════════════════
def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(DARK_QSS)
    pencere = AnaPencere()
    pencere.showMaximized()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
