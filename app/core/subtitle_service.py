from __future__ import annotations

import asyncio
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib import request
import json

from app.infra.process_runner import ProcessRunner


@dataclass(slots=True)
class SubtitleJobInput:
    video_path: str
    output_dir: str
    whisper_model: str = "small"
    source_lang: str = "auto"
    target_lang: str = "zh"
    translator: str = "none"  # none | ollama | openai
    llm_model: str = "gpt-4o-mini"


class SubtitleService:
    def __init__(self, ffmpeg_path: str, runner: ProcessRunner | None = None) -> None:
        self.ffmpeg_path = ffmpeg_path
        self.runner = runner or ProcessRunner()

    async def localize_video(self, data: SubtitleJobInput, progress_cb=None) -> dict[str, str]:
        output_dir = Path(data.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        stem = Path(data.video_path).stem
        raw_srt = output_dir / f"{stem}.raw.srt"
        translated_srt = output_dir / f"{stem}.{data.target_lang}.srt"
        out_video = output_dir / f"{stem}.localized.mkv"

        if progress_cb:
            progress_cb({"stage": "transcribe", "message": "Transcribing with Whisper..."})
        await self._transcribe_to_srt(data, raw_srt)

        if progress_cb:
            progress_cb({"stage": "translate", "message": "Translating subtitle lines..."})
        await self._translate_srt(raw_srt, translated_srt, data)

        if progress_cb:
            progress_cb({"stage": "mux", "message": "Muxing subtitle with original video..."})
        await self._mux_subtitle(data.video_path, translated_srt, out_video)

        return {
            "raw_srt": str(raw_srt),
            "translated_srt": str(translated_srt),
            "output_video": str(out_video),
        }

    async def _transcribe_to_srt(self, data: SubtitleJobInput, out_srt: Path) -> None:
        try:
            import whisper  # type: ignore
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError("Local Whisper unavailable. Install: pip install openai-whisper") from exc

        def _run() -> None:
            model = whisper.load_model(data.whisper_model)
            kwargs: dict[str, Any] = {"task": "transcribe"}
            if data.source_lang and data.source_lang != "auto":
                kwargs["language"] = data.source_lang
            result = model.transcribe(data.video_path, **kwargs)
            self._segments_to_srt(result.get("segments", []), out_srt)

        await asyncio.to_thread(_run)

    async def _translate_srt(self, src_srt: Path, out_srt: Path, data: SubtitleJobInput) -> None:
        if data.target_lang in {"", "auto"} or data.translator == "none":
            shutil.copy2(src_srt, out_srt)
            return

        content = src_srt.read_text(encoding="utf-8", errors="replace")
        blocks = [b for b in re.split(r"\n\s*\n", content) if b.strip()]
        out_blocks: list[str] = []
        for block in blocks:
            lines = block.splitlines()
            if len(lines) < 3:
                out_blocks.append(block)
                continue
            text_lines = lines[2:]
            original = "\n".join(text_lines).strip()
            translated = await self._translate_text(original, data)
            out_blocks.append("\n".join(lines[:2] + [translated]))
        out_srt.write_text("\n\n".join(out_blocks) + "\n", encoding="utf-8")

    async def _translate_text(self, text: str, data: SubtitleJobInput) -> str:
        if not text.strip():
            return text
        if data.translator == "ollama":
            return await asyncio.to_thread(self._translate_with_ollama, text, data.target_lang, data.llm_model)
        if data.translator == "openai":
            return await asyncio.to_thread(self._translate_with_openai, text, data.target_lang, data.llm_model)
        return text

    @staticmethod
    def _translate_with_ollama(text: str, target_lang: str, model: str) -> str:
        payload = {
            "model": model,
            "stream": False,
            "prompt": f"Translate to {target_lang}. Keep one subtitle line, no explanations:\n{text}",
        }
        req = request.Request(
            "http://localhost:11434/api/generate",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with request.urlopen(req, timeout=120) as resp:  # noqa: S310
            data = json.loads(resp.read().decode("utf-8"))
        return str(data.get("response", text)).strip() or text

    @staticmethod
    def _translate_with_openai(text: str, target_lang: str, model: str) -> str:
        try:
            from openai import OpenAI  # type: ignore
        except Exception as exc:  # noqa: BLE001
            raise RuntimeError("OpenAI SDK unavailable. Install: pip install openai") from exc
        client = OpenAI()
        response = client.responses.create(
            model=model,
            input=f"Translate to {target_lang}. Keep concise subtitle style and no commentary:\n{text}",
        )
        output_text = getattr(response, "output_text", "") or ""
        return output_text.strip() or text

    async def _mux_subtitle(self, video_path: str, srt_path: Path, out_video: Path) -> None:
        cmd = [
            self.ffmpeg_path,
            "-hide_banner",
            "-n",
            "-i",
            video_path,
            "-i",
            str(srt_path),
            "-map",
            "0:v:0?",
            "-map",
            "0:a:0?",
            "-map",
            "1:0",
            "-c:v",
            "copy",
            "-c:a",
            "copy",
            "-c:s",
            "srt",
            str(out_video),
        ]
        code, _, err = await self.runner.run(cmd)
        if code != 0:
            raise RuntimeError(f"Mux subtitle failed: {err[-500:]}")

    @staticmethod
    def _segments_to_srt(segments: list[dict[str, Any]], out_srt: Path) -> None:
        lines: list[str] = []
        for idx, seg in enumerate(segments, start=1):
            start = SubtitleService._fmt_time(float(seg.get("start", 0.0)))
            end = SubtitleService._fmt_time(float(seg.get("end", 0.0)))
            text = str(seg.get("text", "")).strip()
            if not text:
                continue
            lines.extend([str(idx), f"{start} --> {end}", text, ""])
        out_srt.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")

    @staticmethod
    def _fmt_time(seconds: float) -> str:
        ms = int(max(0.0, seconds) * 1000)
        h, rem = divmod(ms, 3_600_000)
        m, rem = divmod(rem, 60_000)
        s, rem = divmod(rem, 1000)
        return f"{h:02d}:{m:02d}:{s:02d},{rem:03d}"

