# -*- coding: utf-8 -*-
"""貯金箱（自作版 v3.0）のシリアルログを読んで、判別した硬貨を画面に大きく出す。

  python coin_monitor.py            → XIAO（USB VID 303A）を自動で探す
  python coin_monitor.py COM7       → ポートを指定

・COIN 行が来るたびに、金額を大きく表示し、履歴と回数を足す
・「入れる硬貨」を選んでおくと、判定が合っていたか（○/×）と正解率を出す（50 枚試験用）
・「センサー試験」ボタンで sensortest に入り、ビーム 5 本の状態をランプで出す（音は鳴らない）
・受け取った行はすべて logs/ に保存する（CSV 行も入るので、あとで集計できる）
ポートはこのウィンドウがつかむので、開いている間は pio device monitor などは使えない。
"""
import queue
import re
import sys
import threading
import time
import tkinter as tk
from datetime import datetime
from pathlib import Path

import serial
from serial.tools import list_ports

HERE = Path(__file__).resolve().parent
LOG_DIR = HERE / "logs"
BAUD = 115200
VALUES = [1, 5, 10, 50, 100, 500]
BEAMS = ["HA", "HB", "P1", "P2", "P3"]
COLOR = {1: "#9aa0a6", 5: "#c9a227", 10: "#b0602c", 50: "#8fa3b0", 100: "#7d8f99", 500: "#d4a017"}

RE_COIN = re.compile(r"COIN value=(\d+) stage=(\d+) hole=(\d) v=(\d+) dt=(\d+)ms(.*?) -> (.*)$")
RE_LEVELS = re.compile(r"HA=(\d) HB=(\d) P1=(\d) P2=(\d) P3=(\d)")
RE_PULSE = re.compile(r"^(HA|HB|P1|P2|P3) high=([\d.]+)ms")
RE_JAM = re.compile(r"BEAM (HA|HB|P1|P2|P3) -> (JAM\?|clear)")


def find_port():
    for p in list_ports.comports():
        if p.vid == 0x303A:
            return p.device
    return None


class Reader(threading.Thread):
    """シリアルから 1 行ずつ読んで queue に積む。抜けたら 2 秒おきにつなぎ直す"""

    def __init__(self, port, q):
        super().__init__(daemon=True)
        self.port = port
        self.q = q
        self.ser = None
        self.lock = threading.Lock()

    def send(self, cmd):
        with self.lock:
            if self.ser:
                try:
                    self.ser.write((cmd + "\n").encode("ascii"))
                    return True
                except serial.SerialException:
                    pass
        return False

    def run(self):
        buf = b""
        while True:
            port = self.port or find_port()
            if not port:
                self.q.put(("status", "マイコンが見つかりません（USB を挿してください）"))
                time.sleep(2)
                continue
            try:
                s = serial.Serial()
                s.port, s.baudrate, s.timeout = port, BAUD, 0.1
                s.dtr = False
                s.rts = False
                s.open()
            except serial.SerialException as e:
                self.q.put(("status", f"{port} を開けません：{e}"))
                time.sleep(2)
                continue
            with self.lock:
                self.ser = s
            self.q.put(("status", f"{port} に接続中"))
            try:
                while True:
                    b = s.read(1024)
                    if not b:
                        continue
                    buf += b
                    while b"\n" in buf:
                        line, buf = buf.split(b"\n", 1)
                        self.q.put(("line", line.decode("utf-8", "replace").rstrip("\r")))
            except (serial.SerialException, OSError):
                self.q.put(("status", f"{port} が切れました。つなぎ直します…"))
            with self.lock:
                self.ser = None
            try:
                s.close()
            except Exception:
                pass
            time.sleep(2)


class App:
    def __init__(self, root, port):
        self.root = root
        self.q = queue.Queue()
        self.reader = Reader(port, q=self.q)
        self.counts = {v: 0 for v in VALUES}
        self.total = 0
        self.expect = tk.IntVar(value=0)       # 0 = 指定なし
        self.tally = {}                        # 入れた硬貨 → [正解, 回数]
        self.sensortest = False
        LOG_DIR.mkdir(exist_ok=True)
        self.logf = open(LOG_DIR / f"{datetime.now():%Y%m%d_%H%M%S}.log", "a", encoding="utf-8")

        root.title("貯金箱モニター")
        root.geometry("980x760")
        root.configure(bg="white")
        big = ("Meiryo", 120, "bold")
        mid = ("Meiryo", 16)
        small = ("Meiryo", 11)

        top = tk.Frame(root, bg="white")
        top.pack(fill="x", padx=12, pady=(10, 0))
        self.status = tk.Label(top, text="起動中…", font=small, bg="white", fg="#555")
        self.status.pack(side="left")
        tk.Button(top, text="数をリセット", font=small, command=self.reset).pack(side="right", padx=4)
        self.st_btn = tk.Button(top, text="センサー試験 ON", font=small, command=self.toggle_sensortest)
        self.st_btn.pack(side="right", padx=4)
        for v in ["sim 1", "sim 100", "sim 500"]:
            tk.Button(top, text=v, font=small, command=lambda c=v: self.reader.send(c)).pack(side="right", padx=2)

        # 入れる硬貨（正解）
        ex = tk.Frame(root, bg="white")
        ex.pack(fill="x", padx=12, pady=(6, 0))
        tk.Label(ex, text="入れる硬貨：", font=mid, bg="white").pack(side="left")
        for v in [0] + VALUES:
            tk.Radiobutton(ex, text="指定なし" if v == 0 else f"{v}円", value=v, variable=self.expect,
                           font=mid, bg="white", command=self.refresh_tally).pack(side="left", padx=2)

        # 大きな表示
        self.big = tk.Label(root, text="—", font=big, bg="white", fg="#bbb")
        self.big.pack(pady=(4, 0))
        self.detail = tk.Label(root, text="硬貨を入れてください", font=mid, bg="white", fg="#555")
        self.detail.pack()

        # ビームのランプ
        bf = tk.Frame(root, bg="white")
        bf.pack(pady=(8, 0))
        tk.Label(bf, text="ビーム：", font=small, bg="white").pack(side="left")
        self.lamps = {}
        for b in BEAMS:
            l = tk.Label(bf, text=b, font=("Meiryo", 14, "bold"), width=5, bg="#e8f5e9", relief="ridge")
            l.pack(side="left", padx=3)
            self.lamps[b] = l
        self.lamp_note = tk.Label(bf, text="（ランプはセンサー試験中だけ動く）", font=small, bg="white", fg="#888")
        self.lamp_note.pack(side="left", padx=8)

        # 回数と正解率
        self.count_lbl = tk.Label(root, font=mid, bg="white")
        self.count_lbl.pack(pady=(8, 0))
        self.tally_lbl = tk.Label(root, font=mid, bg="white", fg="#1a5")
        self.tally_lbl.pack()

        # 履歴と生ログ
        pan = tk.Frame(root, bg="white")
        pan.pack(fill="both", expand=True, padx=12, pady=8)
        self.hist = tk.Listbox(pan, font=("Meiryo", 12), width=34)
        self.hist.pack(side="left", fill="y")
        self.raw = tk.Text(pan, font=("Consolas", 10), bg="#fafafa")
        self.raw.pack(side="left", fill="both", expand=True, padx=(8, 0))

        self.refresh_counts()
        self.refresh_tally()
        self.reader.start()
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.after(50, self.poll)

    # ---- ボタン ----------------------------------------------------------
    def toggle_sensortest(self):
        if self.reader.send("exit" if self.sensortest else "sensortest"):
            self.set_sensortest(not self.sensortest)

    def set_sensortest(self, on):
        self.sensortest = on
        self.st_btn.config(text="センサー試験 OFF" if on else "センサー試験 ON",
                           bg="#ffe0b2" if on else "SystemButtonFace")
        self.lamp_note.config(text="センサー試験中：さえぎると赤（音は鳴らない）" if on
                              else "（ランプはセンサー試験中だけ動く）")
        if not on:
            for l in self.lamps.values():
                l.config(bg="#e8f5e9")

    def reset(self):
        self.counts = {v: 0 for v in VALUES}
        self.total = 0
        self.tally = {}
        self.hist.delete(0, "end")
        self.reader.send("reset")
        self.big.config(text="—", fg="#bbb")
        self.detail.config(text="硬貨を入れてください")
        self.refresh_counts()
        self.refresh_tally()

    def close(self):
        if self.sensortest:
            self.reader.send("exit")
        self.logf.close()
        self.root.destroy()

    # ---- 表示 ------------------------------------------------------------
    def refresh_counts(self):
        s = "　".join(f"{v}円 {self.counts[v]}" for v in VALUES)
        self.count_lbl.config(text=f"{s}　｜　合計 {self.total} 枚")

    def refresh_tally(self):
        parts = []
        for v in VALUES:
            if v in self.tally:
                ok, n = self.tally[v]
                parts.append(f"{v}円 {ok}/{n}（{ok * 100 // n}%）")
        self.tally_lbl.config(text="正解率：" + "　".join(parts) if parts
                              else "「入れる硬貨」を選ぶと正解率を数えます")

    def flash(self, beam, ms=250):
        l = self.lamps[beam]
        l.config(bg="#ef5350")
        self.root.after(ms, lambda: l.config(bg="#e8f5e9"))

    def on_coin(self, m):
        value, stage, hole, v, dt, flags, action = m.groups()
        value = int(value)
        flags = flags.split()
        how = {"timeout": "", "adopted": "途中から拾った", "forced": "あふれて決めた"}
        note = "・".join(how[f] for f in flags if how.get(f))
        self.total += 1
        if value in self.counts:
            self.counts[value] += 1
        exp = self.expect.get()
        mark = ""
        if exp:
            ok, n = self.tally.get(exp, [0, 0])
            hit = value == exp
            self.tally[exp] = [ok + hit, n + 1]
            mark = "○ " if hit else f"× （正解 {exp}円）"
        self.big.config(text=f"{value}円", fg=COLOR.get(value, "#333"))
        if exp and value != exp:
            self.big.config(fg="#d32f2f")
        self.detail.config(text=f"段 {stage}・穴{'あり' if hole == '1' else 'なし'}・速さ {v}mm/s・"
                                f"{dt}ms で決定　{note}　→ {action}")
        t = datetime.now().strftime("%H:%M:%S")
        self.hist.insert(0, f"{t}  {value:>3}円  {mark}{note}")
        if mark.startswith("×"):
            self.hist.itemconfig(0, fg="#d32f2f")
        self.refresh_counts()
        self.refresh_tally()

    def on_line(self, line):
        self.logf.write(f"{datetime.now():%H:%M:%S.%f}"[:-3] + "  " + line + "\n")
        self.logf.flush()
        self.raw.insert("end", line + "\n")
        if int(self.raw.index("end-1c").split(".")[0]) > 600:
            self.raw.delete("1.0", "200.0")
        self.raw.see("end")

        m = RE_COIN.search(line)
        if m:
            self.on_coin(m)
            return
        if "sensortest: ON" in line:
            self.set_sensortest(True)
        elif "sensortest: OFF" in line or "coin-bank v3.0 boot" in line:
            self.set_sensortest(False)
        m = RE_LEVELS.search(line)
        if m and self.sensortest:
            for b, lv in zip(BEAMS, m.groups()):
                self.lamps[b].config(bg="#ef5350" if lv == "1" else "#e8f5e9")
        m = RE_PULSE.search(line)
        if m and self.sensortest:
            self.flash(m.group(1))
            self.detail.config(text=f"{m.group(1)} をさえぎった（{m.group(2)}ms）")
        m = RE_JAM.search(line)
        if m and not self.sensortest:
            self.lamps[m.group(1)].config(bg="#ffb300" if m.group(2) == "JAM?" else "#e8f5e9")

    def poll(self):
        try:
            while True:
                kind, val = self.q.get_nowait()
                if kind == "line":
                    self.on_line(val)
                else:
                    self.status.config(text=val)
        except queue.Empty:
            pass
        self.root.after(50, self.poll)


def main():
    port = sys.argv[1] if len(sys.argv) > 1 else None
    root = tk.Tk()
    App(root, port)
    root.mainloop()


if __name__ == "__main__":
    main()
