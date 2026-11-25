from __future__ import annotations

import os
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

CHROME_MODE = "chrome"
CHROME_BACKGROUND_MODE = "chrome-background"
CHROME_CDP_MODE = "chrome-cdp"
PLAYWRIGHT_MODE = "playwright"
MODE_ALIASES = {
    "visible": CHROME_MODE,
    "background": CHROME_BACKGROUND_MODE,
    "demo": CHROME_MODE,
}
VALID_MODES = {PLAYWRIGHT_MODE, CHROME_MODE, CHROME_BACKGROUND_MODE, CHROME_CDP_MODE}
DEFAULT_CDP_URL = "http://127.0.0.1:9222"
DEFAULT_CDP_PORT = 9222
DEFAULT_PROFILE_NAME = "catalogforge-chrome"
CDP_READY_TIMEOUT_SEC = 25

_job_depth = 0
_launched_process: subprocess.Popen | None = None
_lifecycle = {
    "browser_created_by_us": False,
    "launches": 0,
    "attaches": 0,
    "pages_created": 0,
    "pages_closed": 0,
}

WINDOWS_CHROME_CANDIDATES = (
    Path(os.environ.get("PROGRAMFILES", r"C:\Program Files")) / "Google/Chrome/Application/chrome.exe",
    Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)")) / "Google/Chrome/Application/chrome.exe",
    Path(os.environ.get("LOCALAPPDATA", "")) / "Google/Chrome/Application/chrome.exe",
)
MAC_CHROME_CANDIDATES = (
    Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
)
LINUX_CHROME_CANDIDATES = (
    Path("/usr/bin/google-chrome"),
    Path("/usr/bin/google-chrome-stable"),
    Path("/usr/bin/chromium"),
    Path("/usr/bin/chromium-browser"),
)


class ChromeUnavailableError(RuntimeError):
    code = "chrome_unavailable"

    def __init__(self, message: str, path: str | None = None):
        super().__init__(message)
        self.path = path

    def __str__(self) -> str:
        return f"{self.code}: {super().__str__()}"


class ChromeCdpUnavailableError(ChromeUnavailableError):
    code = "CHROME_CDP_UNAVAILABLE"


@dataclass
class ChromeHandle:
    browser: object
    mode: str
    path: str | None
    debug_url: str | None
    owns_browser: bool
    owns_process: bool = False
    pid: int | None = None
    profile_path: str | None = None
    debug_port: int | None = None
    process: subprocess.Popen | None = None


def resolve_browser_mode(value: str | None = None) -> str:
    raw = (value if value is not None else os.getenv("CATALOGFORGE_BROWSER_MODE", PLAYWRIGHT_MODE)) or PLAYWRIGHT_MODE
    mode = MODE_ALIASES.get(raw.strip().lower(), raw.strip().lower())
    if mode not in VALID_MODES:
        raise ValueError(
            f"Unsupported browser mode {raw!r}. Use playwright, chrome, chrome-background, or chrome-cdp."
        )
    return mode


def configured_chrome_path() -> str | None:
    override = (os.getenv("CATALOGFORGE_CHROME_PATH") or "").strip()
    return override or None


def chrome_debug_url(*, required: bool = False) -> str | None:
    value = (os.getenv("CATALOGFORGE_CHROME_DEBUG_URL") or "").strip()
    if value:
        return value
    if required:
        return DEFAULT_CDP_URL
    return None


def catalogforge_profile_dir() -> Path:
    override = (os.getenv("CATALOGFORGE_CHROME_PROFILE") or "").strip()
    if override:
        path = Path(override)
    else:
        path = Path(tempfile.gettempdir()) / DEFAULT_PROFILE_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def choose_debug_port(preferred: int | None = None) -> int:
    start = preferred if preferred is not None else int(os.getenv("CATALOGFORGE_CHROME_DEBUG_PORT", str(DEFAULT_CDP_PORT)))
    for port in range(start, start + 20):
        if _port_available(port):
            return port
    raise ChromeUnavailableError(f"No free Chrome debugging port found near {start}.")


def browser_lifecycle() -> dict[str, int | bool]:
    return dict(_lifecycle)


def note_page_created() -> None:
    _lifecycle["pages_created"] = int(_lifecycle["pages_created"]) + 1


def note_page_closed() -> None:
    _lifecycle["pages_closed"] = int(_lifecycle["pages_closed"]) + 1


def reset_browser_lifecycle_for_tests() -> None:
    global _job_depth, _launched_process
    _job_depth = 0
    _launched_process = None
    _lifecycle.update(
        {
            "browser_created_by_us": False,
            "launches": 0,
            "attaches": 0,
            "pages_created": 0,
            "pages_closed": 0,
        }
    )


@contextmanager
def browser_job():
    """Keep one managed Chrome process for a whole discovery job."""
    global _job_depth
    _job_depth += 1
    try:
        yield
    finally:
        _job_depth = max(0, _job_depth - 1)
        if _job_depth == 0:
            _stop_launched_browser()


def _stop_launched_browser() -> None:
    global _launched_process
    _stop_process(_launched_process)
    _launched_process = None


def preferred_debug_url() -> str:
    return chrome_debug_url() or f"http://127.0.0.1:{int(os.getenv('CATALOGFORGE_CHROME_DEBUG_PORT', str(DEFAULT_CDP_PORT)))}"


def cdp_endpoint_ready(debug_url: str, timeout_sec: float = 0.6) -> bool:
    try:
        wait_for_cdp(debug_url, timeout_sec=timeout_sec)
        return True
    except ChromeUnavailableError:
        return False


def detect_chrome_path(explicit: str | None = None) -> str | None:
    """Return an existing Chrome executable path, or None if not found.

    Does not invent a path. CATALOGFORGE_CHROME_PATH wins when set.
    """
    if explicit:
        path = Path(explicit)
        return str(path) if path.is_file() else None
    override = configured_chrome_path()
    if override:
        path = Path(override)
        return str(path) if path.is_file() else None
    for candidate in _chrome_candidates():
        if candidate and candidate.is_file():
            return str(candidate)
    return None


def _chrome_candidates() -> list[Path]:
    return [path for path in (*WINDOWS_CHROME_CANDIDATES, *MAC_CHROME_CANDIDATES, *LINUX_CHROME_CANDIDATES) if path]


def _port_available(port: int) -> bool:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind(("127.0.0.1", port))
        return True
    except OSError:
        return False
    finally:
        sock.close()


def wait_for_cdp(debug_url: str, timeout_sec: float = CDP_READY_TIMEOUT_SEC) -> None:
    endpoint = debug_url.rstrip("/") + "/json/version"
    deadline = time.time() + timeout_sec
    last_error = "timeout"
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(endpoint, timeout=1) as response:
                if 200 <= response.status < 300:
                    return
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_error = str(exc)
        time.sleep(0.25)
    raise ChromeUnavailableError(f"Chrome remote debugging did not become ready at {debug_url} ({last_error}).")


def start_catalogforge_chrome(*, visible: bool) -> dict[str, object]:
    """Start installed Google Chrome with a dedicated CatalogForge profile and CDP.

    Reuses an already-ready CDP endpoint instead of launching another Chrome.
    """
    global _launched_process
    debug_url = preferred_debug_url()
    port = int(urlparse_port(debug_url))
    if cdp_endpoint_ready(debug_url):
        _lifecycle["attaches"] = int(_lifecycle["attaches"]) + 1
        return {
            "process": None,
            "pid": None,
            "path": detect_chrome_path(),
            "profile_path": str(catalogforge_profile_dir()),
            "debug_port": port,
            "debug_url": debug_url,
            "visible": visible,
            "reused": True,
        }
    executable = detect_chrome_path()
    if not executable:
        raise ChromeUnavailableError(
            "Installed Google Chrome was not found. Set CATALOGFORGE_CHROME_PATH to chrome.exe."
        )
    if not _port_available(port):
        raise ChromeUnavailableError(
            f"Chrome debug port {port} is busy and CDP is not ready. Not launching a second Chrome."
        )
    profile = catalogforge_profile_dir()
    args = [
        executable,
        f"--remote-debugging-port={port}",
        f"--user-data-dir={profile}",
        "--no-first-run",
        "--no-default-browser-check",
    ]
    creationflags = 0
    if os.name == "nt":
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    process = subprocess.Popen(
        args,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        creationflags=creationflags,
    )
    try:
        wait_for_cdp(debug_url)
    except Exception:
        _stop_process(process)
        raise
    _launched_process = process
    _lifecycle["launches"] = int(_lifecycle["launches"]) + 1
    _lifecycle["browser_created_by_us"] = True
    return {
        "process": process,
        "pid": process.pid,
        "path": executable,
        "profile_path": str(profile),
        "debug_port": port,
        "debug_url": debug_url,
        "visible": visible,
        "reused": False,
    }


def urlparse_port(debug_url: str) -> int:
    from urllib.parse import urlparse

    parsed = urlparse(debug_url)
    if parsed.port:
        return parsed.port
    return DEFAULT_CDP_PORT


def acquire_managed_chrome(playwright, *, visible: bool) -> ChromeHandle:
    started = start_catalogforge_chrome(visible=visible)
    debug_url = str(started["debug_url"])
    try:
        browser = playwright.chromium.connect_over_cdp(debug_url)
    except Exception as exc:
        _stop_process(started.get("process"))
        raise ChromeUnavailableError(
            f"Started Chrome but could not connect over CDP at {debug_url}.",
            path=str(started.get("path") or ""),
        ) from exc
    mode = CHROME_MODE if visible else CHROME_BACKGROUND_MODE
    launched = not started.get("reused") and bool(started.get("process") or started.get("pid"))
    return ChromeHandle(
        browser=browser,
        mode=mode,
        path=str(started["path"]) if started.get("path") else None,
        debug_url=debug_url,
        owns_browser=False,
        owns_process=(not visible) and launched,
        pid=int(started["pid"]) if started.get("pid") else None,
        profile_path=str(started["profile_path"]) if started.get("profile_path") else None,
        debug_port=int(started["debug_port"]) if started.get("debug_port") else None,
        process=started["process"] if isinstance(started.get("process"), subprocess.Popen) else None,
    )


def acquire_chrome(playwright) -> ChromeHandle:
    """Visible/demo mode: start CatalogForge Chrome, then connect_over_cdp."""
    return acquire_managed_chrome(playwright, visible=True)


def acquire_chrome_background(playwright) -> ChromeHandle:
    """Production mode: start CatalogForge Chrome, connect_over_cdp, close after the job."""
    return acquire_managed_chrome(playwright, visible=False)


def acquire_chrome_cdp(playwright) -> ChromeHandle:
    """Connect to a user-started Chrome. Never launches a browser."""
    debug_url = chrome_debug_url(required=True) or DEFAULT_CDP_URL
    try:
        browser = playwright.chromium.connect_over_cdp(debug_url)
    except Exception as exc:
        raise ChromeCdpUnavailableError(
            "Start Chrome with remote debugging on port 9222 and try again.",
            path=None,
        ) from exc
    return ChromeHandle(
        browser=browser,
        mode=CHROME_CDP_MODE,
        path=None,
        debug_url=debug_url,
        owns_browser=False,
        owns_process=False,
    )


def close_chrome(handle: ChromeHandle | None) -> None:
    global _launched_process
    if handle is None:
        return
    if handle.owns_browser and handle.browser is not None:
        try:
            handle.browser.close()
        except Exception:
            pass
    if handle.owns_process:
        if _job_depth > 0:
            return
        _stop_process(handle.process)
        if handle.pid and handle.process is None:
            _stop_pid(handle.pid)
        if handle.process is _launched_process:
            _launched_process = None


def _stop_process(process: object) -> None:
    if process is None or not hasattr(process, "poll"):
        return
    if process.poll() is not None:
        return
    try:
        process.terminate()
        process.wait(timeout=5)
    except Exception:
        try:
            process.kill()
        except Exception:
            pass


def _stop_pid(pid: int) -> None:
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, check=False)
        return
    try:
        os.kill(pid, 15)
    except OSError:
        pass
