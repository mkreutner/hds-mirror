#!/usr/bin/env python3
"""Miroir de l'écran du OWON HDS2202S. Affichage seul.
M : mode suivant (à appuyer avec Mode du HDS). F11 : plein écran. Esc : fenêtré. Q : quitter.
Lancement : hds_mirror.py [osc|dmm|gen] ; sans argument, reprend le dernier mode affiché."""
import glob, json, os, re, struct, sys, time
import numpy as np
import serial

# ----------------------------------------------------------------------------- SCPI
class Hds:
    def __init__(self, dev=None):
        dev = dev or next(iter(glob.glob("/dev/ttyUSB*")), None)
        if not dev:
            sys.exit("aucun /dev/ttyUSB* : scope branché et allumé ?")
        self.s = serial.Serial(dev, 115200, timeout=0.1)

    def text(self, cmd, timeout=0.5):
        self.s.reset_input_buffer()
        self.s.write((cmd + "\n").encode())
        buf, t0 = b"", time.monotonic()
        while time.monotonic() - t0 < timeout:
            buf += self.s.read(256)
            if buf.endswith(b"\n"):
                break
        return buf.decode(errors="replace").strip()

    def block(self, cmd, timeout=1.0):
        self.s.reset_input_buffer()
        self.s.write((cmd + "\n").encode())
        head = self._exact(4, timeout)
        return self._exact(struct.unpack("<I", head)[0], timeout)

    def _exact(self, n, timeout):
        buf, t0 = b"", time.monotonic()
        while len(buf) < n:
            if time.monotonic() - t0 > timeout:
                raise TimeoutError(f"{len(buf)}/{n} octets")
            buf += self.s.read(n - len(buf))
        return buf

    # oscillo
    def head(self):
        return json.loads(self.block(":DATa:WAVe:SCReen:HEAD?"))

    def wave(self, ch):
        return np.frombuffer(self.block(f":DATa:WAVe:SCReen:CH{ch}?"), dtype=np.int8)

    # multimètre : ne répond qu'en mode DMM
    def dmm(self):
        v = self.text(":DMM:MEAS?", 0.3)
        if not v:
            return None
        q = lambda c: self.text(c)
        return {"value": v, "volt": q(":DMM:CONFigure:VOLTage?"), "curr": q(":DMM:CONFigure:CURRent?"),
                "func": q(":DMM:CONFigure?"), "range": q(":DMM:RANGE?")}

    # générateur : fréquence en µHz et amplitude/offset en mV sur firmware V1.2.0
    def gen(self):
        q = lambda c: self.text(c)
        f = lambda s, d: float(s) / d if re.match(r"^[-+]?[\d.]+(e[-+]?\d+)?$", s or "") else 0.0
        return {"wave": q(":FUNCtion?"), "freq": f(q(":FUNCtion:FREQuency?"), 1e6),
                "ampl": f(q(":FUNCtion:AMPLitude?"), 1e3), "offset": f(q(":FUNCtion:OFFSet?"), 1e3),
                "on": q(":CHANnel?").upper() in ("ON", "1")}


def si(x, unit, d=4):
    for p, s in ((1e6, "M"), (1e3, "k"), (1, ""), (1e-3, "m"), (1e-6, "µ")):
        if abs(x) >= p or p == 1e-6:
            return f"{x/p:.{d}g} {s}{unit}"


# ----------------------------------------------------------------------------- UI
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QKeySequence, QShortcut
from PySide6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QStackedWidget
import pyqtgraph as pg

MONO = QFont("DejaVu Sans Mono", 11)
YEL, CYA = "#ffd400", "#30c8ff"
CPL = {"AC": "~", "DC": "⎓", "GND": "⏚"}


def tag(text="", color="#ddd", bg="#101828"):
    l = QLabel(text); l.setFont(MONO)
    l.setStyleSheet(f"color:{color}; background:{bg}; padding:1px 6px; border-radius:2px;")
    return l


def black(w):
    w.setAttribute(Qt.WA_StyledBackground, True); w.setStyleSheet("background:#000;")
    return w


def grid_plot(hdiv, vdiv):
    p = pg.PlotWidget(background="#000"); pi = p.getPlotItem()
    pi.hideAxis("left"); pi.hideAxis("bottom"); pi.hideButtons(); pi.setMenuEnabled(False); pi.setMouseEnabled(x=False, y=False)
    pi.setXRange(-hdiv / 2, hdiv / 2, padding=0); pi.setYRange(-vdiv / 2, vdiv / 2, padding=0)
    g, a = pg.mkPen("#3a5a9a", style=Qt.DotLine), pg.mkPen("#6a8ad0", style=Qt.DotLine)
    for i in range(-hdiv // 2, hdiv // 2 + 1): pi.addLine(x=i, pen=a if i == 0 else g)
    for i in range(-vdiv // 2, vdiv // 2 + 1): pi.addLine(y=i, pen=a if i == 0 else g)
    return p


class Osc(QWidget):
    def __init__(self):
        super().__init__(); black(self)
        lay = QVBoxLayout(self); lay.setContentsMargins(6, 4, 6, 4); lay.setSpacing(3)
        top = QHBoxLayout(); self.trig = tag("Trig", "#8f8", "#0a3"); self.tb = tag("", "#ff8"); self.hoff = tag("", "#f98")
        for w in (self.trig, self.tb, self.hoff): top.addWidget(w)
        top.addStretch(); lay.addLayout(top)
        self.plot = grid_plot(12, 8); lay.addWidget(self.plot, 1)
        pi = self.plot.getPlotItem()
        self.curves = {1: pi.plot(pen=pg.mkPen(YEL, width=1.5)), 2: pi.plot(pen=pg.mkPen(CYA, width=1.5))}
        self.marks = {1: pi.addLine(y=0, pen=pg.mkPen(YEL, width=2)), 2: pi.addLine(y=0, pen=pg.mkPen(CYA, width=2))}
        bot = QHBoxLayout(); self.ch = {1: tag("", YEL), 2: tag("", CYA)}; self.sr = tag("", "#fff"); self.trg = tag("", "#ff8")
        for w in (self.ch[1], self.ch[2], self.sr, self.trg): bot.addWidget(w)
        bot.addStretch(); lay.addLayout(bot)

    def update(self, h, waves):
        self.trig.setText(h["RUNSTATUS"].upper()); self.tb.setText("M:" + h["TIMEBASE"]["SCALE"]); self.hoff.setText(f"T:{h['TIMEBASE']['HOFFSET']} div")
        for i, c in enumerate(h["CHANNEL"], 1):
            on = c["DISPLAY"] == "ON"
            if on and i in waves:
                raw = waves[i]; n = len(raw)
                self.curves[i].setData(-6 + 12 * (0.5 + np.arange(n)) / n, raw / 25.0)
                self.marks[i].setValue(c["OFFSET"] / 25.0); self.marks[i].show()
            else:
                self.curves[i].clear(); self.marks[i].hide()
            self.ch[i].setText(f"{i} {c['SCALE']} {CPL.get(c['COUPLING'], '')}" + ("" if on else " off"))
        self.sr.setText(h["SAMPLE"]["SAMPLERATE"])
        it = h.get("Trig", {}).get("Items", {})
        self.trg.setText(f"{it.get('Channel','')}:{it.get('Coupling','')} {'∫' if it.get('Edge')=='RISE' else '∖'} {it.get('Level','')}")


class Dmm(QWidget):
    def __init__(self):
        super().__init__(); black(self)
        lay = QVBoxLayout(self); lay.setContentsMargins(6, 4, 6, 4)
        top = QHBoxLayout(); self.func = tag("", "#fff", "#1d3f93"); self.auto = tag("Auto", "#4f4"); self.rng = tag("", "#fff")
        for w in (self.func, self.auto, self.rng): top.addWidget(w)
        top.addStretch(); lay.addLayout(top)
        row = QHBoxLayout(); self.val = QLabel("-----"); self.val.setFont(QFont("DejaVu Sans Mono", 96, QFont.Bold)); self.val.setStyleSheet(f"color:{YEL};")
        self.unit = QLabel(""); self.unit.setFont(QFont("DejaVu Sans", 48, QFont.Bold)); self.unit.setStyleSheet(f"color:{YEL}; padding-bottom:20px;"); self.unit.setAlignment(Qt.AlignBottom)
        row.addStretch(); row.addWidget(self.val); row.addWidget(self.unit); row.addStretch()
        lay.addStretch(); lay.addLayout(row); lay.addStretch()

    def update(self, d):
        m = re.match(r"^\s*(\S+)\s*(.*)$", d["value"])
        self.val.setText(m.group(1) if m else d["value"]); self.unit.setText(m.group(2) if m else "")
        ok = lambda s: s and s != "error"
        f = d["volt"] if ok(d["volt"]) else d["curr"] if ok(d["curr"]) else d["func"] if ok(d["func"]) else "DMM"
        self.func.setText(("⎓ " if f.startswith("DC") else "~ " if f.startswith("AC") else "") + f)
        self.rng.setText("Range " + (d["range"] if ok(d["range"]) else "--"))


class Gen(QWidget):
    def __init__(self):
        super().__init__(); black(self)
        lay = QVBoxLayout(self); lay.setContentsMargins(6, 4, 6, 4)
        top = QHBoxLayout(); self.on = tag("OFF", "#fff", "#555"); self.wave = tag("", "#ff8"); self.load = tag("High Z", "#ff8")
        for w in (self.on, self.wave, self.load): top.addWidget(w)
        top.addStretch(); lay.addLayout(top)
        row = QHBoxLayout(); col = QVBoxLayout(); self.f = {}
        for k, t in (("freq", "Freq"), ("ampl", "Amplitude"), ("offset", "Offset"), ("wave", "Type")):
            l = QLabel(t); l.setStyleSheet("color:#9fc1ee;"); v = QLabel("—"); v.setFont(QFont("DejaVu Sans Mono", 24)); v.setStyleSheet("color:#fff; background:#1d3f93; padding:4px 10px;")
            col.addWidget(l); col.addWidget(v); self.f[k] = v
        col.addStretch(); row.addLayout(col)
        self.plot = grid_plot(4, 2); self.curve = self.plot.getPlotItem().plot(pen=pg.mkPen(YEL, width=1.5)); row.addWidget(self.plot, 1)
        lay.addLayout(row, 1)

    def update(self, g):
        self.on.setText("ON" if g["on"] else "OFF"); self.on.setStyleSheet(f"color:#fff; background:{'#0a3' if g['on'] else '#555'}; padding:1px 6px;")
        self.wave.setText(g["wave"]); self.f["wave"].setText(g["wave"])
        self.f["freq"].setText(si(g["freq"], "Hz")); self.f["ampl"].setText(si(g["ampl"], "Vpp", 3)); self.f["offset"].setText(si(g["offset"], "V", 3))
        t = np.linspace(0, 1, 400, endpoint=False); w = g["wave"].upper()
        y = (np.where(t < .5, 1, -1) if w.startswith("SQU") else np.where(t < .2, 1, -1) if w.startswith("PULS")
             else 4 * np.abs(t - .5) - 1 if w.startswith("RAMP") else np.sin(40 * np.pi * t) * np.exp(-3 * t) if w.startswith("AMPALT")
             else np.sinc(16 * (t - .5)) if w.startswith("SINC") else np.sin(2 * np.pi * t))
        self.curve.setData(-2 + 4 * t, y)


LAST = os.path.expanduser("~/.hds_mirror_mode")   # dernier mode affiché, repris au lancement


class Mirror(QMainWindow):
    """Le HDS n'expose pas son mode en SCPI : la touche M suit la touche Mode du HDS (OSC -> DMM -> GEN)."""
    ORDER = {"OSC": "DMM", "DMM": "GEN", "GEN": "OSC"}

    def __init__(self, hds):
        super().__init__(); self.hds = hds
        self.setWindowTitle(hds.text("*IDN?")); self.setStyleSheet("QMainWindow{background:#000;}")
        self.osc, self.dmm, self.gen = Osc(), Dmm(), Gen()
        self.stack = QStackedWidget()
        for s in (self.osc, self.dmm, self.gen): self.stack.addWidget(s)
        self.setCentralWidget(self.stack); self.mode = None
        QShortcut(QKeySequence("F11"), self, lambda: self.showNormal() if self.isFullScreen() else self.showFullScreen())
        QShortcut(QKeySequence("Escape"), self, self.showNormal)
        QShortcut(QKeySequence("Q"), self, QApplication.quit)
        QShortcut(QKeySequence("M"), self, lambda: self.show_mode(self.ORDER[self.mode]))
        arg = next((a.upper() for a in sys.argv[1:] if a.upper() in self.ORDER), None)
        self.show_mode(arg or (open(LAST).read().strip() if os.path.exists(LAST) else "OSC"))
        self.timer = QTimer(self, interval=200, timeout=self.poll); self.timer.start()

    def show_mode(self, m):
        self.mode = m
        try: open(LAST, "w").write(m)
        except OSError: pass
        self.stack.setCurrentWidget({"OSC": self.osc, "DMM": self.dmm, "GEN": self.gen}[m])
        if hasattr(self, "timer"): self.timer.setInterval(1000 if m == "GEN" else 200)
        self.statusBar().showMessage(f"{m}   (M : mode suivant · F11 : plein écran · Q : quitter)", 3000)

    def poll(self):
        try:
            if self.mode == "OSC":
                h = self.hds.head()
                self.osc.update(h, {i: self.hds.wave(i) for i, c in enumerate(h["CHANNEL"], 1) if c["DISPLAY"] == "ON"})
            elif self.mode == "DMM":
                d = self.hds.dmm()
                if d: self.dmm.update(d)
            else:
                self.gen.update(self.hds.gen())
        except Exception as e:
            self.statusBar().showMessage(str(e), 3000)


if __name__ == "__main__":
    if "--idn" in sys.argv:
        print(Hds().text("*IDN?") or "pas de réponse à *IDN?"); sys.exit()
    app = QApplication(sys.argv)
    w = Mirror(Hds()); w.resize(1280, 900); w.show()
    sys.exit(app.exec())
