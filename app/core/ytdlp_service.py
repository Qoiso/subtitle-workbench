from __future__ import annotations

import asyncio
from dataclasses import asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from app.core.models import DownloadInput, DownloadResult, FormatInfo

try:
    from yt_dlp import YoutubeDL
    from yt_dlp.utils import DownloadError
except Exception:  # pragma: no cover
    YoutubeDL = None
    DownloadError = Exception


class YtDlpService:
    def __init__(self) -> None:
        self._cache: dict[str, tuple[datetime, dict[str, Any]]] = {}
        self._ttl = timedelta(minutes=10)

    def _cookie_options(self, data: DownloadInput) -> dict[str, Any]:
        opts: dict[str, Any] = {}
        if data.cookies_mode == "browser" and data.browser_name:
            opts["cookiesfrombrowser"] = (data.browser_name,)
        elif data.cookies_mode == "file" and data.cookies_file:
            opts["cookiefile"] = data.cookies_file
        return opts

    def _base_opts(self, data: DownloadInput) -> dict[str, Any]:
        outtmpl = str(Path(data.output_dir) / "%(title).200B [%(id)s].%(ext)s")
        return {
            "outtmpl": outtmpl,
            "noplaylist": True,
            "quiet": True,
            "no_warnings": True,
            "continuedl": True,
            "nopart": False,
            **self._cookie_options(data),
        }

    async def list_formats(self, url: str, cookie_opts: DownloadInput) -> list[FormatInfo]:
        if not YoutubeDL:
            raise RuntimeError("yt-dlp is unavailable. Install dependencies first.")

        now = datetime.now()
        cached = self._cache.get(url)
        if cached and now - cached[0] <= self._ttl:
            info = cached[1]
        else:
            def _extract() -> dict[str, Any]:
                with YoutubeDL(self._base_opts(cookie_opts)) as ydl:
                    return ydl.extract_info(url, download=False)

            info = await asyncio.to_thread(_extract)
            self._cache[url] = (now, info)

        items: list[FormatInfo] = []
        for f in info.get("formats", []):
            items.append(
                FormatInfo(
                    format_id=str(f.get("format_id", "")),
                    ext=str(f.get("ext", "")),
                    note=str(f.get("format_note", "")),
                    resolution=f.get("resolution"),
                    vcodec=f.get("vcodec"),
                    acodec=f.get("acodec"),
                )
            )
        return items

    async def download(self, data: DownloadInput, progress_cb=None) -> DownloadResult:
        if not YoutubeDL:
            raise RuntimeError("yt-dlp is unavailable. Install dependencies first.")
        Path(data.output_dir).mkdir(parents=True, exist_ok=True)

        def _download() -> DownloadResult:
            holder: dict[str, str | None] = {"filename": None, "title": None}

            def hook(event: dict[str, Any]) -> None:
                if progress_cb:
                    progress_cb(event)
                if event.get("status") == "finished":
                    holder["filename"] = event.get("filename")

            opts = self._base_opts(data)
            opts["progress_hooks"] = [hook]
            opts["format"] = data.format_selector or "bestvideo+bestaudio/best"
            with YoutubeDL(opts) as ydl:
                info = ydl.extract_info(data.url, download=True)
                holder["title"] = info.get("title") if isinstance(info, dict) else None
            return DownloadResult(filepath=holder["filename"], title=holder["title"])

        try:
            return await asyncio.to_thread(_download)
        except DownloadError as exc:
            text = str(exc).lower()
            reason = "Download failed."
            if "sign in" in text or "cookies" in text or "login" in text:
                reason = "Download failed: auth required. Use cookies file or browser cookies."
            elif "unsupported url" in text:
                reason = "Download failed: URL is not supported by yt-dlp."
            elif "geo" in text or "region" in text:
                reason = "Download failed: geo restriction."
            raise RuntimeError(reason) from exc

    def check_version(self) -> str:
        if not YoutubeDL:
            return "N/A"
        # yt-dlp version is not guaranteed on YoutubeDL class; prefer package metadata.
        try:
            from importlib.metadata import version

            return str(version("yt-dlp"))
        except Exception:
            pass
        try:
            import yt_dlp  # type: ignore

            v = getattr(yt_dlp, "__version__", None)
            if v:
                return str(v)
        except Exception:
            pass
        try:
            from yt_dlp import version as yv  # type: ignore

            v = getattr(yv, "__version__", None)
            if v:
                return str(v)
        except Exception:
            pass
        return "unknown"

    @staticmethod
    def to_dict_formats(items: list[FormatInfo]) -> list[dict[str, Any]]:
        return [asdict(i) for i in items]

    @staticmethod
    def build_quality_options(items: list[FormatInfo]) -> list[dict[str, str]]:
        heights: set[int] = set()
        for item in items:
            if item.vcodec in (None, "", "none"):
                continue
            if not item.resolution:
                continue
            text = str(item.resolution).lower()
            if "x" in text:
                try:
                    heights.add(int(text.split("x", 1)[1]))
                except ValueError:
                    continue
            elif text.endswith("p"):
                try:
                    heights.add(int(text[:-1]))
                except ValueError:
                    continue

        options = [{"label": "Auto Best", "value": "bestvideo+bestaudio/best"}]
        for h in sorted(heights, reverse=True):
            options.append({"label": f"{h}p", "value": f"bestvideo[height<={h}]+bestaudio/best[height<={h}]"})
        options.append({"label": "Video Only", "value": "bestvideo/best"})
        options.append({"label": "Audio Only", "value": "bestaudio/best"})
        return options
