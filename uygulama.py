
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
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer, QSize
from PyQt6.QtGui import QFont, QColor, QClipboard, QIcon, QAction

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
# Alarm Kontrol Thread
# ═══════════════════════════════════════════════════════════
class AlarmThread(QThread):
    tetiklendi = pyqtSignal(str, float, float)   # hisse, hedef, guncel

    def __init__(self):
        super().__init__()
        self._dur = False

    def dur(self):
        self._dur = True

    def run(self):
        import time
        import yfinance as yf
        while not self._dur:
            alarmlar = list(ALARMLAR.listesi().items())
            for hisse, hedef in alarmlar:
                if self._dur:
                    break
                try:
                    # 2 günlük 1s'lik veri → bugünün en güncel saatlik kapanışı
                    df = yf.download(
                        f"{hisse}.IS", period="2d", interval="1h",
                        auto_adjust=True, progress=False,
                    )
                    if df is not None and not df.empty:
                        from tarayici import _sutunlari_duzenle
                        df = _sutunlari_duzenle(df)
                        guncel = float(df['Close'].iloc[-1])
                        if guncel >= hedef:
                            self.tetiklendi.emit(hisse, hedef, guncel)
                except Exception:
                    pass
            # 5 dakika bekle — 1'er saniyelik uykularla iptal edilebilir
            for _ in range(300):
                if self._dur:
                    break
                time.sleep(1)


SINYAL_RENK = {
    "KUTU+MACD":     "#fbbf24",   # parlak altın — en güçlü kombinasyon
    "HACİM+MACD":    "#4ade80",   # parlak yeşil — hacim kırılımı + macd
    "DESTEK+MACD":   "#2dd4bf",   # parlak teal — destek + macd teyidi
    "KUTU AL":       "#f59e0b",   # amber — konsolidasyon kutusu
    "HACİM KIRILIM": "#fcd34d",   # sarı-amber — hacim kırılımı
    "MACD KESİŞİM":  "#38bdf8",   # sky blue — taze kesişim
    "EMA SIRALANMA": "#86efac",   # açık yeşil — ema dizilimi
    "MACD YAKLAŞIM": "#818cf8",   # indigo — yaklaşıyor
    "DESTEK AL":     "#34d399",   # yeşil — destekte tutunma
    "GÜÇLÜ SAT":    C_RED,
    "SAT":          C_RED,
    "NÖTR":         C_MUTED,
}
C_KUTU = "#f59e0b"  # amber — kutu konsolidasyon rengi

# Sinyal badge arka plan renkleri
_SINYAL_BG = {
    "KUTU+MACD":     "#5a3c00",
    "HACİM+MACD":    "#064e3b",
    "DESTEK+MACD":   "#0c3d38",
    "KUTU AL":       "#6b4c00",
    "HACİM KIRILIM": "#713f12",
    "MACD KESİŞİM":  "#0c3547",
    "EMA SIRALANMA": "#14532d",
    "MACD YAKLAŞIM": "#1e1b4b",
    "DESTEK AL":     "#064e3b",
    "GÜÇLÜ SAT":    "#5c1111",
    "SAT":          C_RED_DIM,
}

def sinyal_bg(genel: str) -> str:
    return _SINYAL_BG.get(genel, C_HEADER)

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
    border-radius: 2px;
    height: 4px;
    text-align: center;
    font-size: 0px;
}}
QProgressBar::chunk {{ background-color: {C_GREEN}; border-radius: 2px; }}
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

    def __init__(self, parent=None):
        self.fig = Figure(facecolor=self.BG_FRAME)
        super().__init__(self.fig)
        self.setParent(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumHeight(300)

    def guncelle(self, df_g, destekler, direncler, hisse="", kutu=None, ema_goster=True):
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
            ax_vol.set_xlim(-0.8, n - 0.2)
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
        ax.set_xlim(-0.8, n - 0.2)
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
        for idx, d in enumerate(destekler):
            guc = 1.0 - idx * 0.20
            lw  = 1.6 - idx * 0.3
            mesafe = (son_k - d) / son_k * 100 if son_k > 0 else 0
            # Glow + dashed çizgi
            ax.axhline(d, color=self.C_DESTEK, lw=lw * 5, alpha=0.05, zorder=3)
            ax.axhline(d, color=self.C_DESTEK, lw=lw,
                       linestyle='--', alpha=guc * 0.9, zorder=5)
            # Bölge gölgesi ±%0.5
            ax.axhspan(d * 0.995, d * 1.005,
                       alpha=max(0.02, 0.07 - idx * 0.02),
                       color=self.C_DESTEK, zorder=1)
            ax.plot(n - 1, d, 'o', color=self.C_DESTEK,
                    ms=4.5 - idx * 0.5, alpha=guc * 0.9, zorder=7)
            _etiket_ekle(_frac(d),
                         f" D{idx+1}  {d:.2f}  ↓{mesafe:.1f}% ",
                         self.C_DESTEK, self.BG_CHART)

        # ── Direnç çizgileri ─────────────────────────
        for idx, rv in enumerate(direncler):
            guc = 1.0 - idx * 0.20
            lw  = 1.6 - idx * 0.3
            mesafe = (rv - son_k) / son_k * 100 if son_k > 0 else 0
            ax.axhline(rv, color=self.C_DIRENC, lw=lw * 5, alpha=0.05, zorder=3)
            ax.axhline(rv, color=self.C_DIRENC, lw=lw,
                       linestyle='--', alpha=guc * 0.9, zorder=5)
            ax.axhspan(rv * 0.995, rv * 1.005,
                       alpha=max(0.02, 0.07 - idx * 0.02),
                       color=self.C_DIRENC, zorder=1)
            ax.plot(n - 1, rv, 'o', color=self.C_DIRENC,
                    ms=4.5 - idx * 0.5, alpha=guc * 0.9, zorder=7)
            _etiket_ekle(_frac(rv),
                         f" R{idx+1}  {rv:.2f}  ↑{mesafe:.1f}% ",
                         self.C_DIRENC, self.BG_CHART)

        # ── Kutu konsolidasyon ────────────────────────
        if kutu:
            k_d   = kutu['destek']
            k_r   = kutu['direnc']
            k_pct = kutu['aralik_pct']
            k_doc = kutu.get('dokunma', 0)
            k_bar = kutu.get('gun_sayisi', 30)
            x0    = max(0, n - k_bar - 1)

            # Dolu alan — kutu barları boyunca x-kısıtlı
            xs = list(range(x0, n))
            ax.fill_between(xs, k_d, k_r,
                            alpha=0.11, color=self.C_KUTU, zorder=1)
            # Sol kenar
            ax.plot([x0, x0], [k_d, k_r],
                    color=self.C_KUTU, lw=0.7, alpha=0.35, zorder=4)
            # Alt çizgi (destek) — solid
            ax.plot([x0, n - 0.2], [k_d, k_d],
                    color=self.C_KUTU, lw=2.0, alpha=0.90, zorder=6)
            ax.axhline(k_d, color=self.C_KUTU, lw=6, alpha=0.05, zorder=3)
            # Üst çizgi (hedef/kırılım) — dashed
            ax.plot([x0, n - 0.2], [k_r, k_r],
                    color=self.C_KUTU, lw=1.4, linestyle='--', alpha=0.85, zorder=6)
            ax.axhline(k_r, color=self.C_KUTU, lw=6, alpha=0.05, zorder=3)
            _etiket_ekle(_frac(k_r),
                         f" KUTU ▸ {k_r:.2f}  %{k_pct} ",
                         self.C_KUTU, "#2d1e00")
            _etiket_ekle(_frac(k_d),
                         f" KUTU ▸ {k_d:.2f}  {k_doc}x ",
                         self.C_KUTU, "#2d1e00")

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

        self.btn_kopyala = QPushButton("📋")
        self.btn_kopyala.setFixedSize(38, 38)
        self.btn_kopyala.setToolTip("Bildirim metnini kopyala")
        self.btn_kopyala.setObjectName("copyBtn")
        self.btn_kopyala.setStyleSheet(
            f"QPushButton{{background:{C_CARD2};border:none;"
            f"border-radius:10px;font-size:15px;padding:0;}}"
            f"QPushButton:hover{{background:{C_BLUE};}}")
        self.btn_kopyala.clicked.connect(self._kopyala)

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
        baslik_layout.addWidget(self.btn_kopyala)
        root.addLayout(baslik_layout)

        # ── Alt başlık: tarih + periyot segmented control ──
        alt_layout = QHBoxLayout()
        self.lbl_tarih = QLabel("")
        self.lbl_tarih.setObjectName("gecikme")
        alt_layout.addWidget(self.lbl_tarih)
        alt_layout.addStretch()

        # EMA toggle butonu
        self._ema_goster = True
        self.btn_ema = QPushButton("EMA")
        self.btn_ema.setCheckable(True)
        self.btn_ema.setChecked(True)
        self.btn_ema.setFixedSize(46, 28)
        self.btn_ema.setStyleSheet(self._ema_btn_stili(True))
        self.btn_ema.clicked.connect(self._ema_toggle)
        alt_layout.addWidget(self.btn_ema)
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
        for etiket, kod in [("1S","1h"), ("4S","4h"), ("Gün","1d"), ("Haf","1w")]:
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

        # ── Göstergeler Grid (2×3) ────────────
        self.grid = QGridLayout()
        self.grid.setSpacing(10)
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
        root.addLayout(self.grid)

        # ── Teknik Özet Satırı ────────────────
        ozet_frame = QFrame()
        ozet_frame.setFixedHeight(34)
        ozet_frame.setStyleSheet(f"background:{C_CARD}; border-radius:10px; border:none;")
        ozet_lay = QHBoxLayout(ozet_frame)
        ozet_lay.setContentsMargins(10, 4, 10, 4)
        ozet_lay.setSpacing(6)
        self._ozet_rsi  = QLabel("RSI: —")
        self._ozet_macd = QLabel("MACD: —")
        self._ozet_ema  = QLabel("EMA: —")
        self._ozet_vol  = QLabel("Vol: —")
        _pill_base = (f"color:{C_MUTED}; font-size:11px; font-weight:600; "
                      f"background:{C_CARD2}; border-radius:6px; padding:2px 9px; border:none;")
        for lbl in (self._ozet_rsi, self._ozet_macd, self._ozet_ema, self._ozet_vol):
            lbl.setStyleSheet(_pill_base)
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            ozet_lay.addWidget(lbl)
        ozet_lay.addStretch()
        root.addWidget(ozet_frame)

        # ── Mum Grafiği (tam alan) ────────────
        self.grafik = GrafikWidget(self)
        root.addWidget(self.grafik, stretch=1)

        self._sonuc = None

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

    def _ema_toggle(self):
        self._ema_goster = not self._ema_goster
        self.btn_ema.setChecked(self._ema_goster)
        self.btn_ema.setStyleSheet(self._ema_btn_stili(self._ema_goster))
        if self._sonuc:
            df_g = self._sonuc.get('df_grafik')
            self.grafik.guncelle(
                df_g,
                self._sonuc.get('destekler', [])[:3],
                self._sonuc.get('direncler', [])[:3],
                self._sonuc.get('hisse', ''),
                self._sonuc.get('kutu'),
                ema_goster=self._ema_goster,
            )

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
            lambda h: self.lbl_tarih.setText(f"{h} — veri alınamadı"))
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

        renk = SINYAL_RENK.get(genel, C_MUTED)
        bg   = sinyal_bg(genel)
        self.lbl_sinyal_btn.setText(genel)
        self.lbl_sinyal_btn.setStyleSheet(
            f"background-color:{bg}; color:{renk}; border-radius:8px; "
            f"padding:6px 10px; font-weight:700; font-size:14px;")

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

        # Grafik
        df_g = sonuc.get('df_grafik')
        self.grafik.guncelle(
            df_g,
            sonuc.get('destekler', [])[:3],
            sonuc.get('direncler', [])[:3],
            hisse,
            sonuc.get('kutu'),
            ema_goster=self._ema_goster,
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
        gun_sayilari = {"1h": 3, "4h": 18, "1d": 3, "1w": 3}
        al_n = sat_n = 0
        toplam = len(self.hisseler) * len(self.periyotlar)
        say = 0

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
                        if genel_s in SINYAL_RENK and genel_s not in ("GÜÇLÜ SAT", "SAT", "NÖTR"):
                            al_n += 1
                            GECMIS.kaydet(hisse, genel_s, sonuc['fiyat'], periyot)
                        else:
                            sat_n += 1
                        self.sinyal_buldu.emit(sonuc)

        self.bitti.emit(al_n, sat_n)


class TekHisseFetchThread(QThread):
    """Tek bir hisse için arka planda veri çeker (favoriler için)."""
    bitti = pyqtSignal(dict)
    hata  = pyqtSignal(str)

    def __init__(self, hisse: str, periyot: str):
        super().__init__()
        self.hisse   = hisse
        self.periyot = periyot

    def run(self):
        gun_sayilari = {"1h": 3, "4h": 18, "1d": 3, "1w": 3}
        df = veri_cek(self.hisse, self.periyot)
        if df is None:
            self.hata.emit(self.hisse)
            return
        # Günlük olmayan periyotlarda EMAlar için günlük close çek
        close_gunluk = None
        if self.periyot != "1d":
            df_gun = veri_cek(self.hisse, "1d")
            if df_gun is not None and 'Close' in df_gun.columns:
                close_gunluk = df_gun['Close']
        sonuc = sinyal_hesapla(df, self.periyot, gun_sayilari.get(self.periyot, 3),
                               close_gunluk=close_gunluk)
        if sonuc:
            sonuc['hisse'] = self.hisse
            self.bitti.emit(sonuc)
        else:
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
    layout.addWidget(lbl_s)

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
# Ana Pencere
# ═══════════════════════════════════════════════════════════
class AnaPencere(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("BIST Sinyal Tarayıcısı")
        self.resize(1280, 820)
        self._thread    = None
        self._fav_fetch = None
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

        lbl_logo = QLabel("BIST Sinyal")
        lbl_logo.setStyleSheet(
            f"color:{C_TEXT}; font-size:17px; font-weight:700; letter-spacing:-0.3px;")
        tb.addWidget(lbl_logo)
        tb.addSpacing(4)

        # Periyot — segmented control görünümü
        seg_bg = QWidget()
        seg_bg.setFixedHeight(32)
        seg_bg.setStyleSheet(
            f"background:{C_CARD2}; border-radius:10px;")
        seg_lay = QHBoxLayout(seg_bg)
        seg_lay.setContentsMargins(3, 3, 3, 3)
        seg_lay.setSpacing(2)

        self._periyot_butonlar = {}
        _PER_BTN = [("1S", "1h"), ("4S", "4h"), ("Gün", "1d"), ("Haf", "1w")]
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

        act_alarmlar = QAction("🔔   Alarmlar", self)
        act_alarmlar.triggered.connect(self._alarmlar_ac)
        self._ayar_menu.addAction(act_alarmlar)

        self._ayar_menu.addSeparator()

        act_gecmis = QAction("📋   Sinyal Geçmişi", self)
        act_gecmis.triggered.connect(self._gecmis_ac)
        self._ayar_menu.addAction(act_gecmis)

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
        self.prog_bar.setFixedHeight(4)
        self.prog_bar.setTextVisible(False)

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

        for etiket, kod, bar in [
            ("Tümü", "TÜM", filtre_bar1),
            ("AL",   "AL",  filtre_bar1),
            ("SAT",  "SAT", filtre_bar1),
            ("MACD", "MACD", filtre_bar2),
            ("HACİM", "HACİM", filtre_bar2),
            ("★ Favori", "FAV", filtre_bar2),
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
            self._fav_fetch.hata.connect(lambda h: self.lbl_durum.setText(f"{h} veri alınamadı"))
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
        # df_gun'daki günlük EMA kolonlarını df_g'ye hizala
        import pandas as pd, numpy as np
        def _gun_no(ts):
            return int(pd.Timestamp(ts).value // (86_400 * 10**9))
        g_days = [_gun_no(t) for t in df_g.index]
        e_days = [_gun_no(t) for t in df_gun.index]
        e_arr  = np.array(e_days)
        for p in (5, 8, 13, 21, 50):
            col = f'EMA{p}'
            if col not in df_gun.columns:
                continue
            e_vals = df_gun[col].values.astype(float)
            result = np.full(len(df_g), np.nan)
            for i, gd in enumerate(g_days):
                idx = int(np.searchsorted(e_arr, gd, side='right')) - 1
                if idx >= 0:
                    result[i] = e_vals[idx]
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
                "AL":    (C_GREEN,       "#000000"),
                "SAT":   (C_RED,         "#ffffff"),
                "MACD":  ("#0a84ff",     "#ffffff"),
                "HACİM": ("#ff9f0a",     "#000000"),
                "FAV":   ("#ffd60a",     "#000000"),
                "TÜM":   ("#ffffff",     "#000000"),
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
            al_sinyal    = genel in SINYAL_RENK and genel not in ("GÜÇLÜ SAT", "SAT", "NÖTR")
            sat_sinyal   = genel in ("GÜÇLÜ SAT", "SAT")
            macd_sinyal  = genel in ("MACD KESİŞİM", "MACD YAKLAŞIM", "DESTEK+MACD", "KUTU+MACD", "HACİM+MACD")
            hacim_sinyal = genel in ("HACİM KIRILIM", "HACİM+MACD")
            fav_sinyal   = FAVORILER.favori_mi(hisse_ad)
            goster = (self._filtre_aktif == "TÜM" or
                      (self._filtre_aktif == "AL"     and al_sinyal) or
                      (self._filtre_aktif == "SAT"    and sat_sinyal) or
                      (self._filtre_aktif == "MACD"   and macd_sinyal) or
                      (self._filtre_aktif == "HACİM"  and hacim_sinyal) or
                      (self._filtre_aktif == "FAV"    and fav_sinyal))
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

    def _alarm_bildir(self, hisse: str, hedef: float, guncel: float):
        try:
            winsound.Beep(1200, 180)
            winsound.Beep(1400, 180)
        except Exception:
            pass
        self._tray.showMessage(
            f"Fiyat Alarmı: {hisse}",
            f"Hedef ₺{hedef:.2f} aşıldı — güncel ₺{guncel:.2f}",
            QSystemTrayIcon.MessageIcon.Information,
            6000,
        )
        ALARMLAR.kaldir(hisse)
        self.statusBar().showMessage(
            f"Alarm tetiklendi: {hisse} → ₺{guncel:.2f}  (hedef ₺{hedef:.2f})")

    def _hisse_ara(self):
        giriş = self.txt_hisse.text().strip().upper()
        if not giriş:
            return
        periyotlar = self._secilen_periyotlar()
        gun_sayilari = {"1h": 3, "4h": 18, "1d": 3, "1w": 3}
        for periyot in periyotlar:
            df = veri_cek(giriş, periyot)
            if df is None:
                self.statusBar().showMessage(f"{giriş} bulunamadı veya veri yok")
                continue
            sonuc = sinyal_hesapla(df, periyot, gun_sayilari[periyot])
            if sonuc:
                sonuc['hisse'] = giriş
                item, widget = _liste_satiri_olustur(sonuc, pin_cb=lambda h: self._pin_toggle(h))
                self.liste.insertItem(0, item)
                self.liste.setItemWidget(item, widget)
                self.liste.setCurrentItem(item)
                self._sonuclar.insert(0, sonuc)
        self.txt_hisse.clear()

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
