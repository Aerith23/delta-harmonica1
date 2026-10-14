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
from transcription import convert_recording, ConversionCancelled

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
        self.title("口琴助手 · 录音与转谱")
        self.geometry("1120x760")
        self.minsize(1060, 730)
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
        self.converting = False
        self.conversion_thread = None
        self.conversion_cancel = threading.Event()
        self.score_folder = ROOT / "曲库" / "曲谱"
        self.last_score = None
        self.mode_var = tk.StringVar(value="单音简化")
        self.conversion_text = tk.StringVar(value="选择下方已录制文件，转换为兼容曲库的 JSON。")
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
        self.label(head, "系统录音   /   自动跳过开头静音   /   本地音频转谱", 10, MUTED).pack(anchor="w")

        body = tk.Frame(main, bg=BG)
        body.pack(fill="both", expand=True, pady=(10, 0))
        left = tk.Frame(body, bg=BG, width=460)
        left.pack(side="left", fill="y", padx=(0, 20))
        left.pack_propagate(False)
        right = tk.Frame(body, bg=BG)
        right.pack(side="left", fill="both", expand=True)

        settings = tk.Frame(left, bg=BG)
        settings.pack(fill="x", pady=(20, 14))
        self.label(settings, "录音来源", 10, MUTED).grid(row=0, column=0, sticky="w", pady=(0, 5))
        self.combo = ttk.Combobox(settings, textvariable=self.device_var, state="readonly", font=(FONT, 10))
        self.combo.grid(row=1, column=0, sticky="ew", padx=(0, 10))
        self.refresh_btn = self.button(settings, "刷新设备", self.refresh_devices)
        self.refresh_btn.grid(row=1, column=1)
        settings.columnconfigure(0, weight=1)

        card = tk.Frame(left, bg=PANEL, padx=24, pady=18)
        card.pack(fill="x")
        top = tk.Frame(card, bg=PANEL)
        top.pack(fill="x")
        self.label(top, textvariable=self.status_text, size=13, color=ACCENT).pack(side="left")
        self.label(top, "WASAPI  ·  系统输出", 9, MUTED).pack(side="right")
        self.timer = self.label(card, "00:00", 36)
        self.timer.pack(pady=(3, 0))
        self.stats = self.label(card, "录制时长 · 等待声音时不计时", 9, MUTED)
        self.stats.pack()
        self.meter = tk.Canvas(card, bg=PANEL, height=42, highlightthickness=0)
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
                   wraplength=410).pack()

        gate = tk.Frame(left, bg=BG)
        gate.pack(fill="x", pady=(12, 8))
        self.label(gate, "起录灵敏度", 10).pack(side="left")
        self.scale = tk.Scale(gate, from_=-80, to=-25, resolution=1, orient="horizontal",
                             variable=self.threshold, showvalue=False, bg=BG, fg=TEXT,
                             troughcolor="#29374a", activebackground=ACCENT,
                             highlightthickness=0, bd=0, length=170,
                             command=lambda v: self.threshold_text.set(f"{int(float(v))} dBFS"))
        self.scale.pack(side="left", padx=12)
        self.label(gate, textvariable=self.threshold_text, size=9, color=ACCENT).pack(side="left")
        self.label(gate, "数值越低，越容易触发。", 9, MUTED).pack(side="right")

        dest = tk.Frame(left, bg=BG)
        dest.pack(fill="x", pady=(0, 10))
        self.label(dest, "保存至", 9, MUTED).pack(side="left", padx=(0, 8))
        self.path_entry = tk.Entry(dest, textvariable=self.path_text, state="readonly", readonlybackground=BG,
                                   fg=MUTED, relief="flat", font=(FONT, 9))
        self.path_entry.pack(side="left", fill="x", expand=True)
        self.folder_btn = self.button(dest, "更改", self.choose_folder)
        self.folder_btn.pack(side="right")

        row = tk.Frame(right, bg=BG)
        row.pack(fill="x", pady=(0, 8))
        self.label(row, "已录制文件", 12).pack(side="left")
        self.preview_btn = self.button(row, "试听 / 停止", self.preview)
        self.preview_btn.pack(side="right", padx=(6, 0))
        self.open_btn = self.button(row, "打开保存目录", self.open_folder)
        self.open_btn.pack(side="right")
        self.list_refresh_btn = self.button(row, "刷新列表", self._refresh_files)
        self.list_refresh_btn.pack(side="right", padx=(0, 6))
        self.file_status = tk.StringVar()
        self.label(right, textvariable=self.file_status, size=9, color=MUTED,
                   wraplength=540, justify="left").pack(anchor="w", pady=(0, 8))
        list_area = tk.Frame(right, bg=BG)
        list_area.pack(fill="both", expand=True)
        self.table = ttk.Treeview(list_area, columns=("name", "duration", "size"), show="headings", selectmode="browse", height=4)
        self.table.heading("name", text="文件名")
        self.table.heading("size", text="大小")
        self.table.heading("duration", text="时长")
        self.table.column("duration", width=80, anchor="center")
        self.table.column("name", width=310)
        self.table.column("size", width=85, anchor="e")
        self.table.pack(side="left", fill="both", expand=True)
        scrollbar = ttk.Scrollbar(list_area, orient="vertical", command=self.table.yview)
        scrollbar.pack(side="right", fill="y")
        self.table.configure(yscrollcommand=scrollbar.set)
        conversion = tk.Frame(right, bg=PANEL, padx=14, pady=10)
        conversion.pack(fill="x", pady=(10, 0))
        actions = tk.Frame(conversion, bg=PANEL)
        actions.pack(fill="x")
        self.label(actions, "转谱方式", 9, MUTED).pack(side="left", padx=(0, 8))
        self.mode_combo = ttk.Combobox(actions, textvariable=self.mode_var, values=["单音简化", "保留所有音符"],
                                       state="readonly", width=14, font=(FONT, 9))
        self.mode_combo.pack(side="left")
        buttons = tk.Frame(conversion, bg=PANEL)
        buttons.pack(fill="x", pady=(7, 0))
        self.convert_btn = self.button(buttons, "转换为 JSON", self.convert_selected, True)
        self.convert_btn.pack(side="left", padx=(0, 8))
        self.cancel_btn = self.button(buttons, "取消转换", self.cancel_conversion)
        self.cancel_btn.pack(side="left")
        self.cancel_btn.configure(state="disabled")
        self.result_btn = self.button(actions, "查看生成曲谱", self.open_result)
        self.result_btn.pack(side="right")
        self.result_btn.configure(state="disabled")
        self.progress = ttk.Progressbar(conversion, maximum=100)
        self.progress.pack(fill="x", pady=(8, 4))
        self.label(conversion, textvariable=self.conversion_text, size=9, color=MUTED,
                   wraplength=440, justify="left").pack(anchor="w")
        self.label(conversion, "独奏和清晰器乐效果更好；混音可能包含错音。\n单音简化不等同于人声分离。",
                   9, MUTED, justify="left").pack(anchor="w", pady=(3, 0))
        self.table.bind("<Double-1>", lambda e: self.preview())
        self.label(main, "仅捕获所选设备的电脑输出声音，不使用麦克风。录音完全保存在本机。", 9, MUTED).pack(anchor="w", pady=(9, 0))
        self.previewing = False

    def refresh_devices(self):
        if self.session_open or self.loading or self.converting:
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
        for widget in (self.refresh_btn, self.folder_btn, self.scale, self.preview_btn, self.convert_btn, self.list_refresh_btn):
            widget.configure(state="disabled" if busy else "normal")
        self.mode_combo.configure(state="disabled" if busy else "readonly")

    def start(self):
        if self.session_open or self.loading or self.recorder.busy or self.converting:
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
        if self.session_open or self.converting:
            return
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
        self.file_status.set(f"{len(self.files)} 个已录制文件 · {self.folder}" if self.files else
                             f"当前目录没有 WAV 录音 · {self.folder}；可更改保存目录或开始录制。")
        for i, (path, stat) in enumerate(entries):
            self.table.insert("", "end", iid=str(i), values=(path.name, self._wav_duration(path), f"{stat.st_size / 1048576:.2f} MB"))
            if str(path) == select:
                self.table.selection_set(str(i))
                self.table.see(str(i))

    def preview(self):
        if self.session_open or self.converting:
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

    @staticmethod
    def _wav_duration(path):
        import wave
        try:
            with wave.open(str(path)) as wav:
                return clock(wav.getnframes() / wav.getframerate())
        except (OSError, wave.Error, EOFError):
            return "—"

    def convert_selected(self):
        if self.session_open or self.converting or self.closing:
            return
        selected = self.table.selection()
        if not selected:
            messagebox.showinfo("请选择录音", "先在已录制文件列表中选择一个 WAV 文件。")
            return
        source = self.files[int(selected[0])]
        monophonic = self.mode_var.get() == "单音简化"
        winsound.PlaySound(None, 0)
        self.previewing = False
        self.converting = True
        self.conversion_cancel.clear()
        self.progress["value"] = 0
        self.conversion_text.set("正在准备：" + source.name)
        self._set_busy(True)
        self.stop_btn.configure(state="disabled")
        self.cancel_btn.configure(state="normal")
        def work():
            try:
                result = convert_recording(source, self.score_folder, monophonic,
                    self.conversion_cancel,
                    lambda value, message: self.ui_events.put(("conversion_progress", (value, message))))
                self.ui_events.put(("conversion_finished", result))
            except ConversionCancelled:
                self.ui_events.put(("conversion_cancelled", None))
            except Exception as exc:
                self.ui_events.put(("conversion_error", str(exc)))
        self.conversion_thread = threading.Thread(target=work, name="audio-to-score", daemon=True)
        self.conversion_thread.start()

    def cancel_conversion(self):
        self.conversion_cancel.set()
        self.cancel_btn.configure(state="disabled")
        self.conversion_text.set("正在取消，等待当前识别步骤结束…")

    def open_result(self):
        if self.last_score and self.last_score.is_file():
            try:
                os.startfile(str(self.last_score))
            except OSError as exc:
                messagebox.showerror("无法打开曲谱", str(exc))

    def _handle_conversion_event(self, kind, value):
        if kind == "conversion_progress":
            if not self.conversion_cancel.is_set():
                self.progress["value"], message = value
                self.conversion_text.set(message)
            return
        self.converting = False
        self._set_busy(False)
        self.cancel_btn.configure(state="disabled")
        if kind == "conversion_finished":
            self.last_score = Path(value["path"])
            self.progress["value"] = 100
            self.result_btn.configure(state="normal")
            self.conversion_text.set(f"已生成 {value['notes']} 个音符 · {self.last_score}")
        elif kind == "conversion_cancelled":
            self.progress["value"] = 0
            self.conversion_text.set("转换已取消，原录音保留。")
        else:
            self.progress["value"] = 0
            self.conversion_text.set("转换失败：" + value)
            if not self.closing:
                messagebox.showerror("转谱失败", value)

    def tick(self):
        try:
            while True:
                kind, value = self.ui_events.get_nowait()
                if kind.startswith("conversion_"):
                    self._handle_conversion_event(kind, value)
                    continue
                self.loading = False
                self.refresh_btn.configure(state="normal")
                if kind == "devices":
                    self.devices = value
                    self.combo["values"] = [d.name + ("  · 系统默认" if d.default else "") for d in value]
                    if value:
                        self.combo.current(next((i for i, d in enumerate(value) if d.default), 0))
                        self.start_btn.configure(state="disabled" if self.converting or self.closing else "normal")
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
            height = max(2, level * 36)
            self.meter.create_rectangle(i * stride, 21 - height / 2, i * stride + max(1, stride - 2),
                                        21 + height / 2, fill=ACCENT if level else "#2a394b", outline="")
        if self.closing and not self.recorder.busy and not self.loading and not self.converting:
            self.destroy()
            return
        self.after(80, self.tick)

    def close(self):
        self.closing = True
        if self.converting:
            self.cancel_conversion()
        winsound.PlaySound(None, 0)
        self.stop()
        self.start_btn.configure(state="disabled")


if __name__ == "__main__":
    # Headless conversion is also useful for integration tests of the frozen EXE.
    if len(sys.argv) == 4 and sys.argv[1] == "--convert":
        try:
            convert_recording(sys.argv[2], sys.argv[3])
        except Exception:
            import traceback
            (ROOT / "transcription-error.log").write_text(traceback.format_exc(), encoding="utf-8")
            sys.exit(1)
        sys.exit(0)
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (AttributeError, OSError):
        pass
    App().mainloop()
