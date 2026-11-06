# ST7789 keyboard dashboard simulator

A Windows desktop LVGL simulator for a 240 x 280 keyboard dashboard. The canvas is shared C code, rendered with LVGL; the window provides manual left/right status controls and can optionally read Raven's ZMK v0.3.0 USB debug output. This repository contains the simulator and shared screen only. It does not contain a ZMK firmware module or a flashable build.

## Windows setup

Install Git and Python 3 with Tkinter. In PowerShell, from this repository:

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install cmake ninja ziglang pyserial
$env:Path = "$PWD/.venv/Scripts;$env:Path"
git init build/lvgl
git -C build/lvgl remote add origin https://github.com/lvgl/lvgl.git
git -C build/lvgl fetch --depth 1 origin 8a6a2d1d29d17d1e4bdc94c243c146a39d635fdd
git -C build/lvgl checkout --detach FETCH_HEAD
$zig = & .\.venv\Scripts\python -c "import ziglang, pathlib; print(pathlib.Path(ziglang.__file__).parent / 'zig.exe')"
cmake -S simulator -B build/simulator -G Ninja -DLVGL_DIR="$PWD/build/lvgl" -DCMAKE_C_COMPILER="$zig" -DCMAKE_C_COMPILER_ARG1=cc
cmake --build build/simulator
.\.venv\Scripts\python simulator/live.py
```

The LVGL commit is the revision pinned by the Zephyr dependency of stable ZMK v0.3.0. The simulator shows the 240 x 280 canvas at twice its native size. Manual mode estimates WPM from Windows keyboard activity. It retains only recent timestamps in memory, not typed characters or key identities.

## Optional ZMK USB debug source

Run a compatible ZMK v0.3.0 USB-logging build, connect its central over USB, enter its COM port (COM3 is the default), and click **Connect**. Close any other serial monitor first. USB mode consumes layer transitions, WPM, and left modifier mask updates from the debug stream at 115200 baud. It filters serial input in memory and never saves or displays raw logs or typed content. ZMK debug output can contain keycodes; use logging only when appropriate.

The layer is marked OBS because the debug stream contains transitions, not a complete initial snapshot. If no observed layer is active, it shows Unknown. WPM and modifiers are unknown until a relevant message arrives. The displayed modifier letters C, S, A, G correspond to left Ctrl, Shift, Alt and GUI; Alt and GUI still need interactive verification on the hardware. **Use manual** disconnects the port and restores manual layer and estimated WPM.

The left/right battery, charging, connection, host output and Bluetooth profile controls always simulate values. In particular, the simulator does not claim to read those fields from Raven's debug stream. Raven's current central is its left half; a future dongle with two peripherals is a different topology. USB logging is only a test source and is not a requirement for eventual hardware.

## Tests

```powershell
.\.venv\Scripts\python -m unittest discover -s tests -v
```

Tests cover colored ZMK log lines, layer transitions, modifier masks, malformed and oversized input, scan noise, serial errors, and disconnect/reconnect. The UI requires Windows and a graphical desktop. Physical display wiring, colors, power, and performance are not validated by this simulator.
