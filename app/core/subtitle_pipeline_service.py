from __future__ import annotations

import asyncio
import re
from pathlib import Path
from time import perf_counter
from typing import Any

from app.core.faster_whisper_service import FasterWhisperService
from app.core.models import SubtitleJobInput
from app.core.translation_router import TranslationConfig, TranslationRouter
from app.infra.process_runner import ProcessRunner


class SubtitlePipelineService:
    def __init__(self, ffmpeg_path: str, runner: ProcessRunner | None = None) -> None:
        self.ffmpeg_path = ffmpeg_path
        self.runner = runner or ProcessRunner()
        self.asr = FasterWhisperService()
        self.translator = TranslationRouter()

    async def download_model(
        self,
        model_name: str,
        model_dir: str | None,
        compute_preference: str = "auto",
        progress_cb=None,
    ) -> dict[str, str | bool]:
        return await self.asr.download_model(
            model_name,
            model_dir,
            compute_preference=compute_preference,
            progress_cb=progress_cb,
        )

    async def warmup_model(
        self,
        model_name: str,
        model_dir: str | None,
        compute_preference: str = "auto",
        progress_cb=None,
    ) -> None:
        await self.asr.warmup_model(
            model_name,
            model_dir,
            compute_preference=compute_preference,
            local_only=True,
            progress_cb=progress_cb,
        )

    async def unload_model(self) -> None:
        await self.asr.unload_model_async()

    async def run(self, data: SubtitleJobInput, progress_cb=None) -> dict[str, Any]:
        if data.preset_mode == "one_click_voice":
            return await self._run_voice_audio_mode(data, progress_cb=progress_cb)
        return await self._run_normal_mode(data, progress_cb=progress_cb)

    async def _run_normal_mode(self, data: SubtitleJobInput, progress_cb=None) -> dict[str, Any]:
        run_start = perf_counter()
        timings: dict[str, float] = {}
        effective_run_mode = "all" if data.preset_mode == "one_click_normal" else data.run_mode
        output_dir = Path(data.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        media_path = data.video_path
        stem = Path(media_path).stem
        raw_srt = output_dir / f"{stem}.raw.srt"
        translated_srt = output_dir / f"{stem}.{data.target_lang}.srt"
        out_video = output_dir / f"{stem}.localized.mkv"
        audio_only_input = self._is_audio_only_media(media_path)

        has_raw = self._usable_srt(raw_srt)
        has_translated = self._usable_srt(translated_srt)
        asr_ran = False

        if effective_run_mode in {"all", "asr_only"}:
            if has_raw:
                if progress_cb:
                    progress_cb({"stage": "asr", "progress": 20.0, "message": f"Reuse existing ASR subtitle: {raw_srt.name}"})
            else:
                if progress_cb:
                    progress_cb({"stage": "asr", "progress": 20.0, "message": "ASR started"})
                asr_start = perf_counter()
                await self._run_asr(data, str(raw_srt), media_path=media_path, progress_cb=progress_cb)
                timings["asr_seconds"] = perf_counter() - asr_start
                asr_ran = True
                has_raw = self._usable_srt(raw_srt)
                if not has_raw:
                    raise RuntimeError("ASR finished but raw subtitle was not generated.")

        if effective_run_mode == "asr_only":
            if progress_cb:
                progress_cb({"stage": "done", "progress": 100.0, "message": "ASR finished"})
            return {
                "raw_srt": str(raw_srt),
                "translated_srt": str(translated_srt),
                "output_video": "",
                "timings": timings,
            }

        if not has_raw:
            raise RuntimeError(f"Missing raw subtitle: {raw_srt.name}. Please run 'ASR only' first or use full mode.")

        if (
            effective_run_mode == "all"
            and asr_ran
            and data.auto_unload_after_asr
            and data.asr_backend == "faster_whisper"
        ):
            if progress_cb:
                progress_cb({"stage": "asr", "progress": 52.0, "message": "ASR done, unloading local model to free VRAM..."})
            unload_start = perf_counter()
            try:
                await self.unload_model()
                timings["auto_unload_seconds"] = perf_counter() - unload_start
                if progress_cb:
                    progress_cb({"stage": "asr", "progress": 54.0, "message": "Local ASR model unloaded"})
            except Exception as exc:  # noqa: BLE001
                if progress_cb:
                    progress_cb({"stage": "asr", "progress": 54.0, "message": f"Auto unload skipped: {exc}"})

        if effective_run_mode in {"all", "translate_only"}:
            if has_translated and data.translator_provider != "none":
                if progress_cb:
                    progress_cb({"stage": "translate", "progress": 55.0, "message": f"Reuse existing translated subtitle: {translated_srt.name}"})
            else:
                if progress_cb:
                    progress_cb({"stage": "translate", "progress": 55.0, "message": "Translation started"})
                translate_start = perf_counter()
                await self._translate_srt(raw_srt, translated_srt, data)
                timings["translate_seconds"] = perf_counter() - translate_start

        if effective_run_mode == "translate_only":
            if progress_cb:
                progress_cb({"stage": "done", "progress": 100.0, "message": "Translation finished"})
            return {
                "raw_srt": str(raw_srt),
                "translated_srt": str(translated_srt),
                "output_video": "",
                "timings": timings,
            }

        if not self._usable_srt(translated_srt):
            if data.translator_provider == "none":
                translated_srt.write_text(raw_srt.read_text(encoding="utf-8", errors="replace"), encoding="utf-8")
            else:
                raise RuntimeError(f"Missing translated subtitle: {translated_srt.name}. Please run 'Translate only' first or use full mode.")

        if effective_run_mode == "embed_only" and audio_only_input:
            raise RuntimeError("Embed-only requires a video input. Current input is audio-only.")

        if audio_only_input:
            if progress_cb:
                progress_cb({"stage": "done", "progress": 100.0, "message": "Audio input detected: finished ASR + translation only"})
            if effective_run_mode == "all":
                timings["total_seconds"] = perf_counter() - run_start
            return {
                "raw_srt": str(raw_srt),
                "translated_srt": str(translated_srt),
                "output_video": "",
                "timings": timings,
            }

        if progress_cb:
            progress_cb({"stage": "mux", "progress": 90.0, "message": "Muxing subtitles"})
        mux_start = perf_counter()
        await self._mux_subtitle(media_path, translated_srt, out_video)
        timings["mux_seconds"] = perf_counter() - mux_start

        if progress_cb:
            progress_cb({"stage": "done", "progress": 100.0, "message": "Done"})
        if effective_run_mode == "all":
            timings["total_seconds"] = perf_counter() - run_start
        return {
            "raw_srt": str(raw_srt),
            "translated_srt": str(translated_srt),
            "output_video": str(out_video),
            "timings": timings,
        }

    async def _run_voice_audio_mode(self, data: SubtitleJobInput, progress_cb=None) -> dict[str, Any]:
        if data.run_mode != "all":
            raise RuntimeError("Audio-localization preset only supports one-click mode.")
        run_start = perf_counter()
        timings: dict[str, float] = {}
        output_dir = Path(data.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        image_path = data.voice_image_path or ""
        audio_path = data.voice_audio_path or ""
        subtitle_path = (data.voice_subtitle_path or "").strip()
        if not image_path or not audio_path:
            raise RuntimeError("Audio-localization mode requires both image and audio.")

        stem = Path(audio_path).stem
        raw_srt = output_dir / f"{stem}.raw.srt"
        translated_srt = output_dir / f"{stem}.{data.target_lang}.srt"
        output_video = self._unique_output_path(output_dir / f"{stem}.voice.localized.{data.voice_output_container}")

        merge_subtitle_path: Path
        if subtitle_path:
            merge_subtitle_path = Path(subtitle_path)
            if not merge_subtitle_path.exists():
                raise RuntimeError(f"Subtitle file not found: {merge_subtitle_path}")
            if progress_cb:
                progress_cb({"stage": "prepare", "progress": 55.0, "message": "Using provided subtitle file"})
        else:
            has_raw = self._usable_srt(raw_srt)
            if not has_raw:
                if progress_cb:
                    progress_cb({"stage": "asr", "progress": 20.0, "message": "ASR started (audio-localization mode)"})
                asr_start = perf_counter()
                await self._run_asr(data, str(raw_srt), media_path=audio_path, progress_cb=progress_cb)
                timings["asr_seconds"] = perf_counter() - asr_start
                has_raw = self._usable_srt(raw_srt)
                if not has_raw:
                    raise RuntimeError("ASR finished but subtitle was not generated.")

            if data.auto_unload_after_asr and data.asr_backend == "faster_whisper":
                unload_start = perf_counter()
                await self.unload_model()
                timings["auto_unload_seconds"] = perf_counter() - unload_start

            if progress_cb:
                progress_cb({"stage": "translate", "progress": 55.0, "message": "Translation started"})
            translate_start = perf_counter()
            await self._translate_srt(raw_srt, translated_srt, data)
            timings["translate_seconds"] = perf_counter() - translate_start
            merge_subtitle_path = translated_srt if self._usable_srt(translated_srt) else raw_srt

        if progress_cb:
            progress_cb({"stage": "mux", "progress": 90.0, "message": "Merging image/audio/subtitle"})
        mux_start = perf_counter()
        await self._merge_voice_audio_assets(
            image_path=image_path,
            audio_path=audio_path,
            subtitle_path=merge_subtitle_path,
            output_path=output_video,
            container=data.voice_output_container,
            quality=data.voice_output_quality,
            subtitle_mode=data.voice_subtitle_mode,
        )
        timings["mux_seconds"] = perf_counter() - mux_start

        if progress_cb:
            progress_cb({"stage": "done", "progress": 100.0, "message": "Done"})
        timings["total_seconds"] = perf_counter() - run_start
        return {
            "raw_srt": str(raw_srt if raw_srt.exists() else merge_subtitle_path),
            "translated_srt": str(translated_srt if translated_srt.exists() else merge_subtitle_path),
            "output_video": str(output_video),
            "timings": timings,
        }

    async def _run_asr(self, data: SubtitleJobInput, out_srt: str, media_path: str, progress_cb=None) -> None:
        if data.asr_backend != "faster_whisper":
            temp_audio_path: Path | None = None
            if (
                data.asr_backend in {"asr_gemini", "asr_qwen"}
                or self._is_gemini_openai_base(data.asr_api_base_url or "")
                or self._is_qwen_openai_base(data.asr_api_base_url or "")
            ):
                temp_audio_path = Path(out_srt).with_suffix(".cloud_asr.wav")
                if progress_cb:
                    progress_cb({"stage": "asr", "progress": 15.0, "message": "Preparing cloud ASR audio (wav)..."})
                await self._extract_audio_for_cloud_asr(media_path, temp_audio_path)
                media_path = str(temp_audio_path)
            try:
                await self.asr.transcribe_cloud_to_srt(
                    media_path=media_path,
                    out_srt=out_srt,
                    api_base_url=data.asr_api_base_url or "",
                    api_key=data.asr_api_key or "",
                    model_name=data.asr_model_name,
                    source_lang=data.source_lang,
                    backend=data.asr_backend,
                )
            finally:
                if temp_audio_path and temp_audio_path.exists():
                    try:
                        temp_audio_path.unlink()
                    except Exception:
                        pass
            return
        await self.asr.transcribe_to_srt(
            video_path=media_path,
            model_name=data.whisper_model,
            out_srt=out_srt,
            source_lang=data.source_lang,
            compute_preference=data.asr_compute_type,
            model_dir=data.model_dir,
            progress_cb=progress_cb,
        )

    @staticmethod
    def _is_gemini_openai_base(api_base_url: str) -> bool:
        return "generativelanguage.googleapis.com" in (api_base_url or "").lower()

    @staticmethod
    def _is_qwen_openai_base(api_base_url: str) -> bool:
        return "dashscope.aliyuncs.com" in (api_base_url or "").lower()

    async def _extract_audio_for_cloud_asr(self, media_path: str, out_wav: Path) -> None:
        out_wav.parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            self.ffmpeg_path,
            "-hide_banner",
            "-y",
            "-i",
            media_path,
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "pcm_s16le",
            str(out_wav),
        ]
        code, _, err = await self.runner.run(cmd)
        if code != 0:
            raise RuntimeError(f"Cloud ASR audio preparation failed: {err[-500:]}")

    @staticmethod
    def _usable_srt(path: Path) -> bool:
        if not path.exists():
            return False
        try:
            txt = path.read_text(encoding="utf-8", errors="replace").strip()
        except Exception:  # noqa: BLE001
            return False
        # Basic validity: has timestamp marker and some text.
        return bool(txt) and "-->" in txt

    async def _translate_srt(self, src: Path, dst: Path, data: SubtitleJobInput) -> None:
        if data.translator_provider == "none" or data.target_lang in {"", "auto"}:
            dst.write_text(src.read_text(encoding="utf-8", errors="replace"), encoding="utf-8")
            return

        content = src.read_text(encoding="utf-8", errors="replace")
        blocks = [b for b in re.split(r"\n\s*\n", content) if b.strip()]

        cfg = TranslationConfig(
            provider=data.translator_provider,
            base_url=data.api_base_url,
            api_key=data.api_key,
            model_name=data.model_name,
            extra_headers=data.extra_headers,
        )

        out_blocks: list[str] = []
        for i, block in enumerate(blocks):
            lines = block.splitlines()
            if len(lines) < 3:
                out_blocks.append(block)
                continue
            text = "\n".join(lines[2:]).strip()
            translated = await asyncio.to_thread(self.translator.translate, text, data.target_lang, cfg)
            out_blocks.append("\n".join(lines[:2] + [translated]))
            if i and i % 20 == 0:
                await asyncio.sleep(0)
        dst.write_text("\n\n".join(out_blocks).strip() + "\n", encoding="utf-8")

    @staticmethod
    def _is_audio_only_media(path: str) -> bool:
        ext = Path(path).suffix.lower()
        return ext in {".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg", ".opus", ".wma"}

    @staticmethod
    def _unique_output_path(path: Path) -> Path:
        if not path.exists():
            return path
        idx = 1
        while True:
            candidate = path.with_name(f"{path.stem} ({idx}){path.suffix}")
            if not candidate.exists():
                return candidate
            idx += 1

    @staticmethod
    def _pick_video_codec_args(quality: str) -> list[str]:
        if quality == "nvidia_h265":
            return [
                "-c:v",
                "hevc_nvenc",
                "-preset",
                "p5",
                "-rc",
                "vbr",
                "-cq",
                "23",
                "-b:v",
                "0",
                "-pix_fmt",
                "yuv420p",
            ]
        return ["-c:v", "libx264", "-crf", "18", "-preset", "medium", "-pix_fmt", "yuv420p"]

    @staticmethod
    def _escape_subtitle_filter_path(path: str) -> str:
        escaped = path.replace("\\", "/")
        escaped = escaped.replace(":", "\\:")
        escaped = escaped.replace("'", r"\'")
        return escaped

    @staticmethod
    def _needs_mov_text(out_path: Path, subtitle_path: Path) -> bool:
        return out_path.suffix.lower() == ".mp4" and subtitle_path.suffix.lower() == ".srt"

    async def _merge_voice_audio_assets(
        self,
        *,
        image_path: str,
        audio_path: str,
        subtitle_path: Path,
        output_path: Path,
        container: str,
        quality: str,
        subtitle_mode: str,
    ) -> None:
        _ = container
        effective_quality = quality if quality != "lossless_copy" else "cpu_h264"
        cmd = [
            self.ffmpeg_path,
            "-hide_banner",
            "-n",
            "-loop",
            "1",
            "-i",
            image_path,
            "-i",
            audio_path,
        ]
        if subtitle_mode == "soft":
            cmd.extend(["-i", str(subtitle_path)])
        elif subtitle_mode == "hard":
            escaped_sub = self._escape_subtitle_filter_path(str(subtitle_path))
            cmd.extend(["-vf", f"subtitles='{escaped_sub}'"])

        cmd.extend(self._pick_video_codec_args(effective_quality))
        cmd.extend(["-map", "0:v:0", "-map", "1:a:0", "-c:a", "aac", "-b:a", "256k"])

        if subtitle_mode == "soft":
            cmd.extend(["-map", "2:s:0"])
            if self._needs_mov_text(output_path, subtitle_path):
                cmd.extend(["-c:s", "mov_text"])
            else:
                cmd.extend(["-c:s", "copy"])
            cmd.extend(["-disposition:s:0", "default"])

        cmd.extend(["-shortest", str(output_path)])
        code, _, err = await self.runner.run(cmd)
        if code != 0:
            raise RuntimeError(f"Audio-localization merge failed: {err[-500:]}")

    async def _mux_subtitle(self, video_path: str, subtitle_path: Path, output_video: Path) -> None:
        cmd = [
            self.ffmpeg_path,
            "-hide_banner",
            "-n",
            "-i",
            video_path,
            "-i",
            str(subtitle_path),
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
            str(output_video),
        ]
        code, _, err = await self.runner.run(cmd)
        if code != 0:
            raise RuntimeError(f"Mux failed: {err[-500:]}")
