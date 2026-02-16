from app.core.models import DownloadInput
from app.core.ytdlp_service import YtDlpService


def test_cookie_options_browser() -> None:
    svc = YtDlpService()
    payload = DownloadInput(
        url="https://example.com",
        output_dir=".",
        cookies_mode="browser",
        browser_name="chrome",
    )
    opts = svc._cookie_options(payload)
    assert "cookiesfrombrowser" in opts


def test_cookie_options_file() -> None:
    svc = YtDlpService()
    payload = DownloadInput(
        url="https://example.com",
        output_dir=".",
        cookies_mode="file",
        cookies_file="cookies.txt",
    )
    opts = svc._cookie_options(payload)
    assert opts.get("cookiefile") == "cookies.txt"

