"""In-memory ZMK v0.3 USB debug parser and optional serial source."""
import re
import threading

_ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
_LAYER = re.compile(r"\blayer_changed: layer (\d+) state ([01])(?:\s|$)")
_WPM = re.compile(r"\bRaised WPM state changed (\d+) wpm_update_counter (\d+)(?:\s|$)")
_MODIFIERS = re.compile(r"\bModifiers set to 0x([0-9a-fA-F]{1,2})(?:\s|$)")

class ZmkState:
    """Tracks observed transitions; no initial layer snapshot exists in the logs."""
    def __init__(self):
        self.reset()

    def reset(self):
        self.active_layers = set()
        self.wpm = None
        self.modifiers = None

    def feed(self, line):
        line = _ANSI.sub("", line)
        match = _LAYER.search(line)
        if match:
            layer, active = map(int, match.groups())
            if not 0 <= layer <= 255:
                return
            if active:
                self.active_layers.add(layer)
            else:
                self.active_layers.discard(layer)
            return
        match = _WPM.search(line)
        if match:
            value, counter = map(int, match.groups())
            if 0 <= value <= 255 and 1 <= counter <= 5:
                self.wpm = value
            return
        match = _MODIFIERS.search(line)
        if match:
            self.modifiers = int(match.group(1), 16)

    def snapshot(self):
        return (max(self.active_layers) if self.active_layers else None,
                self.wpm, self.modifiers)

class SerialSource:
    def __init__(self, serial_factory=None):
        self.lock = threading.Lock()
        self.state = ZmkState()
        self.status = "Manual mode"
        self.connected = False
        self.stop_event = threading.Event()
        self.thread = None
        self.serial_factory = serial_factory

    def connect(self, port):
        if not self.disconnect():
            return False
        with self.lock:
            self.state.reset()
            self.status = f"Connecting to {port}..."
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._run, args=(port,), daemon=True)
        self.thread.start()
        return True

    def _run(self, port):
        device = None
        try:
            if self.serial_factory is None:
                import serial
                device = serial.Serial(port=port, baudrate=115200, timeout=0.2)
            else:
                device = self.serial_factory(port=port, baudrate=115200, timeout=0.2)
            with self.lock:
                self.connected = True
                self.status = f"Connected to {port} (115200 baud)"
            # Buffer only one bounded line, discarding oversized lines entirely.
            buf = bytearray()
            discard = False
            while not self.stop_event.is_set():
                chunk = device.read(256)
                for byte in chunk:
                    if byte == 10:
                        if not discard and buf:
                            line = buf.decode("ascii", "replace")
                            with self.lock:
                                self.state.feed(line)
                        buf.clear()
                        discard = False
                    elif not discard:
                        if len(buf) < 512:
                            buf.append(byte)
                        else:
                            buf.clear()
                            discard = True
        except Exception as exc:
            with self.lock:
                self.status = f"Serial error: {exc}. Check port and close other serial monitors."
        finally:
            if device is not None:
                try:
                    device.close()
                except Exception:
                    pass
            with self.lock:
                self.connected = False
                self.state.reset()
                if self.stop_event.is_set():
                    self.status = "Disconnected"

    def snapshot(self):
        with self.lock:
            return self.connected, self.status, self.state.snapshot()

    def disconnect(self):
        self.stop_event.set()
        if self.thread is not None:
            self.thread.join(timeout=1)
            if self.thread.is_alive():
                # Do not start another reader until an opening operation has returned.
                with self.lock:
                    self.status = "Waiting for serial port to close"
                return False
            self.thread = None
        with self.lock:
            self.connected = False
            self.state.reset()
            self.status = "Disconnected"
        return True
