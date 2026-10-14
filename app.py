"""Harmonica Studio / a local-first system-audio recorder."""
from pathlib import Path
from collections import deque
import ctypes
import os
import queue
import sys
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import winsound

from recorder import Recorder, list_outputs

ROOT = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
BG = "#10151e"
PANEL = "#1a2230"
TEXT = "#ecf2f9"
MUTED = "#93a4b9"
ACCENT = "#67e8c0"
FONT = "Microsoft YaHei UI"


def clock(seconds):
    seconds = int(seconds)
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("口琴助手 · 系统录音")
        self.geometry("1040x790")
        self.minsize(900, 710)
        self.configure(bg=BG)
        self.recorder = Recorder()
        self.folder = ROOT / "recordings"
        self.devices = []
        self.files = []
        self.ui_events = queue.Queue()
        self.history = deque([0.0] * 130, maxlen=130)
        self.closing = False
        self.loading = False
        self.session_open = False
        self.last_state = None
        self.threshold = tk.DoubleVar(value=-60)
        self.device_var = tk.StringVar()
        self.threshold_text = tk.StringVar(value="−60 dBFS")
        self.path_text = tk.StringVar(value=str(self.folder))
        self.status_text = tk.StringVar(value="准备就绪")
        self.detail_text = tk.StringVar(value="先点击开始录制，再播放你想录下的音乐。")
        self._style()
        self._build()
        self._refresh_files()
        self.refresh_devices()
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.after(80, self.tick)

    def _style(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TCombobox", fieldbackground="#253145", background="#253145",
                        foreground=TEXT, arrowcolor=TEXT, borderwidth=0, padding=9)
        style.map("TCombobox", fieldbackground=[("readonly", "#253145")],
                  foreground=[("readonly", TEXT), ("disabled", MUTED)])
        style.configure("Treeview", background=PANEL, fieldbackground=PANEL,
                        foreground=TEXT, rowheight=34, borderwidth=0, font=(FONT, 10))
        style.configure("Treeview.Heading", background="#253145", foreground=MUTED,
                        font=(FONT, 9), relief="flat", padding=8)
        style.map("Treeview", background=[("selected", "#30485c")])
        self.option_add("*TCombobox*Listbox.background", PANEL)
        self.option_add("*TCombobox*Listbox.foreground", TEXT)
        self.option_add("*TCombobox*Listbox.font", (FONT, 10))

    def label(self, parent, text=None, size=10, color=TEXT, **kwargs):
        return tk.Label(parent, text=text, font=(FONT, size), fg=color,
                        bg=parent.cget("bg"), **kwargs)

    def button(self, parent, text, command, primary=False):
        return tk.Button(parent, text=text, command=command,
                         font=(FONT, 10, "bold"), relief="flat", bd=0,
                         bg=ACCENT if primary else "#29374a",
                         fg=BG if primary else TEXT,
                         activebackground="#a4f5dc" if primary else "#3a4b63",
                         activeforeground=BG if primary else TEXT,
                         disabledforeground="#607486", cursor="hand2",
                         padx=18, pady=10)

    def _build(self):
        main = tk.Frame(self, bg=BG)
        main.pack(fill="both", expand=True, padx=30, pady=22)
        head = tk.Frame(main, bg=BG)
        head.pack(fill="x")
        self.label(head, "HARMONICA  /  口琴助手", 10, ACCENT).pack(anchor="w")
        self.label(head, "把正在播放的声音，留成素材。", 23).pack(anchor="w", pady=(6, 3))
        self.label(head, "系统录音   /   自动跳过开头静音   /   本地 WAV", 10, MUTED).pack(anchor="w")

        settings = tk.Frame(main, bg=BG)
        settings.pack(fill="x", pady=(20, 14))
        self.label(settings, "录音来源", 10, MUTED).grid(row=0, column=0, sticky="w", pady=(0, 5))
        self.combo = ttk.Combobox(settings, textvariable=self.device_var, state="readonly", font=(FONT, 10))
        self.combo.grid(row=1, column=0, sticky="ew", padx=(0, 10))
        self.refresh_btn = self.button(settings, "刷新设备", self.refresh_devices)
        self.refresh_btn.grid(row=1, column=1)
        settings.columnconfigure(0, weight=1)

        card = tk.Frame(main, bg=PANEL, padx=24, pady=18)
        card.pack(fill="x")
        top = tk.Frame(card, bg=PANEL)
        top.pack(fill="x")
        self.label(top, textvariable=self.status_text, size=13, color=ACCENT).pack(side="left")
        self.label(top, "WASAPI  ·  系统输出", 9, MUTED).pack(side="right")
        self.timer = self.label(card, "00:00", 43)
        self.timer.pack(pady=(3, 0))
        self.stats = self.label(card, "录制时长 · 等待声音时不计时", 9, MUTED)
        self.stats.pack()
        self.meter = tk.Canvas(card, bg=PANEL, height=58, highlightthickness=0)
        self.meter.pack(fill="x", pady=(10, 3))
        self.level = self.label(card, "输入电平  —", 9, MUTED)
        self.level.pack()
        controls = tk.Frame(card, bg=PANEL)
        controls.pack(pady=(12, 8))
        self.start_btn = self.button(controls, "●  开始录制", self.start, True)
        self.start_btn.pack(side="left", padx=6)
        self.stop_btn = self.button(controls, "■  停止并保存", self.stop)
        self.stop_btn.pack(side="left", padx=6)
        self.stop_btn.configure(state="disabled")
        self.label(card, textvariable=self.detail_text, size=10, color=MUTED,
                   wraplength=810).pack()

        gate = tk.Frame(main, bg=BG)
        gate.pack(fill="x", pady=(12, 8))
        self.label(gate, "起录灵敏度", 10).pack(side="left")
        self.scale = tk.Scale(gate, from_=-80, to=-25, resolution=1, orient="horizontal",
                             variable=self.threshold, showvalue=False, bg=BG, fg=TEXT,
                             troughcolor="#29374a", activebackground=ACCENT,
                             highlightthickness=0, bd=0, length=170,
                             command=lambda v: self.threshold_text.set(f"{int(float(v))} dBFS"))
        self.scale.pack(side="left", padx=12)
        self.label(gate, textvariable=self.threshold_text, size=9, color=ACCENT).pack(side="left")
        self.label(gate, "数值越低，越容易触发；录制开始后保留全部停顿。", 9, MUTED).pack(side="right")

        dest = tk.Frame(main, bg=BG)
        dest.pack(fill="x", pady=(0, 10))
        self.label(dest, "保存至", 9, MUTED).pack(side="left", padx=(0, 8))
        self.path_entry = tk.Entry(dest, textvariable=self.path_text, state="readonly", readonlybackground=BG,
                                   fg=MUTED, relief="flat", font=(FONT, 9))
        self.path_entry.pack(side="left", fill="x", expand=True)
        self.folder_btn = self.button(dest, "更改", self.choose_folder)
        self.folder_btn.pack(side="right")

        row = tk.Frame(main, bg=BG)
        row.pack(fill="x", pady=(0, 8))
        self.label(row, "录音素材", 12).pack(side="left")
        self.preview_btn = self.button(row, "试听 / 停止", self.preview)
        self.preview_btn.pack(side="right", padx=(6, 0))
        self.open_btn = self.button(row, "打开保存目录", self.open_folder)
        self.open_btn.pack(side="right")
        self.table = ttk.Treeview(main, columns=("name", "size"), show="headings", selectmode="browse", height=3)
        self.table.heading("name", text="文件名")
        self.table.heading("size", text="大小")
        self.table.column("name", width=610)
        self.table.column("size", width=100, anchor="e")
        self.table.pack(fill="both", expand=True)
        self.table.bind("<Double-1>", lambda e: self.preview())
        self.label(main, "仅捕获所选设备的电脑输出声音，不使用麦克风。录音完全保存在本机。", 9, MUTED).pack(anchor="w", pady=(9, 0))
        self.previewing = False

    def refresh_devices(self):
        if self.session_open or self.loading:
            return
        self.loading = True
        self.refresh_btn.configure(state="disabled")
        self.start_btn.configure(state="disabled")
        self.device_var.set("正在查找扬声器和耳机…")
        def work():
            try:
                self.ui_events.put(("devices", list_outputs()))
            except Exception as exc:
                self.ui_events.put(("device_error", str(exc)))
        threading.Thread(target=work, daemon=True).start()

    def _set_busy(self, busy):
        self.start_btn.configure(state="disabled" if busy or not self.devices else "normal")
        self.stop_btn.configure(state="normal" if busy else "disabled")
        self.combo.configure(state="disabled" if busy else "readonly")
        for widget in (self.refresh_btn, self.folder_btn, self.scale, self.preview_btn):
            widget.configure(state="disabled" if busy else "normal")

    def start(self):
        if self.session_open or self.loading or self.recorder.busy:
            return
        index = self.combo.current()
        if not 0 <= index < len(self.devices):
            return
        winsound.PlaySound(None, 0)
        self.previewing = False
        self.history = deque([0.0] * 130, maxlen=130)
        self.session_open = True
        self._set_busy(True)
        self.last_state = None
        self.detail_text.set("正在打开输出设备…")
        self.recorder.start(self.devices[index], self.folder, self.threshold.get())

    def stop(self):
        if self.session_open:
            self.recorder.stop()
            self.stop_btn.configure(state="disabled")
            self.status_text.set("正在保存…")
            self.detail_text.set("正在结束录音并写入 WAV 文件。")

    def choose_folder(self):
        path = filedialog.askdirectory(title="选择录音保存目录", initialdir=str(self.folder if self.folder.exists() else ROOT))
        if path:
            self.folder = Path(path)
            self.path_text.set(path)
            self._refresh_files()

    def open_folder(self):
        try:
            self.folder.mkdir(parents=True, exist_ok=True)
            os.startfile(str(self.folder))
        except OSError as exc:
            messagebox.showerror("无法打开目录", str(exc))

    def _refresh_files(self, select=None):
        self.table.delete(*self.table.get_children())
        entries = []
        try:
            for path in self.folder.glob("*.wav"):
                if not path.name.endswith(".partial.wav"):
                    try:
                        entries.append((path, path.stat()))
                    except OSError:
                        continue
        except OSError:
            self.detail_text.set("无法读取录音列表，请选择可访问的保存目录。")
        entries.sort(key=lambda pair: pair[1].st_mtime, reverse=True)
        entries = entries[:100]
        self.files = [path for path, _ in entries]
        for i, (path, stat) in enumerate(entries):
            self.table.insert("", "end", iid=str(i), values=(path.name, f"{stat.st_size / 1048576:.2f} MB"))
            if str(path) == select:
                self.table.selection_set(str(i))
                self.table.see(str(i))

    def preview(self):
        if self.session_open:
            return
        if self.previewing:
            winsound.PlaySound(None, 0)
            self.previewing = False
            return
        selection = self.table.selection()
        if selection:
            try:
                winsound.PlaySound(str(self.files[int(selection[0])]), winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
                self.previewing = True
            except RuntimeError as exc:
                messagebox.showerror("试听失败", str(exc))

    def tick(self):
        try:
            while True:
                kind, value = self.ui_events.get_nowait()
                self.loading = False
                self.refresh_btn.configure(state="normal")
                if kind == "devices":
                    self.devices = value
                    self.combo["values"] = [d.name + ("  · 系统默认" if d.default else "") for d in value]
                    if value:
                        self.combo.current(next((i for i, d in enumerate(value) if d.default), 0))
                        self.start_btn.configure(state="normal")
                    else:
                        self.device_var.set("没有找到输出设备")
                        self.detail_text.set("请连接耳机或扬声器，再点击刷新设备。")
                else:
                    self.devices = []
                    self.device_var.set("设备初始化失败")
                    self.detail_text.set("请确认音频设备可用，并点击刷新设备重试。")
                    messagebox.showerror("设备初始化失败", value)
        except queue.Empty:
            pass
        try:
            while True:
                kind, result = self.recorder.events.get_nowait()
                if kind == "notice":
                    self.detail_text.set(result)
                    continue
                self.session_open = False
                self._set_busy(False)
                if result["path"]:
                    self.status_text.set("已保存录音")
                    self.detail_text.set(Path(result["path"]).name + " · 可在下方选择试听")
                    self._refresh_files(result["path"])
                else:
                    self.status_text.set("未生成录音")
                    self.detail_text.set("本次未检测到声音，没有创建空白文件。")
                if result["error"]:
                    self.status_text.set("录音已停止 · 发生错误")
                    self.detail_text.set("已录部分已保留。" if result["path"] else "请检查输出设备与保存目录后重试。")
                    if not self.closing:
                        messagebox.showerror("录音提示", result["error"])
        except queue.Empty:
            pass
        snap = self.recorder.snapshot()
        state = snap["state"]
        if self.session_open and state != self.last_state and self.stop_btn.cget("state") != "disabled":
            self.last_state = state
            self.status_text.set({"opening": "正在连接设备", "waiting": "等待声音 · 自动跳过静音",
                                  "recording": "● 正在录制", "idle": "正在保存…"}[state])
            self.detail_text.set("现在可以播放音乐；检测到声音后自动开始计时。" if state == "waiting"
                                 else "正在保存电脑声音，音乐中的停顿会完整保留。")
        self.timer.configure(text=clock(snap["seconds"]))
        self.stats.configure(text=f"已跳过开头等待 {clock(snap['skipped'])}   ·   {snap['bytes'] / 1048576:.2f} MB")
        db = snap["peak"]
        self.level.configure(text=f"输入峰值  {db:.0f} dBFS" if db > -96 else "输入电平  —")
        self.history.append(max(0, (db + 80) / 80))
        self.meter.delete("all")
        width = max(1, self.meter.winfo_width())
        stride = width / len(self.history)
        for i, level in enumerate(self.history):
            height = max(2, level * 48)
            self.meter.create_rectangle(i * stride, 29 - height / 2, i * stride + max(1, stride - 2),
                                        29 + height / 2, fill=ACCENT if level else "#2a394b", outline="")
        if self.closing and not self.recorder.busy and not self.loading:
            self.destroy()
            return
        self.after(80, self.tick)

    def close(self):
        self.closing = True
        winsound.PlaySound(None, 0)
        self.stop()
        self.start_btn.configure(state="disabled")


if __name__ == "__main__":
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError, OSError):
        pass
    App().mainloop()
