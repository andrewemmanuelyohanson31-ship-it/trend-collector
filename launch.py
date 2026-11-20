"""Open the trend dashboard like an app: no terminal, one click, its own window.
Adapted from data-analyst-agent/launch.py.

    python launch.py             start (or reopen) the dashboard
    python launch.py --install   one-time: make a Desktop shortcut (Windows) or "Trend Collector.app" (macOS)

The dashboard only reads trends.db, so it doesn't need Ollama. Stop it with "Quit app" in its sidebar.
"""
from __future__ import annotations

import os
import platform
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LOGS = ROOT / "logs"
PORT_FILE = LOGS / "app.port"
APP_NAME = "Trend Collector"
IS_WIN, IS_MAC = sys.platform == "win32", sys.platform == "darwin"
NO_WINDOW = 0x08000000 if IS_WIN else 0  # CREATE_NO_WINDOW: no console flashing up on Windows


def log(msg: str) -> None:
    LOGS.mkdir(exist_ok=True)
    with open(LOGS / "launcher.log", "a", encoding="utf-8") as f:
        f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}\n")


def responds(url: str, timeout: float = 1.0) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout):
            return True
    except Exception:  # noqa: BLE001 - any failure means "not up"
        return False


def wait_for(url: str, seconds: float) -> bool:
    end = time.time() + seconds
    while time.time() < end:
        if responds(url):
            return True
        time.sleep(0.5)
    return False


def free_port(preferred: int = 8601) -> int:
    for port in [preferred, *range(preferred + 1, preferred + 99)]:
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    raise RuntimeError(f"no free port from {preferred}")


def running_port() -> int | None:
    """The port of an app this launcher started earlier, if it is still serving."""
    try:
        port = int(PORT_FILE.read_text().strip())
    except (OSError, ValueError):
        return None
    return port if responds(f"http://localhost:{port}/_stcore/health") else None


def start_app() -> int:
    port = free_port()
    LOGS.mkdir(exist_ok=True)
    env = {**os.environ, "TC_LAUNCHER": "1"}  # shows the "Quit app" button
    out = open(LOGS / "app.log", "a", encoding="utf-8")  # noqa: SIM115 - handed to the child process
    subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", str(ROOT / "dashboard.py"), "--server.headless", "true",
         "--server.port", str(port), "--browser.gatherUsageStats", "false"],
        cwd=ROOT, env=env, stdout=out, stderr=subprocess.STDOUT, creationflags=NO_WINDOW,
        start_new_session=not IS_WIN)
    if not wait_for(f"http://localhost:{port}/_stcore/health", 60):
        raise RuntimeError(f"the app didn't start within 60 s; details in {LOGS / 'app.log'}")
    PORT_FILE.write_text(str(port))
    return port


def browser_command(url: str, system: str = sys.platform, exists=os.path.exists) -> list[str] | None:
    """Command that opens url as an app window (no tabs or address bar), or None for the default browser."""
    if system == "win32":
        candidates = [os.path.expandvars(p) for p in (
            r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe",
            r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe",
            r"%ProgramFiles%\Google\Chrome\Application\chrome.exe",
            r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe")]
        path = next((p for p in candidates if exists(p)), None)
        return [path, f"--app={url}", "--window-size=1400,900"] if path else None
    if system == "darwin":
        for app in ("Google Chrome", "Microsoft Edge", "Brave Browser"):
            if exists(f"/Applications/{app}.app"):
                return ["open", "-na", app, "--args", f"--app={url}", "--window-size=1400,900"]
        return None  # Safari has no app mode: open a normal window
    return None


def open_window(url: str) -> None:
    cmd = browser_command(url)
    if cmd:
        subprocess.Popen(cmd, creationflags=NO_WINDOW)
    else:
        webbrowser.open(url)


def show_error(message: str) -> None:
    """There is no terminal when started from the shortcut, so show problems in a dialog."""
    text = f"{APP_NAME} couldn't start:\n\n{message}\n\nLog: {LOGS / 'launcher.log'}"
    try:
        if IS_WIN:
            import ctypes

            ctypes.windll.user32.MessageBoxW(None, text, APP_NAME, 0x10)
        elif IS_MAC:
            safe = text.replace("\\", "\\\\").replace('"', '\\"')
            subprocess.run(["osascript", "-e", f'display dialog "{safe}" with title "{APP_NAME}" buttons {{"OK"}}'],
                           check=False)
    except Exception:  # noqa: BLE001 - the log still has it
        pass


def launch() -> None:
    port = running_port()
    if port:
        log(f"already running on port {port}: opening a window")
    else:
        port = start_app()
        log(f"started on port {port}")
    open_window(f"http://localhost:{port}")


# ---------- one-time install ----------

def make_icon() -> Path:
    """Draw a rising-trend icon (PNG + ICO) with Pillow, which Streamlit already installs."""
    from PIL import Image, ImageDraw

    out = ROOT / "assets"
    out.mkdir(exist_ok=True)
    img = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((8, 8, 248, 248), radius=48, fill=(220, 38, 38))  # red, like Indonesia's flag
    d.line([(44, 196), (100, 136), (136, 164), (204, 72)], fill=(255, 255, 255), width=18, joint="curve")
    d.polygon([(214, 50), (214, 112), (160, 70)], fill=(255, 255, 255))  # arrow head
    img.save(out / "icon.png")
    img.save(out / "icon.ico", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    return out


def install_windows() -> Path:
    icons = make_icon()
    pythonw = Path(sys.executable).with_name("pythonw.exe")  # pythonw: no console window
    ps = rf"""
$desktop = [Environment]::GetFolderPath('Desktop')
$s = (New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $desktop '{APP_NAME}.lnk'))
$s.TargetPath = '{pythonw}'
$s.Arguments = '"{ROOT / 'launch.py'}"'
$s.WorkingDirectory = '{ROOT}'
$s.IconLocation = '{icons / 'icon.ico'}'
$s.Description = 'Indonesia next viral trend dashboard'
$s.Save()
Join-Path $desktop '{APP_NAME}.lnk'
"""
    done = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True, check=True)
    return Path(done.stdout.strip())


def install_mac() -> Path:
    """Build '~/Applications/Data Analyst Agent.app' with built-in macOS tools (osacompile, sips, iconutil)."""
    icons = make_icon()
    python = ROOT / ".venv" / "bin" / "python"
    if not python.exists():  # first time on this Mac: create the environment
        subprocess.run([sys.executable, "-m", "venv", str(ROOT / ".venv")], check=True)
        subprocess.run([str(python), "-m", "pip", "install", "-r", str(ROOT / "requirements.txt")], check=True)
    apps = Path.home() / "Applications"
    apps.mkdir(exist_ok=True)
    app = apps / f"{APP_NAME}.app"
    script = f'do shell script "cd {_q(ROOT)} && {_q(python)} launch.py > /dev/null 2>&1 &"'
    subprocess.run(["osacompile", "-o", str(app), "-e", script], check=True)
    iconset = icons / "icon.iconset"
    iconset.mkdir(exist_ok=True)
    for size in (16, 32, 128, 256):
        for scale in (1, 2):
            px = size * scale
            subprocess.run(["sips", "-z", str(px), str(px), str(icons / "icon.png"), "--out",
                            str(iconset / f"icon_{size}x{size}{'@2x' if scale == 2 else ''}.png")],
                           check=True, capture_output=True)
    subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(app / "Contents" / "Resources" / "applet.icns")],
                   check=True)
    shutil.rmtree(iconset, ignore_errors=True)
    subprocess.run(["touch", str(app)], check=False)  # make Finder pick up the new icon
    return app


def _q(path) -> str:
    """Quote a path for the shell inside an AppleScript string."""
    return "'" + str(path).replace("'", "'\\''") + "'"


def install() -> None:
    where = install_windows() if IS_WIN else install_mac() if IS_MAC else None
    if where is None:
        print(f"No installer for {platform.system()}; run: {sys.executable} launch.py")
        return
    print(f"Created {where}\nDouble-click it to start {APP_NAME}.")
    if IS_MAC:
        print("First time only: if macOS says it can't check the app, right-click it and choose Open.")


if __name__ == "__main__":
    if "--install" in sys.argv:
        install()
    else:
        try:
            launch()
        except Exception as e:  # noqa: BLE001 - no terminal: log it and show it
            log(f"ERROR {e}")
            show_error(str(e))
            sys.exit(1)
