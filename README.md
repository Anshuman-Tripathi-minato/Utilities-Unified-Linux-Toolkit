# Utilities — Unified Linux Toolkit

Utilities is a lightweight desktop dashboard for inspecting and managing an Ubuntu/Linux workstation. It combines live system telemetry with practical device, package, file, privacy, and backup tools in a responsive glassmorphism interface.

The application is intentionally local. The Python backend binds to `127.0.0.1` on an automatically selected port and serves the dashboard from the same process. It reads data from Linux APIs and files such as `sysfs`, and uses established system tools including BlueZ and `dpkg`.

## Features

The dashboard is organized into focused “houses”:

- **Monitor** — CPU, memory, swap, disk, load, and process activity.
- **Net** — network interfaces, addresses, link state, speed, and active connections.
- **Power** — battery percentage, charging state, health, capacity, voltage, power, and cycle data when exposed by the hardware.
- **Thermal** — thermal zones, fan RPM, and writable hwmon PWM controls.
- **Device** — Bluetooth adapters and devices plus USB device discovery.
- **Disk** — mounted filesystems, capacity, usage, and free space.
- **App** — installed Debian packages and package removal through an administrator prompt.
- **File** — common filesystem locations and a request to open folders with the desktop file manager.
- **Privacy** — local privacy and system-state checks exposed by the backend.
- **Backup** — local recovery and backup guidance.

Most live panels refresh automatically while the dashboard is open. Hardware-dependent values are omitted or marked unavailable when Linux does not expose them.

## Requirements

- Ubuntu or another Linux distribution with Python 3
- Python package: [`psutil`](https://pypi.org/project/psutil/)
- Chromium or `chromium-browser`
- Optional system integrations:
  - `bluez` / `bluetoothctl` for Bluetooth controls
  - `usbutils` / `lsusb` for USB discovery
  - `policykit-1` / `pkexec` for package removal

## Quick start

Install the base dependencies and launch the dashboard:

```bash
sudo apt update
sudo apt install -y python3 python3-pip chromium bluez usbutils policykit-1
./run.sh
```

`run.sh` installs `psutil` for the current user (falling back to a system install if necessary), starts the backend, waits for its health signal, and opens Chromium in app mode. The launcher chooses a free localhost port automatically, so it can run alongside other local dashboards.

To stop Utilities, close the Chromium window and press `Ctrl+C` in the terminal that started it. The launcher cleans up its backend process when it exits.

## Run without the launcher

The backend can also be started directly:

```bash
python3 -m pip install --user -r requirements.txt
python3 server.py
```

The server prints the selected port:

```text
UTILITIES_PORT=54321
```

Open `http://127.0.0.1:54321` in a browser, replacing the port with the value printed by your process.

## Permissions and safety

- The server listens on loopback only; it is not intended to be exposed to a network.
- Bluetooth actions depend on the permissions granted to the current desktop session and on `bluetoothctl`.
- Fan controls are shown only for writable `/sys/class/hwmon/...` PWM files. Writing an incorrect value can affect cooling, so change fan values cautiously.
- Package removal runs `pkexec apt remove -y <package>` and requires explicit administrator approval.
- Opening a folder delegates to the desktop environment through `xdg-open`.
- Utilities is an inspection and convenience layer; it does not replace a dedicated backup system or hardware monitoring daemon.

## Troubleshooting

### Chromium is not found

Install Chromium, or install the distribution package that provides `chromium-browser`. The backend can still be started with `python3 server.py`, but `run.sh` requires a Chromium executable to open the UI.

### Optional panels are empty

This is usually expected when the corresponding Linux interface or command is unavailable. Install the optional packages listed above and verify the relevant command, for example:

```bash
command -v bluetoothctl
command -v lsusb
```

Some battery, temperature, fan, and cycle-count fields are hardware-specific and cannot be synthesized when the kernel does not provide them.

### The backend fails to start

Run it directly to see the error:

```bash
python3 server.py
```

`run.sh` writes its launcher log to `${TMPDIR:-/tmp}/utilities-suite-$USER.log`.

## Project layout

```text
.
├── server.py          # Local HTTP API and Linux integrations
├── static/index.html  # Dashboard UI
├── run.sh             # Dependency install, launch, and cleanup wrapper
├── requirements.txt   # Python dependencies
└── README.md
```


