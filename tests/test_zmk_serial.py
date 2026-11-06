import pathlib
import queue
import sys
import time
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "simulator"))
from zmk_serial import ZmkState, SerialSource

class ParserTest(unittest.TestCase):
    def test_layer_transitions_noise_and_reset(self):
        state = ZmkState()
        for line in ["split_central_device_found: chatter", "layer_changed: layer 2 state 1",
                     "layer_changed: layer 1 state 1"]:
            state.feed(line)
        self.assertEqual(state.snapshot(), (2, None, None))
        state.feed("layer_changed: layer 2 state 0")
        self.assertEqual(state.snapshot()[0], 1)
        state.feed("layer_changed: layer 1 state 0")
        self.assertIsNone(state.snapshot()[0])
        state.feed("layer_changed: layer 0 state 9")
        state.feed("layer_changed: layer 999 state 1")
        self.assertIsNone(state.snapshot()[0])
        state.reset()
        self.assertEqual(state.snapshot(), (None, None, None))

    def test_ansi_colored_raven_messages(self):
        state = ZmkState()
        state.feed("\x1b[0;36m[00:01] zmk: layer_changed: layer 2 state 1\x1b[0m")
        state.feed("\x1b[0;36mRaised WPM state changed 21 wpm_update_counter 5\x1b[0m")
        state.feed("\x1b[0;36mModifiers set to 0x02\x1b[0m")
        self.assertEqual(state.snapshot(), (2, 21, 2))
        state.feed("layer_changed: layer 2 state 0\x1b[0m")
        state.feed("Modifiers set to 0x00\x1b[0m")
        self.assertEqual(state.snapshot(), (None, 21, 0))

    def test_wpm_and_modifier_masks(self):
        state = ZmkState()
        state.feed("[00:00] <dbg> zmk: wpm_work_handler: Raised WPM state changed 42 wpm_update_counter 2")
        for mask in (1, 2, 4, 8, 0):
            state.feed(f"<dbg> zmk: zmk_hid_foo: Modifiers set to 0x{mask:02x}")
            self.assertEqual(state.snapshot()[2], mask)
        state.feed("Modifiers set to 0xZZ")
        state.feed("Raised WPM state changed 9999 wpm_update_counter 1")
        state.feed("Raised WPM state changed 12 wpm_update_counter 0")
        self.assertEqual(state.snapshot(), (None, 42, 0))

class FakePort:
    def __init__(self, **kwargs):
        self.chunks = queue.Queue()
        self.closed = False
    def read(self, _):
        try:
            return self.chunks.get(timeout=.03)
        except queue.Empty:
            return b""
    def close(self):
        self.closed = True

def wait_for(predicate):
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        if predicate(): return True
        time.sleep(.01)
    return False

class SerialLifecycleTest(unittest.TestCase):
    def test_interleaved_partial_lines_and_disconnect_reconnect(self):
        ports = []
        def factory(**kwargs):
            port = FakePort(**kwargs); ports.append(port); return port
        src = SerialSource(factory)
        self.assertTrue(src.connect("COM3"))
        self.assertTrue(wait_for(lambda: src.snapshot()[0]))
        ports[-1].chunks.put(b"advertisement noise\nlayer_changed: layer 2 ")
        ports[-1].chunks.put(b"state 1\nModifiers set to 0x02\n")
        self.assertTrue(wait_for(lambda: src.snapshot()[2] == (2, None, 2)))
        self.assertTrue(src.disconnect())
        self.assertTrue(ports[0].closed)
        self.assertEqual(src.snapshot()[2], (None, None, None))
        self.assertTrue(src.connect("COM3"))
        self.assertTrue(wait_for(lambda: src.snapshot()[0]))
        self.assertEqual(src.snapshot()[2], (None, None, None))
        self.assertTrue(src.disconnect())
        self.assertTrue(ports[1].closed)

    def test_busy_port_is_reported_and_state_is_unknown(self):
        def factory(**kwargs): raise OSError("port busy")
        src = SerialSource(factory)
        src.connect("COM3")
        self.assertTrue(wait_for(lambda: "port busy" in src.snapshot()[1]))
        self.assertEqual(src.snapshot()[2], (None, None, None))
        self.assertTrue(src.disconnect())

    def test_unexpected_disconnect_clears_live_state(self):
        class Unplugged(FakePort):
            def read(self, _):
                item = self.chunks.get(timeout=1)
                if item is None:
                    raise OSError("device disconnected")
                return item
        ports=[]
        def factory(**kwargs):
            port=Unplugged(**kwargs); ports.append(port); return port
        src=SerialSource(factory); src.connect("COM3")
        self.assertTrue(wait_for(lambda: src.snapshot()[0]))
        ports[0].chunks.put(b"layer_changed: layer 2 state 1\n")
        self.assertTrue(wait_for(lambda: src.snapshot()[2][0] == 2))
        ports[0].chunks.put(None)
        self.assertTrue(wait_for(lambda: not src.snapshot()[0]))
        self.assertIn("device disconnected", src.snapshot()[1])
        self.assertEqual(src.snapshot()[2], (None,None,None))
        self.assertTrue(ports[0].closed)
        src.disconnect()

    def test_overlong_lines_are_discarded(self):
        ports=[]
        def factory(**kwargs):
            port=FakePort(**kwargs); ports.append(port); return port
        src=SerialSource(factory); src.connect("COM3")
        self.assertTrue(wait_for(lambda: src.snapshot()[0]))
        ports[0].chunks.put(b"x"*600+b"layer_changed: layer 2 state 1\n")
        ports[0].chunks.put(b"Modifiers set to 0x01\n")
        self.assertTrue(wait_for(lambda: src.snapshot()[2][2] == 1))
        self.assertIsNone(src.snapshot()[2][0]); src.disconnect()

if __name__ == "__main__": unittest.main()
