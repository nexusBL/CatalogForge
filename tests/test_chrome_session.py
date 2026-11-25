from pathlib import Path

import pytest

from scraper.swiggy.chrome_session import (
    ChromeCdpUnavailableError,
    ChromeUnavailableError,
    DEFAULT_CDP_URL,
    acquire_chrome,
    acquire_chrome_background,
    acquire_chrome_cdp,
    catalogforge_profile_dir,
    chrome_debug_url,
    detect_chrome_path,
    resolve_browser_mode,
    start_catalogforge_chrome,
)
from scraper.swiggy.parser import parse_swiggy_catalogue
from scraper.swiggy.scraper import collect_local_source, collect_swiggy_source

FIXTURE_JSON = Path(__file__).parent / "fixtures" / "swiggy_menu_payload.json"
FIXTURE_HTML = Path(__file__).parent / "fixtures" / "dom_menu_categories.html"
URL = "https://www.swiggy.com/city/mangaluru/harbor-leaf-cafe-rest210000"


def test_default_browser_mode_is_playwright(monkeypatch):
    monkeypatch.delenv("CATALOGFORGE_BROWSER_MODE", raising=False)
    assert resolve_browser_mode(None) == "playwright"


def test_browser_mode_from_cli_and_env(monkeypatch):
    monkeypatch.setenv("CATALOGFORGE_BROWSER_MODE", "chrome")
    assert resolve_browser_mode(None) == "chrome"
    assert resolve_browser_mode("playwright") == "playwright"


def test_visible_and_background_mode_aliases():
    assert resolve_browser_mode("visible") == "chrome"
    assert resolve_browser_mode("background") == "chrome-background"
    assert resolve_browser_mode("chrome-cdp") == "chrome-cdp"


def test_dedicated_profile_uses_system_temp(tmp_path, monkeypatch):
    monkeypatch.setenv("CATALOGFORGE_CHROME_PROFILE", str(tmp_path / "catalogforge-chrome"))
    path = catalogforge_profile_dir()
    assert path == tmp_path / "catalogforge-chrome"
    assert path.is_dir()
    assert "l670b" not in str(path).replace(str(tmp_path), "")


def test_start_catalogforge_chrome_uses_cdp_and_dedicated_profile(tmp_path, monkeypatch):
    chrome = tmp_path / "chrome.exe"
    chrome.write_bytes(b"")
    profile = tmp_path / "catalogforge-chrome"
    monkeypatch.setenv("CATALOGFORGE_CHROME_PATH", str(chrome))
    monkeypatch.setenv("CATALOGFORGE_CHROME_PROFILE", str(profile))
    monkeypatch.setenv("CATALOGFORGE_CHROME_DEBUG_PORT", "9222")
    monkeypatch.delenv("CATALOGFORGE_CHROME_DEBUG_URL", raising=False)
    captured = {}

    class FakePopen:
        def __init__(self, args, **kwargs):
            captured["args"] = list(args)
            self.pid = 77

        def poll(self):
            return None

        def terminate(self):
            return None

        def wait(self, timeout=None):
            return 0

        def kill(self):
            return None

    monkeypatch.setattr("scraper.swiggy.chrome_session.subprocess.Popen", FakePopen)
    monkeypatch.setattr("scraper.swiggy.chrome_session.wait_for_cdp", lambda url, timeout_sec=None: None)
    monkeypatch.setattr("scraper.swiggy.chrome_session.cdp_endpoint_ready", lambda url, timeout_sec=None: False)
    monkeypatch.setattr("scraper.swiggy.chrome_session._port_available", lambda port: True)
    monkeypatch.setattr("scraper.swiggy.chrome_session.choose_debug_port", lambda preferred=None: 9222)

    visible = start_catalogforge_chrome(visible=True)
    assert visible["pid"] == 77
    assert visible["debug_url"] == "http://127.0.0.1:9222"
    assert "--remote-debugging-port=9222" in captured["args"]
    assert any(str(arg).startswith("--user-data-dir=") and "catalogforge-chrome" in str(arg) for arg in captured["args"])
    assert "--start-minimized" not in captured["args"]
    assert captured["args"][0] == str(chrome)

    background = start_catalogforge_chrome(visible=False)
    assert "--remote-debugging-port=9222" in captured["args"]
    assert background["profile_path"] == str(profile)
    assert "--start-minimized" not in captured["args"]


def test_ready_cdp_is_reused_instead_of_second_launch(tmp_path, monkeypatch):
    from scraper.swiggy.chrome_session import reset_browser_lifecycle_for_tests, start_catalogforge_chrome

    reset_browser_lifecycle_for_tests()
    chrome = tmp_path / "chrome.exe"
    chrome.write_bytes(b"")
    monkeypatch.setenv("CATALOGFORGE_CHROME_PATH", str(chrome))
    monkeypatch.setenv("CATALOGFORGE_CHROME_PROFILE", str(tmp_path / "catalogforge-chrome"))
    monkeypatch.setenv("CATALOGFORGE_CHROME_DEBUG_PORT", "9222")
    monkeypatch.delenv("CATALOGFORGE_CHROME_DEBUG_URL", raising=False)
    launches = {"n": 0}

    class FakePopen:
        def __init__(self, args, **kwargs):
            launches["n"] += 1
            self.pid = 88

        def poll(self):
            return None

        def terminate(self):
            return None

        def wait(self, timeout=None):
            return 0

        def kill(self):
            return None

    ready = {"cdp": False}

    def fake_ready(url, timeout_sec=None):
        return ready["cdp"]

    monkeypatch.setattr("scraper.swiggy.chrome_session.subprocess.Popen", FakePopen)
    monkeypatch.setattr("scraper.swiggy.chrome_session.wait_for_cdp", lambda url, timeout_sec=None: None)
    monkeypatch.setattr("scraper.swiggy.chrome_session.cdp_endpoint_ready", fake_ready)
    monkeypatch.setattr("scraper.swiggy.chrome_session._port_available", lambda port: True)

    first = start_catalogforge_chrome(visible=False)
    assert launches["n"] == 1
    assert first.get("reused") is False
    ready["cdp"] = True
    second = start_catalogforge_chrome(visible=False)
    assert launches["n"] == 1
    assert second.get("reused") is True


def test_attached_cdp_browser_is_not_killed():
    from scraper.swiggy.chrome_session import ChromeHandle, close_chrome

    stopped = []

    class FakeProc:
        def poll(self):
            return None

        def terminate(self):
            stopped.append("term")

        def wait(self, timeout=None):
            return 0

        def kill(self):
            stopped.append("kill")

    handle = ChromeHandle(
        browser=object(),
        mode="chrome-cdp",
        path=None,
        debug_url="http://127.0.0.1:9222",
        owns_browser=False,
        owns_process=False,
        process=FakeProc(),
        pid=9,
    )
    close_chrome(handle)
    assert stopped == []


def test_owned_chrome_survives_retries_inside_browser_job(monkeypatch):
    from scraper.swiggy.chrome_session import ChromeHandle, browser_job, close_chrome
    import scraper.swiggy.chrome_session as cs

    stopped = []

    class FakeProc:
        def poll(self):
            return None

        def terminate(self):
            stopped.append("term")

        def wait(self, timeout=None):
            return 0

        def kill(self):
            stopped.append("kill")

    proc = FakeProc()
    cs._launched_process = proc
    handle = ChromeHandle(
        browser=object(),
        mode="chrome-background",
        path=None,
        debug_url="http://127.0.0.1:9222",
        owns_browser=False,
        owns_process=True,
        process=proc,
        pid=11,
    )
    with browser_job():
        close_chrome(handle)
        close_chrome(handle)
        assert stopped == []
    assert "term" in stopped
    cs._launched_process = None


def test_managed_visible_chrome_connects_over_cdp_without_playwright_launch(monkeypatch):
    started = {}

    class FakeBrowser:
        contexts = []

    class FakeChromium:
        @staticmethod
        def connect_over_cdp(url):
            started["url"] = url
            return FakeBrowser()

        @staticmethod
        def launch(**kwargs):
            raise AssertionError("must use connect_over_cdp, not bundled Chromium")

    class FakePlaywright:
        chromium = FakeChromium()

    monkeypatch.setattr(
        "scraper.swiggy.chrome_session.start_catalogforge_chrome",
        lambda visible: {
            "process": None,
            "pid": 4242,
            "path": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            "profile_path": r"C:\Temp\catalogforge-chrome",
            "debug_port": 9222,
            "debug_url": "http://127.0.0.1:9222",
            "visible": visible,
        },
    )
    handle = acquire_chrome(FakePlaywright())
    assert started["url"] == "http://127.0.0.1:9222"
    assert handle.mode == "chrome"
    assert handle.owns_process is False
    assert handle.pid == 4242

    background = acquire_chrome_background(FakePlaywright())
    assert background.mode == "chrome-background"
    assert background.owns_process is True


def test_default_cdp_url(monkeypatch):
    monkeypatch.delenv("CATALOGFORGE_CHROME_DEBUG_URL", raising=False)
    assert chrome_debug_url() is None
    assert chrome_debug_url(required=True) == DEFAULT_CDP_URL
    assert DEFAULT_CDP_URL == "http://127.0.0.1:9222"


def test_custom_cdp_url(monkeypatch):
    monkeypatch.setenv("CATALOGFORGE_CHROME_DEBUG_URL", "http://127.0.0.1:9333")
    assert chrome_debug_url() == "http://127.0.0.1:9333"
    assert chrome_debug_url(required=True) == "http://127.0.0.1:9333"


def test_cdp_unavailable_does_not_launch_chrome(monkeypatch):
    monkeypatch.delenv("CATALOGFORGE_CHROME_DEBUG_URL", raising=False)

    class FakeChromium:
        @staticmethod
        def connect_over_cdp(url):
            assert url == DEFAULT_CDP_URL
            raise RuntimeError("ECONNREFUSED")

        @staticmethod
        def launch(**kwargs):
            raise AssertionError("chrome-cdp must not launch Chrome")

    class FakePlaywright:
        chromium = FakeChromium()

    with pytest.raises(ChromeCdpUnavailableError) as exc:
        acquire_chrome_cdp(FakePlaywright())
    assert "CHROME_CDP_UNAVAILABLE" in str(exc.value)
    assert "remote debugging" in str(exc.value)


def test_successful_mocked_cdp_connection(monkeypatch):
    monkeypatch.setenv("CATALOGFORGE_CHROME_DEBUG_URL", "http://127.0.0.1:9222")
    connected = {}

    class FakeBrowser:
        contexts = []

    class FakeChromium:
        @staticmethod
        def connect_over_cdp(url):
            connected["url"] = url
            return FakeBrowser()

        @staticmethod
        def launch(**kwargs):
            raise AssertionError("must not launch")

    class FakePlaywright:
        chromium = FakeChromium()

    handle = acquire_chrome_cdp(FakePlaywright())
    assert connected["url"] == "http://127.0.0.1:9222"
    assert handle.mode == "chrome-cdp"
    assert handle.owns_browser is False
    assert handle.debug_url == "http://127.0.0.1:9222"
    assert handle.browser is not None


def test_collect_chrome_cdp_unavailable_is_failed_not_ok(monkeypatch):
    def boom(_playwright):
        raise ChromeCdpUnavailableError("Start Chrome with remote debugging on port 9222 and try again.")

    class Manager:
        def __enter__(self):
            return object()

        def __exit__(self, *args):
            return False

    monkeypatch.setattr("scraper.swiggy.scraper.sync_playwright", lambda: Manager())
    monkeypatch.setattr("scraper.swiggy.scraper.acquire_chrome_cdp", boom)
    raw = collect_swiggy_source(URL, browser_mode="chrome-cdp")
    assert raw.browser_mode == "chrome-cdp"
    assert raw.access_status == "failed"
    assert "CHROME_CDP_UNAVAILABLE" in (raw.reason or "")
    catalogue = parse_swiggy_catalogue(raw)
    assert catalogue.extraction_status == "failed"
    assert catalogue.item_count == 0


def test_chrome_path_override_when_file_exists(tmp_path, monkeypatch):
    chrome = tmp_path / "chrome.exe"
    chrome.write_bytes(b"")
    monkeypatch.setenv("CATALOGFORGE_CHROME_PATH", str(chrome))
    assert detect_chrome_path() == str(chrome)


def test_chrome_path_override_missing_file(tmp_path, monkeypatch):
    missing = tmp_path / "missing-chrome.exe"
    monkeypatch.setenv("CATALOGFORGE_CHROME_PATH", str(missing))
    assert detect_chrome_path() == None


def test_explicit_path_detection(tmp_path):
    chrome = tmp_path / "Google Chrome"
    chrome.write_bytes(b"")
    assert detect_chrome_path(str(chrome)) == str(chrome)
    assert detect_chrome_path(str(tmp_path / "nope")) is None


def test_missing_chrome_launch_returns_chrome_unavailable(monkeypatch):
    monkeypatch.delenv("CATALOGFORGE_CHROME_PATH", raising=False)
    monkeypatch.delenv("CATALOGFORGE_CHROME_DEBUG_URL", raising=False)
    monkeypatch.setattr("scraper.swiggy.chrome_session.detect_chrome_path", lambda explicit=None: None)

    class FakeChromium:
        @staticmethod
        def launch(**kwargs):
            raise RuntimeError("executable not found")

        @staticmethod
        def connect_over_cdp(url):
            raise AssertionError("should not connect")

    class FakePlaywright:
        chromium = FakeChromium()

    from scraper.swiggy.chrome_session import acquire_chrome

    with pytest.raises(ChromeUnavailableError) as exc:
        acquire_chrome(FakePlaywright())
    assert "chrome_unavailable" in str(exc.value)


def test_collect_chrome_unavailable_is_failed_not_ok(monkeypatch):
    def boom(_playwright):
        raise ChromeUnavailableError("Installed Google Chrome was not found", path=None)

    class Manager:
        def __enter__(self):
            return object()

        def __exit__(self, *args):
            return False

    monkeypatch.setattr("scraper.swiggy.scraper.sync_playwright", lambda: Manager())
    monkeypatch.setattr("scraper.swiggy.scraper.acquire_chrome", boom)
    raw = collect_swiggy_source(URL, browser_mode="chrome")
    assert raw.browser_mode == "chrome"
    assert raw.access_status == "failed"
    assert "chrome_unavailable" in (raw.reason or "")
    catalogue = parse_swiggy_catalogue(raw)
    assert catalogue.extraction_status == "failed"
    assert catalogue.categories == []
    assert catalogue.item_count == 0


def test_fixture_pipeline_still_extracts_without_chrome():
    raw = collect_local_source(URL, json_path=FIXTURE_JSON)
    catalogue = parse_swiggy_catalogue(raw)
    assert catalogue.extraction_status == "ok"
    assert catalogue.source_type == "xhr_json"
    assert catalogue.restaurant.name == "Harbor Spice House"
    assert catalogue.item_count == 2


def test_html_fixture_still_uses_dom_discovery():
    raw = collect_local_source(URL, html_path=FIXTURE_HTML)
    catalogue = parse_swiggy_catalogue(raw)
    assert catalogue.extraction_status == "ok"
    assert catalogue.source_type == "dom_discovery"
    assert catalogue.item_count == 8
