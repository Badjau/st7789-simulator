"""Live Windows preview. Counts key-down activity; never stores typed text."""
import collections
import ctypes
from ctypes import wintypes
import pathlib
import os
import queue
import subprocess
import sys
import threading
import time
# Some portable Windows Python installations do not discover their Tcl files.
_tcl_root = pathlib.Path(sys.base_prefix) / "tcl"
for _name, _folder in (("TCL_LIBRARY", "tcl8.6"), ("TK_LIBRARY", "tk8.6")):
    if (_tcl_root / _folder).is_dir():
        os.environ.setdefault(_name, str(_tcl_root / _folder))
import tkinter as tk
from tkinter import ttk
from zmk_serial import SerialSource

WIDTH, HEIGHT = 240, 280
FRAME_BYTES = WIDTH * HEIGHT * 3
WINDOW_SECONDS = 10

class KeyboardActivity:
    def __init__(self):
        self.events = collections.deque()
        self.lock = threading.Lock()
        self.status = "Starting keyboard listener..."
        self.thread_id = None
        self.thread = threading.Thread(target=self._listen, daemon=True)
        self.thread.start()

    def _listen(self):
        if sys.platform != "win32":
            self.status = "Global keyboard listening requires Windows."
            return
        user = ctypes.WinDLL("user32", use_last_error=True)
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        result = ctypes.c_ssize_t
        callback_type = ctypes.WINFUNCTYPE(result, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
        class KeyEvent(ctypes.Structure):
            _fields_ = [("vkCode", wintypes.DWORD), ("scanCode", wintypes.DWORD),
                        ("flags", wintypes.DWORD), ("time", wintypes.DWORD),
                        ("extra", ctypes.c_size_t)]
        user.SetWindowsHookExW.argtypes = [ctypes.c_int, callback_type, wintypes.HINSTANCE, wintypes.DWORD]
        user.SetWindowsHookExW.restype = wintypes.HANDLE
        user.CallNextHookEx.argtypes = [wintypes.HANDLE, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
        user.CallNextHookEx.restype = result
        user.UnhookWindowsHookEx.argtypes = [wintypes.HANDLE]
        user.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
        user.GetMessageW.restype = ctypes.c_int
        kernel.GetCurrentThreadId.restype = wintypes.DWORD
        self.thread_id = kernel.GetCurrentThreadId()
        @callback_type
        def on_key(code, message, data):
            if code >= 0 and message in (0x0100, 0x0104):  # WM_KEYDOWN / WM_SYSKEYDOWN
                vk = ctypes.cast(data, ctypes.POINTER(KeyEvent)).contents.vkCode
                # Count normal text-producing keys only; never retain key identities.
                if vk == 0x20 or 0x30 <= vk <= 0x5A or 0x60 <= vk <= 0x6F or 0xBA <= vk <= 0xE2:
                    with self.lock:
                        self.events.append(time.monotonic())
            return user.CallNextHookEx(None, code, message, data)
        hook = user.SetWindowsHookExW(13, on_key, None, 0)  # WH_KEYBOARD_LL
        if not hook:
            self.status = f"Keyboard listener failed (Windows error {ctypes.get_last_error()})."
            return
        self.status = "Listening for typing activity across Windows"
        msg = wintypes.MSG()
        while user.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user.TranslateMessage(ctypes.byref(msg))
            user.DispatchMessageW(ctypes.byref(msg))
        user.UnhookWindowsHookEx(hook)

    def wpm(self):
        now = time.monotonic()
        with self.lock:
            while self.events and self.events[0] <= now - WINDOW_SECONDS:
                self.events.popleft()
            return min(999, round(len(self.events) * 60 / WINDOW_SECONDS / 5))

    def stop(self):
        if self.thread_id and sys.platform == "win32":
            ctypes.windll.user32.PostThreadMessageW(self.thread_id, 0x0012, 0, 0)

class Renderer:
    def __init__(self, exe):
        self.requests = queue.Queue(maxsize=1)
        self.frames = queue.Queue(maxsize=1)
        self.error = None
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        self.proc = subprocess.Popen([str(exe), "--live"], stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                     creationflags=flags)
        threading.Thread(target=self._run, daemon=True).start()

    def request(self, state):
        try:
            self.requests.put_nowait(state)
        except queue.Full:
            pass

    def _run(self):
        try:
            while True:
                state = self.requests.get()
                self.proc.stdin.write((state + "\n").encode("ascii"))
                self.proc.stdin.flush()
                frame = bytearray()
                while len(frame) < FRAME_BYTES:
                    part = self.proc.stdout.read(FRAME_BYTES - len(frame))
                    if not part:
                        raise RuntimeError("LVGL renderer exited")
                    frame.extend(part)
                try:
                    self.frames.get_nowait()
                except queue.Empty:
                    pass
                self.frames.put_nowait(bytes(frame))
        except (OSError, ValueError, RuntimeError) as exc:
            self.error = str(exc)

    def close(self):
        self.proc.terminate()
        try:
            self.proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            self.proc.kill()

class App:
    def __init__(self, root, exe):
        self.root = root
        root.title("Keyboard dashboard simulator")
        self.activity = KeyboardActivity()
        self.renderer = Renderer(exe)
        self.serial = SerialSource()
        self.live_mode = False
        self.image_label = tk.Label(root, bg="#111519", bd=0)
        self.image_label.grid(row=0, column=0, rowspan=8, padx=16, pady=16)
        controls = ttk.Frame(root, padding=12)
        controls.grid(row=0, column=1, sticky="n")
        ttk.Label(controls, text="Simulated keyboard state", font=("Segoe UI", 12, "bold")).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 12))
        self.layer = tk.StringVar(value="BASE")
        self.output = tk.StringVar(value="Bluetooth")
        self.connected = tk.BooleanVar(value=True)
        self.profile = tk.IntVar(value=1)
        ttk.Label(controls, text="Layer").grid(row=1, column=0, sticky="w")
        self.layer_control = ttk.Combobox(controls, textvariable=self.layer, values=("BASE", "NAVIGATION", "SYMBOLS", "FUNCTION"), state="readonly", width=15)
        self.layer_control.grid(row=1, column=1, pady=6)
        ttk.Label(controls, text="Host output").grid(row=3, column=0, sticky="w")
        ttk.Combobox(controls, textvariable=self.output, values=("Bluetooth", "USB", "Unavailable"), state="readonly", width=15).grid(row=3, column=1, pady=6)
        ttk.Checkbutton(controls, text="Host connected", variable=self.connected).grid(row=4, column=0, columnspan=2, sticky="w", pady=6)
        ttk.Label(controls, text="BT profile").grid(row=5, column=0, sticky="w")
        ttk.Spinbox(controls, from_=1, to=5, textvariable=self.profile, width=8).grid(row=5, column=1, sticky="w", pady=6)
        self.wpm_text = tk.StringVar()
        ttk.Label(controls, textvariable=self.wpm_text).grid(row=6, column=0, columnspan=2, sticky="w", pady=(14, 6))
        self.status = tk.StringVar()
        ttk.Label(controls, textvariable=self.status, wraplength=220).grid(row=7, column=0, columnspan=2, sticky="w")
        ttk.Label(controls, text="Manual WPM is an estimate.\nNo typed text or logs are saved.", wraplength=220).grid(row=8, column=0, columnspan=2, sticky="w", pady=(10, 0))
        serial_box = ttk.LabelFrame(controls, text="USB debug source", padding=8)
        serial_box.grid(row=9, column=0, columnspan=2, sticky="ew", pady=(12,0))
        self.port = tk.StringVar(value="COM3")
        ttk.Entry(serial_box, textvariable=self.port, width=10).grid(row=0, column=0, padx=(0,4))
        ttk.Button(serial_box, text="Connect", command=self.connect_serial).grid(row=0, column=1)
        ttk.Button(serial_box, text="Use manual", command=self.use_manual).grid(row=1, column=0, columnspan=2, sticky="w", pady=(5,0))
        self.serial_status = tk.StringVar(value="Manual mode")
        ttk.Label(serial_box, textvariable=self.serial_status, wraplength=220).grid(row=2, column=0, columnspan=2, sticky="w", pady=(5,0))
        ttk.Label(serial_box, text="Layer: observed transitions only.\nModifiers: left C S A G; N/A until seen.", wraplength=220).grid(row=3, column=0, columnspan=2, sticky="w", pady=(5,0))
        split_controls = ttk.Frame(root, padding=12)
        split_controls.grid(row=0, column=2, sticky="n")
        ttk.Label(split_controls, text="Simulated keyboard halves", font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=(0, 10))
        self.halves = []
        for name, level in (("Left half", 82), ("Right half", 67)):
            box = ttk.LabelFrame(split_controls, text=name, padding=8)
            box.pack(fill="x", pady=(0, 10))
            link = tk.StringVar(value="Connected")
            battery = tk.IntVar(value=level)
            available = tk.BooleanVar(value=True)
            charge = tk.StringVar(value="Unknown")
            ttk.Label(box, text="Connection").grid(row=0, column=0, sticky="w")
            ttk.Combobox(box, textvariable=link, values=("Connected", "Disconnected", "Unknown"), state="readonly", width=14).grid(row=0, column=1, pady=3)
            ttk.Label(box, text="Battery %").grid(row=1, column=0, sticky="w")
            ttk.Spinbox(box, from_=0, to=100, textvariable=battery, width=8).grid(row=1, column=1, sticky="w", pady=3)
            ttk.Checkbutton(box, text="Battery available", variable=available).grid(row=2, column=0, columnspan=2, sticky="w")
            ttk.Label(box, text="Charging").grid(row=3, column=0, sticky="w")
            ttk.Combobox(box, textvariable=charge, values=("Unknown", "Charging", "Not charging"), state="readonly", width=14).grid(row=3, column=1, pady=3)
            self.halves.append((link, battery, available, charge))
        ttk.Label(split_controls, text="Half state is simulated.\nFirmware forwarding is not verified.", wraplength=220).pack(anchor="w")
        root.protocol("WM_DELETE_WINDOW", self.close)
        self.refresh()

    def connect_serial(self):
        port = self.port.get().strip()
        if not port:
            self.serial_status.set("Enter a COM port.")
            return
        if self.serial.connect(port):
            self.live_mode = True
            self.layer_control.configure(state="disabled")

    def use_manual(self):
        if self.serial.disconnect():
            self.live_mode = False
            self.layer_control.configure(state="readonly")

    def refresh(self):
        try:
            profile = max(1, min(5, self.profile.get()))
        except (tk.TclError, ValueError):
            profile = -1
        connected, serial_status, (layer, live_wpm, modifiers) = self.serial.snapshot()
        if self.live_mode:
            speed = live_wpm if connected and live_wpm is not None else -1
            layer_name = f"L{layer}" if connected and layer is not None else "UNKNOWN"
            modifiers = modifiers if connected and modifiers is not None else -1
            self.wpm_text.set(f"ZMK WPM: {speed}" if speed >= 0 else "ZMK WPM: unknown")
            self.serial_status.set(serial_status)
        else:
            speed = self.activity.wpm()
            layer_name = self.layer.get()
            modifiers = -1
            self.wpm_text.set(f"Estimated WPM: {speed}")
            self.serial_status.set("Manual mode")
        self.status.set(self.renderer.error or self.activity.status)
        output = {"Unavailable": 0, "USB": 1, "Bluetooth": 2}[self.output.get()]
        half_values = []
        for link, battery, available, charge in self.halves:
            try:
                level = max(0, min(100, battery.get())) if available.get() else -1
            except (tk.TclError, ValueError):
                level = -1
            half_values.extend(({"Unknown": 0, "Disconnected": 1, "Connected": 2}[link.get()],
                                level, {"Unknown": 0, "Not charging": 1, "Charging": 2}[charge.get()]))
        half_state = " ".join(map(str, half_values))
        self.renderer.request(f"{layer_name} -1 {output} {int(self.connected.get())} {profile} {speed} {half_state} {modifiers} {int(self.live_mode)}")
        try:
            frame = self.renderer.frames.get_nowait()
            ppm = f"P6\n{WIDTH} {HEIGHT}\n255\n".encode() + frame
            image = tk.PhotoImage(data=ppm, format="PPM")
            self.photo = image.zoom(2, 2)
            self.image_label.configure(image=self.photo)
        except queue.Empty:
            pass
        self.root.after(250, self.refresh)

    def close(self):
        self.serial.disconnect()
        self.activity.stop()
        self.renderer.close()
        self.root.destroy()

if __name__ == "__main__":
    default_exe = pathlib.Path(__file__).resolve().parent.parent / "build" / "simulator" / "dashboard_sim.exe"
    exe = pathlib.Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else default_exe
    if not exe.exists():
        raise SystemExit(f"Simulator executable not found: {exe}. Build it using the README first.")
    app_root = tk.Tk()
    App(app_root, exe)
    app_root.after(100, lambda: app_root.state("normal"))
    app_root.mainloop()
